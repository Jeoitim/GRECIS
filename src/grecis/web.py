from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import AppConfig, load_config
from .db import CorpusDB, ensure_db
from .dictionary import query_word
from .ingest import fetch_url
from .llm import LLMAnalyzer, post_chat_completion_raw
from .models import Article
from .nlp import analyze_article

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_CONFIG_PATH = PROJECT_ROOT / "config" / "local.yaml"
MasteryLevel = Literal["learning", "familiar", "mastered"]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def read_json(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback


def get_config() -> AppConfig:
    return load_config(LOCAL_CONFIG_PATH)


def get_db() -> CorpusDB:
    config = get_config()
    path = Path(config.database.path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return ensure_db(path)


def compact_text(value: str, limit: int = 180) -> str:
    text = " ".join((value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def article_summary(row: Any) -> dict[str, Any]:
    metadata = read_json(row["metadata_json"], {})
    return {
        "id": row["id"],
        "title": row["title"],
        "source": row["source"],
        "url": row["url"],
        "published_at": row["published_at"],
        "field": row["analysis_field"] or row["field"],
        "created_at": row["created_at"],
        "difficulty": row["difficulty"],
        "exam_value": row["exam_value"],
        "progress": row["progress"] or 0,
        "last_read_at": row["last_read_at"] or "",
        "word_count": len((row["text"] or "").split()),
        "snippet": compact_text(metadata.get("description") or row["text"]),
    }


def analysis_digest(llm: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    rhetoric = llm.get("rhetoric") if isinstance(llm.get("rhetoric"), list) else []
    exam_value = llm.get("exam_value") if isinstance(llm.get("exam_value"), dict) else {}
    types = []
    for item in rhetoric:
        if not isinstance(item, dict):
            continue
        value = str(item.get("canonical_type") or item.get("type") or "").strip()
        if value and value not in types:
            types.append(value)
    first = next((item for item in rhetoric if isinstance(item, dict)), {})
    note = str(
        first.get("reading_tip_zh")
        or first.get("reading_tip")
        or first.get("explanation_zh")
        or first.get("explanation")
        or ""
    )
    return {
        "insight": (
            f"模型识别出 {len(rhetoric)} 个可迁移的论证与句式节点。"
            if rhetoric
            else "当前文章已有本地 NLP 分析，尚无可展示的 LLM 修辞摘要。"
        ),
        "structure": " → ".join(types[:3]) or "本地结构识别",
        "domain": exam_value.get("primary_domain") or analysis.get("field") or "unknown",
        "note": note or "结合正文中的转折、限定和因果线索进行精读。",
        "model": (llm.get("_meta") or {}).get("model", ""),
        "rhetoric_count": len(rhetoric),
    }


class SettingsUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str = Field(default="", max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)


class MasteryUpdate(BaseModel):
    level: MasteryLevel | None = None


class ProgressUpdate(BaseModel):
    progress: int = Field(default=0, ge=0, le=100)


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source: str = Field(default="manual", max_length=200)
    url: str = Field(default="", max_length=2000)
    text: str = ""
    use_llm: bool = False


app = FastAPI(title="GRECIS Local Reading API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    db = get_db()
    with db.connect() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("articles", "analyses", "vocabulary", "collocations")
        }
        unique_words = conn.execute("SELECT COUNT(DISTINCT lemma) FROM vocabulary").fetchone()[0]
        fields = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT field FROM analyses WHERE field != '' ORDER BY field"
            ).fetchall()
        ]
    return {"ok": True, "counts": counts, "unique_words": unique_words, "fields": fields}


@app.get("/api/articles")
def list_articles(
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=200),
    field: str = Query(default="", max_length=100),
) -> dict[str, Any]:
    db = get_db()
    conditions: list[str] = []
    params: list[Any] = []
    if q:
        conditions.append("(a.title LIKE ? OR a.source LIKE ? OR a.text LIKE ?)")
        term = f"%{q}%"
        params.extend([term, term, term])
    if field:
        conditions.append("COALESCE(an.field, a.field) = ?")
        params.append(field)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db.connect() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM articles a
            LEFT JOIN analyses an ON an.article_id = a.id
            {where}
            """,
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT a.*, an.field AS analysis_field, an.difficulty, an.exam_value,
                   rp.progress, rp.last_read_at
            FROM articles a
            LEFT JOIN analyses an ON an.article_id = a.id
            LEFT JOIN reading_progress rp ON rp.article_id = a.id
            {where}
            ORDER BY COALESCE(rp.last_read_at, a.created_at) DESC, a.title
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return {
        "items": [article_summary(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/articles/{article_id}")
def get_article(article_id: str) -> dict[str, Any]:
    db = get_db()
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT a.*, an.field AS analysis_field, an.field_scores_json, an.difficulty,
                   an.exam_value, an.llm_json, an.created_at AS analyzed_at,
                   rp.progress, rp.last_read_at
            FROM articles a
            LEFT JOIN analyses an ON an.article_id = a.id
            LEFT JOIN reading_progress rp ON rp.article_id = a.id
            WHERE a.id = ?
            """,
            (article_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文章不存在")
        vocabulary = [
            dict(item)
            for item in conn.execute(
                """
                SELECT v.*, wm.level AS mastery
                FROM vocabulary v
                LEFT JOIN word_mastery wm ON wm.lemma = v.lemma
                WHERE v.article_id = ?
                ORDER BY v.importance DESC, v.frequency DESC, v.lemma
                """,
                (article_id,),
            ).fetchall()
        ]
        collocations = [
            dict(item)
            for item in conn.execute(
                """
                SELECT * FROM collocations
                WHERE article_id = ?
                ORDER BY importance DESC, frequency DESC
                """,
                (article_id,),
            ).fetchall()
        ]
        polysemy = [
            dict(item)
            for item in conn.execute(
                "SELECT * FROM polysemy WHERE article_id = ? ORDER BY word", (article_id,)
            ).fetchall()
        ]
        patterns = [
            dict(item)
            for item in conn.execute(
                "SELECT * FROM sentence_patterns WHERE article_id = ? ORDER BY importance DESC",
                (article_id,),
            ).fetchall()
        ]
    llm = read_json(row["llm_json"], {})
    analysis = {
        "field": row["analysis_field"] or row["field"],
        "field_scores": read_json(row["field_scores_json"], {}),
        "difficulty": row["difficulty"],
        "exam_value": row["exam_value"],
        "created_at": row["analyzed_at"],
    }
    summary = article_summary(row)
    return {
        **summary,
        "text": row["text"],
        "metadata": read_json(row["metadata_json"], {}),
        "analysis": analysis,
        "digest": analysis_digest(llm, analysis),
        "vocabulary": vocabulary,
        "collocations": collocations,
        "polysemy": polysemy,
        "sentence_patterns": patterns,
    }


@app.post("/api/articles")
def create_article(payload: ArticleCreate) -> dict[str, Any]:
    config = get_config()
    db = get_db()
    if not payload.text.strip() and not payload.url.strip():
        raise HTTPException(status_code=400, detail="正文和链接至少需要填写一项")
    try:
        article = (
            fetch_url(payload.url, source=payload.source, crawler=config.crawler)
            if not payload.text.strip()
            else Article(
                title=payload.title,
                text=payload.text.strip(),
                source=payload.source,
                url=payload.url,
            )
        )
        article_id = db.upsert_article(article)
        llm_payload: dict[str, Any] = {}
        if payload.use_llm:
            analyzer = LLMAnalyzer.from_config(
                config.llm.model, config.llm.api_key, config.llm.base_url
            )
            llm_payload = analyzer.analyze(article)
        db.save_analysis(analyze_article(article, llm_payload=llm_payload))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"文章导入失败：{exc}") from exc
    return get_article(article_id)


@app.put("/api/articles/{article_id}/progress")
def save_progress(article_id: str, payload: ProgressUpdate) -> dict[str, Any]:
    db = get_db()
    if not db.get_article(article_id):
        raise HTTPException(status_code=404, detail="文章不存在")
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO reading_progress(article_id, progress, last_read_at)
            VALUES (?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE SET
                progress=excluded.progress, last_read_at=excluded.last_read_at
            """,
            (article_id, payload.progress, now_iso()),
        )
    return {"ok": True, "progress": payload.progress}


@app.post("/api/articles/{article_id}/analyze")
def reanalyze_article(article_id: str, use_llm: bool = True) -> dict[str, Any]:
    config = get_config()
    db = get_db()
    article = db.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    try:
        llm_payload: dict[str, Any] = {}
        if use_llm:
            analyzer = LLMAnalyzer.from_config(
                config.llm.model, config.llm.api_key, config.llm.base_url
            )
            if not analyzer.enabled():
                raise ValueError("本地配置中尚未设置可用的 LLM API")
            llm_payload = analyzer.analyze(article)
        db.save_analysis(analyze_article(article, llm_payload=llm_payload))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"分析失败：{exc}") from exc
    return get_article(article_id)


@app.get("/api/vocabulary")
def list_vocabulary(
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=100),
    mastery: str = Query(default="", max_length=20),
) -> dict[str, Any]:
    db = get_db()
    conditions: list[str] = []
    params: list[Any] = []
    if q:
        conditions.append("(v.lemma LIKE ? OR v.word LIKE ?)")
        term = f"%{q}%"
        params.extend([term, term])
    if mastery == "unmarked":
        conditions.append("wm.level IS NULL")
    elif mastery in {"learning", "familiar", "mastered"}:
        conditions.append("wm.level = ?")
        params.append(mastery)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db.connect() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT v.lemma
                FROM vocabulary v
                LEFT JOIN word_mastery wm ON wm.lemma = v.lemma
                {where}
                GROUP BY v.lemma
            )
            """,
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT v.lemma, MIN(v.word) AS word, SUM(v.frequency) AS frequency,
                   MAX(v.importance) AS importance, COUNT(DISTINCT v.article_id) AS article_count,
                   MIN(NULLIF(v.example_sentence, '')) AS example_sentence,
                   GROUP_CONCAT(DISTINCT v.category) AS categories,
                   GROUP_CONCAT(DISTINCT v.field) AS fields,
                   wm.level AS mastery, wm.updated_at
            FROM vocabulary v
            LEFT JOIN word_mastery wm ON wm.lemma = v.lemma
            {where}
            GROUP BY v.lemma
            ORDER BY MAX(v.importance) DESC, COUNT(DISTINCT v.article_id) DESC,
                     SUM(v.frequency) DESC, v.lemma
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@app.put("/api/vocabulary/{lemma}/mastery")
def save_mastery(lemma: str, payload: MasteryUpdate) -> dict[str, Any]:
    normalized = re.sub(r"[^a-zA-Z '-]", "", lemma).strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="词条格式不正确")
    db = get_db()
    with db.connect() as conn:
        if payload.level is None:
            conn.execute("DELETE FROM word_mastery WHERE lemma = ?", (normalized,))
        else:
            conn.execute(
                """
                INSERT INTO word_mastery(lemma, level, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(lemma) DO UPDATE SET
                    level=excluded.level, updated_at=excluded.updated_at
                """,
                (normalized, payload.level, now_iso()),
            )
    return {"ok": True, "lemma": normalized, "level": payload.level}


@app.get("/api/analysis-history")
def analysis_history(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    db = get_db()
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        rows = conn.execute(
            """
            SELECT an.article_id, a.title, a.source, an.field, an.difficulty,
                   an.exam_value, an.created_at, an.llm_json
            FROM analyses an
            JOIN articles a ON a.id = an.article_id
            ORDER BY an.created_at DESC, a.title
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        llm = read_json(item.pop("llm_json"), {})
        item["mode"] = "LLM + NLP" if llm else "LOCAL NLP"
        item["model"] = (llm.get("_meta") or {}).get("model", "")
        items.append(item)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def read_local_mapping() -> dict[str, Any]:
    if not LOCAL_CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(LOCAL_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def write_local_mapping(payload: dict[str, Any]) -> None:
    LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = LOCAL_CONFIG_PATH.with_suffix(".yaml.tmp")
    temporary.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    temporary.replace(LOCAL_CONFIG_PATH)


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    config = get_config()
    return {
        "model": config.llm.model,
        "base_url": config.llm.base_url,
        "api_key_set": bool(config.llm.api_key),
    }


@app.put("/api/settings")
def save_settings(payload: SettingsUpdate) -> dict[str, Any]:
    mapping = read_local_mapping()
    llm = mapping.setdefault("llm", {})
    llm["model"] = payload.model.strip()
    llm["base_url"] = payload.base_url.strip()
    if payload.api_key is not None and payload.api_key.strip():
        llm["api_key"] = payload.api_key.strip()
    write_local_mapping(mapping)
    return get_settings()


@app.post("/api/settings/test")
def test_settings(payload: SettingsUpdate) -> dict[str, Any]:
    current = get_config().llm
    api_key = (
        payload.api_key.strip()
        if payload.api_key and payload.api_key.strip()
        else current.api_key
    )
    analyzer = LLMAnalyzer.from_config(payload.model.strip(), api_key, payload.base_url.strip())
    if not analyzer.enabled():
        raise HTTPException(status_code=400, detail="请先填写 API Key 或本地模型地址")
    request = {
        "model": analyzer.model,
        "messages": [{"role": "user", "content": "Reply with OK only."}],
        "temperature": 0,
        "max_tokens": 4,
    }
    try:
        if (analyzer.base_url or "").strip().endswith("/chat/completions"):
            content = post_chat_completion_raw(
                analyzer.base_url or "", analyzer.api_key or "", request, timeout=20
            )
        else:
            response = analyzer.client.chat.completions.create(**request)
            content = response.choices[0].message.content or ""
        if not content.strip():
            raise RuntimeError("模型返回了空响应")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"连接失败：{exc}") from exc
    return {"ok": True, "message": f"已连接模型 {analyzer.model}"}


@app.get("/api/dictionary/{word}")
def dictionary_lookup(word: str) -> dict[str, Any]:
    normalized = re.sub(r"[^a-zA-Z '-]", "", word).strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="词条格式不正确")
    return {"word": normalized, **query_word(normalized)}


def main() -> None:
    uvicorn.run("grecis.web:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()

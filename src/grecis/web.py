from __future__ import annotations

import json
import re
from dataclasses import replace
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
from .ingest import fetch_url, iter_fetch_source_articles
from .llm import (
    ANALYSIS_TIMEOUT_SECONDS,
    LLMAnalyzer,
    is_complete_analysis,
    message_text,
    post_chat_completion_raw,
)
from .models import Article
from .nlp import analyze_article, simple_lemma, tokenize
from .wordlists import match_vocabulary_tier, tier_importance, vocabulary_tier

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


def word_context(text: str, word: str, limit: int = 240) -> str:
    pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
    sentences = re.split(r"(?<=[.!?])\s+", " ".join((text or "").split()))
    sentence = next((item for item in sentences if pattern.search(item)), "")
    return compact_text(sentence, limit)


def article_vocabulary_highlights(
    text: str, vocabulary: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Classify every article token independently from the selected review vocabulary."""
    specialized_words: set[str] = set()
    for item in vocabulary:
        if item.get("category") not in {"polysemy", "熟词生义", "domain terminology"}:
            continue
        for value in (item.get("word"), item.get("lemma")):
            normalized = str(value or "").strip().lower()
            tier = vocabulary_tier(normalized)
            is_polysemy = item.get("category") in {"polysemy", "熟词生义"}
            if normalized and (tier == "rare" or (tier == "high_school" and is_polysemy)):
                specialized_words.add(normalized)

    highlights: dict[str, dict[str, str]] = {}
    for surface in tokenize(text):
        lemma, tier = match_vocabulary_tier(surface)
        if tier in {"core", "key", "gre"}:
            highlights[surface] = {"word": surface, "lemma": lemma, "tier": tier}
        elif tier in {"rare", "high_school"}:
            specialized_lemma = simple_lemma(surface)
            if not (
                surface in specialized_words
                or lemma in specialized_words
                or specialized_lemma in specialized_words
            ):
                continue
            highlights[surface] = {
                "word": surface,
                "lemma": specialized_lemma,
                "tier": "specialized",
            }
    return list(highlights.values())


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


RHETORIC_TYPE_LABELS = {
    "concession": "让步",
    "contrast": "对比",
    "causality": "因果",
    "condition": "条件",
    "stance": "立场表达",
    "hedging": "审慎限定",
    "emphasis": "强调",
    "comparison": "比较",
    "inversion": "倒装",
    "cleft": "强调句",
    "relative_clause": "定语从句",
    "participial_clause": "分词结构",
    "nominal_clause": "名词性从句",
    "argument_development": "论证推进",
}


def analysis_digest(llm: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    valid = is_complete_analysis(llm)
    invalid = bool(llm) and not valid
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
    domain = str(exam_value.get("primary_domain") or analysis.get("field") or "unknown")
    type_labels = [RHETORIC_TYPE_LABELS.get(value, value) for value in types]
    direct_insight = str(
        llm.get("article_insight_zh")
        or llm.get("insight_zh")
        or exam_value.get("article_insight_zh")
        or ""
    ).strip()
    first_explanation = str(
        first.get("explanation_zh")
        or first.get("explanation")
        or first.get("reading_tip_zh")
        or first.get("reading_tip")
        or ""
    ).strip()
    if direct_insight:
        insight = direct_insight
    elif rhetoric:
        structure_text = "、".join(type_labels[:3]) or "多层论证结构"
        detail = f" {first_explanation}" if first_explanation else ""
        insight = f"文章围绕“{domain}”展开，主要通过{structure_text}推进论证。{detail}".strip()
    elif valid:
        insight = "LLM 分析已完成，未识别到可展示的修辞节点。"
    elif invalid:
        insight = "此前的 LLM 返回不完整或无法解析；当前仅展示本地 NLP 结果。"
    else:
        insight = "当前文章已有本地 NLP 分析，尚未进行有效的 LLM 分析。"
    return {
        "insight": insight,
        "structure": " → ".join(type_labels[:3]) or "本地结构识别",
        "domain": domain,
        "note": note or "结合正文中的转折、限定和因果线索进行精读。",
        "model": (llm.get("_meta") or {}).get("model", ""),
        "status": "valid" if valid else ("invalid" if invalid else "local"),
        "rhetoric_count": len(rhetoric),
    }


class SettingsUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str = Field(default="", max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)


class MasteryUpdate(BaseModel):
    level: MasteryLevel | None = None
    article_id: str = Field(default="", max_length=100)
    word: str = Field(default="", max_length=100)


class ProgressUpdate(BaseModel):
    progress: int = Field(default=0, ge=0, le=100)


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source: str = Field(default="manual", max_length=200)
    url: str = Field(default="", max_length=2000)
    text: str = ""
    use_llm: bool = False


class CrawlerFetchRequest(BaseModel):
    source: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=3, ge=1, le=20)
    topic_query: str = Field(default="", max_length=200)
    request_timeout_seconds: int = Field(default=20, ge=5, le=120)
    delay_seconds: float = Field(default=1.0, ge=0, le=10)
    min_text_chars: int = Field(default=800, ge=200, le=20_000)
    min_quality_score: float = Field(default=6.0, ge=0, le=10)
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


@app.get("/api/crawler/options")
def crawler_options() -> dict[str, Any]:
    config = get_config()
    return {
        "sources": [
            {
                "name": source.name,
                "field": source.field_hint,
                "category": source.category,
                "enabled": source.enabled,
            }
            for source in config.sources
            if source.enabled
        ],
        "defaults": {
            "limit": min(config.crawler.max_articles_per_source, 5),
            "request_timeout_seconds": config.crawler.request_timeout_seconds,
            "delay_seconds": config.crawler.delay_seconds,
            "min_text_chars": config.crawler.min_text_chars,
            "min_quality_score": config.crawler.min_quality_score,
        },
    }


@app.post("/api/crawler/fetch")
def fetch_from_crawler(payload: CrawlerFetchRequest) -> dict[str, Any]:
    config = get_config()
    db = get_db()
    sources = [
        source
        for source in config.sources
        if source.enabled
        and (payload.source == "all" or source.name.lower() == payload.source.lower())
    ]
    if not sources:
        raise HTTPException(status_code=404, detail="没有匹配的已启用文章来源")

    analyzer = None
    if payload.use_llm:
        analyzer = LLMAnalyzer.from_config(
            config.llm.model,
            config.llm.api_key,
            config.llm.base_url,
        )
        if not analyzer.enabled():
            raise HTTPException(status_code=400, detail="本地配置中尚未设置可用的 LLM API")

    crawler = replace(
        config.crawler,
        max_articles_per_source=payload.limit,
        request_timeout_seconds=payload.request_timeout_seconds,
        delay_seconds=payload.delay_seconds,
        min_text_chars=payload.min_text_chars,
        min_quality_score=payload.min_quality_score,
    )
    existing_urls = {article.url for article in db.list_articles() if article.url}
    article_ids: list[str] = []
    errors: list[str] = []
    for source in sources:
        runtime_source = source
        if payload.topic_query.strip() and source.search_url_templates:
            runtime_source = replace(
                source,
                topic_queries=list(
                    dict.fromkeys([payload.topic_query.strip(), *source.topic_queries])
                ),
            )
        for article in iter_fetch_source_articles(
            runtime_source,
            crawler,
            existing_urls=existing_urls,
        ):
            article_id = db.upsert_article(article)
            llm_payload: dict[str, Any] = {}
            if analyzer:
                try:
                    llm_payload = analyzer.analyze(article)
                except Exception as exc:
                    errors.append(f"{article.title}：LLM 分析失败（{exc}）")
            db.save_analysis(analyze_article(article, llm_payload=llm_payload))
            article_ids.append(article_id)

    return {
        "ok": True,
        "imported": len(article_ids),
        "analyzed": len(article_ids),
        "items": [get_article(article_id) for article_id in article_ids],
        "errors": errors,
    }


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


@app.get("/api/recent-articles")
def list_recent_articles(
    limit: int = Query(default=12, ge=1, le=100),
) -> dict[str, Any]:
    db = get_db()
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT a.*, an.field AS analysis_field, an.difficulty, an.exam_value,
                   rp.progress, rp.last_read_at
            FROM reading_progress rp
            JOIN articles a ON a.id = rp.article_id
            LEFT JOIN analyses an ON an.article_id = a.id
            ORDER BY rp.last_read_at DESC, a.title
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM reading_progress").fetchone()[0]
    return {"items": [article_summary(row) for row in rows], "total": total, "limit": limit}


@app.delete("/api/reading-progress")
def clear_reading_progress() -> dict[str, Any]:
    db = get_db()
    with db.connect() as conn:
        deleted = conn.execute("SELECT COUNT(*) FROM reading_progress").fetchone()[0]
        conn.execute("DELETE FROM reading_progress")
    return {"ok": True, "deleted": deleted}


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
        vocabulary = [
            {
                **item,
                "tier": vocabulary_tier(item["lemma"]),
                "importance": tier_importance(vocabulary_tier(item["lemma"])) or 1,
            }
            for item in vocabulary
            if (
                vocabulary_tier(item["lemma"]) not in {"high_school", "rare"}
                or item["category"] == "polysemy"
                or (
                    vocabulary_tier(item["lemma"]) == "rare"
                    and item["category"] == "domain terminology"
                )
            )
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
        mastery_words = [
            dict(item)
            for item in conn.execute(
                "SELECT lemma, level FROM word_mastery ORDER BY lemma"
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
        "vocabulary_highlights": article_vocabulary_highlights(row["text"], vocabulary),
        "collocations": collocations,
        "polysemy": polysemy,
        "sentence_patterns": patterns,
        "mastery_words": mastery_words,
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
        error_text = str(exc)
        if "timeout" in error_text.lower() or "timed out" in error_text.lower():
            error_text = (
                f"LLM 在 {int(ANALYSIS_TIMEOUT_SECONDS)} 秒内未完成生成；"
                "请稍后重试，或改用响应更快的模型"
            )
        raise HTTPException(status_code=502, detail=f"分析失败：{error_text}") from exc
    return get_article(article_id)


@app.get("/api/vocabulary")
def list_vocabulary(
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=100),
    mastery: str = Query(default="", max_length=20),
) -> dict[str, Any]:
    db = get_db()
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT v.lemma, MIN(v.word) AS word, SUM(v.frequency) AS frequency,
                   MAX(v.importance) AS importance,
                   COUNT(DISTINCT v.article_id) AS article_count,
                   MIN(NULLIF(v.example_sentence, '')) AS example_sentence,
                   GROUP_CONCAT(DISTINCT v.category) AS categories,
                   GROUP_CONCAT(DISTINCT v.field) AS fields,
                   wm.level AS mastery, wm.updated_at
            FROM vocabulary v
            LEFT JOIN word_mastery wm ON wm.lemma = v.lemma
            GROUP BY v.lemma
            """
        ).fetchall()
        personal_rows = conn.execute(
            """
            SELECT p.lemma, p.word, 0 AS frequency, 1 AS importance,
                   CASE WHEN p.article_id IS NULL THEN 0 ELSE 1 END AS article_count,
                   p.example_sentence, '个人标记' AS categories,
                   'personal' AS fields, wm.level AS mastery, wm.updated_at
            FROM personal_vocabulary p
            JOIN word_mastery wm ON wm.lemma = p.lemma
            """
        ).fetchall()

    by_lemma = {row["lemma"]: dict(row) for row in rows}
    for row in personal_rows:
        by_lemma.setdefault(row["lemma"], dict(row))

    query = q.strip().lower()
    items: list[dict[str, Any]] = []
    valid_mastery = {"learning", "familiar", "mastered"}
    for item in by_lemma.values():
        tier = vocabulary_tier(item["lemma"])
        categories = str(item.get("categories") or "")
        special = "polysemy" in categories or "domain terminology" in categories
        if tier == "high_school" and "polysemy" not in categories and not item["mastery"]:
            continue
        if tier == "rare" and not special and not item["mastery"]:
            continue
        if query and query not in item["lemma"].lower() and query not in item["word"].lower():
            continue
        if mastery == "unmarked" and item["mastery"] is not None:
            continue
        if mastery in valid_mastery and item["mastery"] != mastery:
            continue

        item["tier"] = tier
        item["importance"] = tier_importance(tier) or item["importance"]
        items.append(item)

    items.sort(
        key=lambda item: (
            -int(item["importance"]),
            -int(item["article_count"]),
            -int(item["frequency"]),
            item["lemma"],
        )
    )
    total = len(items)
    items = items[offset : offset + limit]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.put("/api/vocabulary/{lemma}/mastery")
def save_mastery(lemma: str, payload: MasteryUpdate) -> dict[str, Any]:
    normalized = re.sub(r"[^a-zA-Z '-]", "", lemma).strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="词条格式不正确")
    db = get_db()
    article = db.get_article(payload.article_id) if payload.article_id else None
    source_word = re.sub(r"[^a-zA-Z '-]", "", payload.word).strip().lower() or normalized
    example = word_context(article.text, source_word) if article else ""
    with db.connect() as conn:
        if payload.level is None:
            conn.execute("DELETE FROM word_mastery WHERE lemma = ?", (normalized,))
            conn.execute("DELETE FROM personal_vocabulary WHERE lemma = ?", (normalized,))
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
            conn.execute(
                """
                INSERT INTO personal_vocabulary(
                    lemma, word, article_id, example_sentence, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(lemma) DO UPDATE SET
                    word=excluded.word,
                    article_id=COALESCE(excluded.article_id, personal_vocabulary.article_id),
                    example_sentence=CASE
                        WHEN excluded.example_sentence = ''
                        THEN personal_vocabulary.example_sentence
                        ELSE excluded.example_sentence
                    END
                """,
                (
                    normalized,
                    source_word,
                    article.normalized_id() if article else None,
                    example,
                    now_iso(),
                ),
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
        item["mode"] = (
            "LLM + NLP"
            if is_complete_analysis(llm)
            else ("LLM 未解析 · NLP" if llm else "LOCAL NLP")
        )
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
        payload.api_key.strip() if payload.api_key and payload.api_key.strip() else current.api_key
    )
    analyzer = LLMAnalyzer.from_config(payload.model.strip(), api_key, payload.base_url.strip())
    if not analyzer.enabled():
        raise HTTPException(status_code=400, detail="请先填写 API Key 或本地模型地址")
    request = {
        "model": analyzer.model,
        "messages": [{"role": "user", "content": 'Return {"ok":true} only.'}],
        "temperature": 0,
        "max_tokens": 128,
    }
    try:
        if (analyzer.base_url or "").strip().endswith("/chat/completions"):
            content = post_chat_completion_raw(
                analyzer.base_url or "", analyzer.api_key or "", request, timeout=20
            )
        else:
            response = analyzer.client.chat.completions.create(**request)
            choices = getattr(response, "choices", None) or []
            content = message_text(choices[0].message) if choices else ""
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

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import AnalysisResult, Article

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    field TEXT NOT NULL DEFAULT 'unknown',
    text TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analyses (
    article_id TEXT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    field_scores_json TEXT NOT NULL,
    difficulty REAL NOT NULL,
    exam_value REAL NOT NULL,
    llm_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vocabulary (
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    word TEXT NOT NULL,
    lemma TEXT NOT NULL,
    field TEXT NOT NULL,
    category TEXT NOT NULL,
    frequency INTEGER NOT NULL,
    importance INTEGER NOT NULL,
    example_sentence TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(article_id, word, category)
);

CREATE TABLE IF NOT EXISTS collocations (
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    expression TEXT NOT NULL,
    type TEXT NOT NULL,
    frequency INTEGER NOT NULL,
    importance INTEGER NOT NULL,
    meaning TEXT NOT NULL DEFAULT '',
    example_sentence TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(article_id, expression)
);

CREATE TABLE IF NOT EXISTS polysemy (
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    word TEXT NOT NULL,
    ordinary_meaning TEXT NOT NULL,
    contextual_meaning TEXT NOT NULL,
    sentence TEXT NOT NULL,
    exam_risk TEXT NOT NULL,
    PRIMARY KEY(article_id, word)
);

CREATE TABLE IF NOT EXISTS sentence_patterns (
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    function TEXT NOT NULL,
    sentence TEXT NOT NULL,
    importance INTEGER NOT NULL
);
"""


class CorpusDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_column(conn, "vocabulary", "example_sentence", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "collocations", "meaning", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(
                conn, "collocations", "example_sentence", "TEXT NOT NULL DEFAULT ''"
            )

    def upsert_article(self, article: Article) -> str:
        article_id = article.normalized_id()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO articles (
                    id, title, source, url, published_at, field, text, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    source=excluded.source,
                    url=excluded.url,
                    published_at=excluded.published_at,
                    field=excluded.field,
                    text=excluded.text,
                    metadata_json=excluded.metadata_json
                """,
                (
                    article_id,
                    article.title,
                    article.source,
                    article.url,
                    article.published_at,
                    article.field,
                    article.text,
                    json.dumps(article.metadata, ensure_ascii=False),
                    article.created_at,
                ),
            )
        return article_id

    def list_articles(self) -> list[Article]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM articles ORDER BY created_at, id").fetchall()
        return [self._row_to_article(row) for row in rows]

    def get_article(self, article_id: str) -> Article | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return self._row_to_article(row) if row else None

    def llm_analyzed_article_ids(self) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT article_id
                FROM analyses
                WHERE llm_json IS NOT NULL AND llm_json != '{}'
                """
            ).fetchall()
        return {row["article_id"] for row in rows}

    def article_exists_by_url(self, url: str) -> bool:
        if not url:
            return False
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM articles WHERE url = ? LIMIT 1", (url,)).fetchone()
        return row is not None

    def save_analysis(self, result: AnalysisResult) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM analyses WHERE article_id = ?", (result.article_id,))
            conn.execute("DELETE FROM vocabulary WHERE article_id = ?", (result.article_id,))
            conn.execute("DELETE FROM collocations WHERE article_id = ?", (result.article_id,))
            conn.execute("DELETE FROM polysemy WHERE article_id = ?", (result.article_id,))
            conn.execute("DELETE FROM sentence_patterns WHERE article_id = ?", (result.article_id,))

            conn.execute(
                """
                INSERT INTO analyses (
                    article_id, field, field_scores_json, difficulty,
                    exam_value, llm_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.article_id,
                    result.field,
                    json.dumps(result.field_scores, ensure_ascii=False),
                    result.difficulty,
                    result.exam_value,
                    json.dumps(result.llm, ensure_ascii=False),
                    result.created_at,
                ),
            )
            conn.executemany(
                """
                INSERT INTO vocabulary (
                    article_id, word, lemma, field, category, frequency,
                    importance, example_sentence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _unique_vocabulary_rows(result.article_id, result.word_frequencies, result.llm),
            )
            conn.executemany(
                """
                INSERT INTO collocations (
                    article_id, expression, type, frequency,
                    importance, meaning, example_sentence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                _unique_collocation_rows(result.article_id, result.collocations, result.llm),
            )
            conn.executemany(
                """
                INSERT INTO sentence_patterns (article_id, type, function, sentence, importance)
                VALUES (?, ?, ?, ?, ?)
                """,
                _unique_sentence_pattern_rows(
                    result.article_id, result.sentence_patterns, result.llm
                ),
            )
            conn.executemany(
                """
                INSERT INTO polysemy (
                    article_id, word, ordinary_meaning, contextual_meaning, sentence, exam_risk
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.article_id,
                        item["word"],
                        item["ordinary_meaning"],
                        item["contextual_meaning"],
                        item["sentence"],
                        item["exam_risk"],
                    )
                    for item in result.polysemy
                ],
            )

    def fetch_report_rows(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            articles = conn.execute(
                """
                SELECT a.*, an.field AS analysis_field, an.field_scores_json, an.difficulty,
                       an.exam_value, an.llm_json, an.created_at AS analyzed_at
                FROM articles a
                LEFT JOIN analyses an ON an.article_id = a.id
                ORDER BY a.created_at, a.id
                """
            ).fetchall()
            rows = []
            for article in articles:
                article_id = article["id"]
                rows.append(
                    {
                        "article": dict(article),
                        "vocabulary": self._fetch_many(conn, "vocabulary", article_id),
                        "collocations": self._fetch_many(conn, "collocations", article_id),
                        "polysemy": self._fetch_many(conn, "polysemy", article_id),
                        "sentence_patterns": self._fetch_many(
                            conn, "sentence_patterns", article_id
                        ),
                    }
                )
            return rows

    def fetch_llm_rows(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT a.id AS article_id,
                       a.source,
                       a.url,
                       a.published_at,
                       a.metadata_json,
                       an.llm_json
                FROM articles a
                JOIN analyses an ON an.article_id = a.id
                WHERE an.llm_json IS NOT NULL AND an.llm_json != '{}'
                ORDER BY a.created_at, a.id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def aggregate_vocabulary(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT field, word, lemma, category,
                       SUM(frequency) AS frequency,
                       MAX(importance) AS importance,
                       COUNT(DISTINCT article_id) AS article_count,
                       MIN(example_sentence) AS example_sentence,
                       GROUP_CONCAT(DISTINCT source) AS sources,
                       MIN(citation) AS citation
                FROM (
                    SELECT v.*, a.source,
                           json_extract(a.metadata_json, '$.citation') AS citation
                    FROM vocabulary v
                    JOIN articles a ON a.id = v.article_id
                )
                GROUP BY field, word, lemma, category
                ORDER BY field, frequency DESC, word
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def aggregate_collocations(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT expression, type, SUM(frequency) AS frequency,
                       MAX(importance) AS importance,
                       COUNT(DISTINCT article_id) AS article_count,
                       MIN(meaning) AS meaning,
                       MIN(example_sentence) AS example_sentence,
                       GROUP_CONCAT(DISTINCT source) AS sources,
                       MIN(citation) AS citation
                FROM (
                    SELECT c.*, a.source,
                           json_extract(a.metadata_json, '$.citation') AS citation
                    FROM collocations c
                    JOIN articles a ON a.id = c.article_id
                )
                GROUP BY expression, type
                ORDER BY frequency DESC, expression
                """
            ).fetchall()
        items = [dict(row) for row in rows]
        items.sort(
            key=lambda item: (
                _collocation_priority(item),
                item["frequency"],
                item["importance"],
            ),
            reverse=True,
        )
        return items

    def aggregate_polysemy(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT p.word, p.ordinary_meaning, p.contextual_meaning,
                       COUNT(DISTINCT p.article_id) AS article_count,
                       MIN(p.sentence) AS example_sentence,
                       GROUP_CONCAT(DISTINCT a.source) AS sources
                FROM polysemy p
                JOIN articles a ON a.id = p.article_id
                GROUP BY p.word, p.ordinary_meaning, p.contextual_meaning
                ORDER BY article_count DESC, p.word
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def aggregate_sentence_patterns(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT type, function,
                       COUNT(*) AS frequency,
                       MAX(importance) AS importance,
                       MIN(sentence) AS example_sentence
                FROM sentence_patterns
                GROUP BY type, function
                ORDER BY frequency DESC, type
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_articles(self, article_ids: list[str]) -> int:
        if not article_ids:
            return 0
        with self.connect() as conn:
            conn.executemany("DELETE FROM articles WHERE id = ?", [(item,) for item in article_ids])
        return len(article_ids)

    def low_quality_article_ids(
        self, min_exam_value: float, min_difficulty: float, min_quality_score: float = 0.0
    ) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.metadata_json, an.exam_value, an.difficulty
                FROM articles a
                LEFT JOIN analyses an ON an.article_id = a.id
                WHERE an.article_id IS NOT NULL
                """
            ).fetchall()
        article_ids = []
        for row in rows:
            metadata = json.loads(row["metadata_json"] or "{}")
            quality_score = float(metadata.get("quality_score", 10.0))
            if (
                row["exam_value"] < min_exam_value
                or row["difficulty"] < min_difficulty
                or quality_score < min_quality_score
            ):
                article_ids.append(row["id"])
        return article_ids

    @staticmethod
    def _fetch_many(conn: sqlite3.Connection, table: str, article_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(f"SELECT * FROM {table} WHERE article_id = ?", (article_id,)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    @staticmethod
    def _row_to_article(row: sqlite3.Row) -> Article:
        return Article(
            id=row["id"],
            title=row["title"],
            source=row["source"],
            url=row["url"],
            published_at=row["published_at"],
            field=row["field"],
            text=row["text"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    @staticmethod
    def _extract_llm_vocabulary(llm: dict[str, Any]) -> list[dict[str, Any]]:
        payload = _normalize_llm_payload(llm)
        rows: list[dict[str, Any]] = []
        for item in payload.get("vocabulary", []):
            if not isinstance(item, dict):
                continue
            lemma = str(item.get("lemma", "")).strip().lower()
            if not lemma:
                continue
            importance = _llm_importance(item.get("exam_importance"))
            category = _llm_category(item.get("exam_importance"), lemma)
            if importance < 3 and category != "polysemy":
                continue
            rows.append(
                {
                    "word": lemma,
                    "lemma": lemma,
                    "field": _llm_field(item),
                    "category": category,
                    "frequency": _llm_frequency(item.get("exam_importance")),
                    "importance": importance,
                    "example_sentence": str(item.get("meaning_in_context", "")),
                }
            )
        return rows

    @staticmethod
    def _extract_llm_collocations(llm: dict[str, Any]) -> list[dict[str, Any]]:
        payload = _normalize_llm_payload(llm)
        rows: list[dict[str, Any]] = []
        for item in payload.get("vocabulary", []):
            if not isinstance(item, dict):
                continue
            lemma = str(item.get("lemma", "")).strip().lower()
            if not lemma or " " not in lemma:
                continue
            importance = _llm_importance(item.get("exam_importance"))
            if importance < 3:
                continue
            rows.append(
                {
                    "expression": lemma,
                    "type": "llm vocabulary phrase",
                    "frequency": _llm_frequency(item.get("exam_importance")),
                    "importance": importance,
                    "meaning": str(item.get("meaning_in_context", "")),
                    "example_sentence": str(item.get("meaning_in_context", "")),
                }
            )
        return rows

    @staticmethod
    def _extract_llm_sentence_patterns(llm: dict[str, Any]) -> list[dict[str, Any]]:
        payload = _normalize_llm_payload(llm)
        rows: list[dict[str, Any]] = []
        for item in payload.get("rhetoric", []):
            if not isinstance(item, dict):
                continue
            sentence = str(item.get("original_sentence", "")).strip()
            explanation = str(item.get("explanation", "")).strip()
            if not sentence or not explanation:
                continue
            rows.append(
                {
                    "type": str(item.get("type", "llm rhetorical pattern")),
                    "function": explanation,
                    "sentence": sentence,
                    "importance": 4,
                }
            )
        return rows


def _normalize_llm_payload(llm: dict[str, Any]) -> dict[str, Any]:
    if not llm:
        return {}
    if isinstance(llm, str):
        try:
            parsed = json.loads(llm)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return llm if isinstance(llm, dict) else {}


def _llm_importance(value: Any) -> int:
    text = str(value or "").lower()
    if text in {"high", "postgraduate"}:
        return 5
    if text in {"medium", "cet-6", "c1"}:
        return 4
    if text:
        return 3
    return 0


def _llm_category(value: Any, lemma: str) -> str:
    text = str(value or "").lower()
    if "polysemy" in text:
        return "polysemy"
    if "idiom" in text or "expression" in text:
        return "phrase"
    if "legal" in text or "political" in text:
        return "domain terminology"
    if "academic" in text:
        return "academic/general"
    return "academic/general"


def _llm_field(item: dict[str, Any]) -> str:
    explicit = str(
        item.get("domain") or item.get("field") or item.get("topic") or item.get("subdomain") or ""
    ).lower()
    lemma = str(item.get("lemma") or "").lower()
    meaning = str(item.get("meaning_in_context") or item.get("common_meaning") or "").lower()
    text = " ".join(
        [
            explicit,
            str(item.get("estimated_level") or ""),
            str(item.get("exam_importance") or ""),
            lemma,
            meaning,
        ]
    ).lower()
    if "law" in text or "political" in text:
        return "law"
    if "econom" in text or "market" in text:
        return "economics"
    if "environment" in text:
        return "environment"
    if "education" in text:
        return "education"
    if "psych" in text:
        return "psychology"
    if "soc" in text:
        return "sociology"
    if any(term in text for term in ["health", "medical", "clinical", "patient", "disease"]):
        return "health"
    if any(
        term in text for term in ["technology", "digital", "algorithm", "ai", "data", "platform"]
    ):
        return "technology"
    if "science" in text or "research" in text or "postgraduate" in text:
        return "science"
    return "unknown"


def _llm_frequency(value: Any) -> int:
    text = str(value or "").lower()
    if text == "high":
        return 5
    if text == "medium":
        return 3
    if text == "low":
        return 1
    if text == "postgraduate":
        return 4
    if text == "cet-6":
        return 3
    return 2


def _shorten_sentence(sentence: str, limit: int = 60) -> str:
    text = sentence.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _unique_vocabulary_rows(
    article_id: str, base_rows: list[dict[str, Any]], llm: dict[str, Any]
) -> list[tuple[Any, ...]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in base_rows:
        merged[(item["lemma"], item["category"])] = item
    for item in CorpusDB._extract_llm_vocabulary(llm):
        merged.setdefault((item["lemma"], item["category"]), item)
    return [
        (
            article_id,
            item["word"],
            item["lemma"],
            item["field"],
            item["category"],
            item["frequency"],
            item["importance"],
            item.get("example_sentence", ""),
        )
        for item in merged.values()
    ]


def _unique_collocation_rows(
    article_id: str, base_rows: list[dict[str, Any]], llm: dict[str, Any]
) -> list[tuple[Any, ...]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in base_rows:
        merged[item["expression"]] = item
    for item in CorpusDB._extract_llm_collocations(llm):
        merged.setdefault(item["expression"], item)
    return [
        (
            article_id,
            item["expression"],
            item["type"],
            item["frequency"],
            item["importance"],
            item.get("meaning", ""),
            item.get("example_sentence", ""),
        )
        for item in merged.values()
    ]


def _unique_sentence_pattern_rows(
    article_id: str, base_rows: list[dict[str, Any]], llm: dict[str, Any]
) -> list[tuple[Any, ...]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in base_rows:
        merged[(item["type"], item["function"], item["sentence"])] = item
    for item in CorpusDB._extract_llm_sentence_patterns(llm):
        merged.setdefault((item["type"], item["function"], item["sentence"]), item)
    return [
        (
            article_id,
            item["type"],
            item["function"],
            item["sentence"],
            item["importance"],
        )
        for item in merged.values()
    ]


def ensure_db(path: str | Path) -> CorpusDB:
    db = CorpusDB(path)
    db.init()
    return db


def upsert_articles(db: CorpusDB, articles: Iterable[Article]) -> list[str]:
    return [db.upsert_article(article) for article in articles]


def _collocation_priority(item: dict[str, Any]) -> tuple[int, int, int]:
    expression = str(item.get("expression", ""))
    if item.get("meaning"):
        return (3, len(expression.split()), len(expression))
    if item.get("type") in {
        "legal/political expression",
        "stance expression",
        "argument expression",
        "academic expression",
        "causality expression",
        "polysemy phrase",
    }:
        return (3, len(expression.split()), len(expression))
    if item.get("type") == "3-gram":
        return (2, len(expression.split()), len(expression))
    if item.get("type") == "2-gram":
        return (
            1 if float(item.get("frequency", 0)) >= 4 else 0,
            len(expression.split()),
            len(expression),
        )
    return (1, len(expression.split()), len(expression))

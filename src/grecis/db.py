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
                [
                    (
                        result.article_id,
                        item["word"],
                        item["lemma"],
                        item["field"],
                        item["category"],
                        item["frequency"],
                        item["importance"],
                        item.get("example_sentence", ""),
                    )
                    for item in result.word_frequencies
                ],
            )
            conn.executemany(
                """
                INSERT INTO collocations (
                    article_id, expression, type, frequency,
                    importance, meaning, example_sentence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.article_id,
                        item["expression"],
                        item["type"],
                        item["frequency"],
                        item["importance"],
                        item.get("meaning", ""),
                        item.get("example_sentence", ""),
                    )
                    for item in result.collocations
                ],
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
            conn.executemany(
                """
                INSERT INTO sentence_patterns (article_id, type, function, sentence, importance)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.article_id,
                        item["type"],
                        item["function"],
                        item["sentence"],
                        item["importance"],
                    )
                    for item in result.sentence_patterns
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

    def aggregate_vocabulary(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT field, word, lemma, category,
                       SUM(frequency) AS frequency,
                       MAX(importance) AS importance,
                       COUNT(DISTINCT article_id) AS article_count,
                       MIN(example_sentence) AS example_sentence
                FROM vocabulary
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
                       MIN(example_sentence) AS example_sentence
                FROM collocations
                GROUP BY expression, type
                ORDER BY frequency DESC, expression
                """
            ).fetchall()
        return [dict(row) for row in rows]

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


def ensure_db(path: str | Path) -> CorpusDB:
    db = CorpusDB(path)
    db.init()
    return db


def upsert_articles(db: CorpusDB, articles: Iterable[Article]) -> list[str]:
    return [db.upsert_article(article) for article in articles]

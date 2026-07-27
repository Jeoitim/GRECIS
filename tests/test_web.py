from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

from grecis import web
from grecis.config import AppConfig, CrawlerConfig, LLMConfig, SourceConfig
from grecis.db import SCHEMA, CorpusDB, ensure_db
from grecis.models import Article
from grecis.nlp import analyze_article
from grecis.wordlists import (
    common_american_20k,
    gaokao_words,
    gre_words,
    kaoyan_words,
    vocabulary_tier,
)


def sample_db(tmp_path):
    db = ensure_db(tmp_path / "corpus.sqlite")
    article = Article(
        title="A Dynamic Corpus",
        source="test",
        text=(
            "Reliable reading requires sustained attention. "
            "A careful reader compares evidence and revises judgment. "
            "Metacognition can improve comprehension."
        ),
    )
    article_id = db.upsert_article(article)
    db.save_analysis(analyze_article(article))
    return db, article_id


def test_corpus_api_reads_sqlite_and_persists_mastery(monkeypatch, tmp_path):
    db, article_id = sample_db(tmp_path)
    monkeypatch.setattr(web, "get_db", lambda: db)
    client = TestClient(web.app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["counts"]["articles"] == 1

    articles = client.get("/api/articles")
    assert articles.status_code == 200
    assert articles.json()["total"] == 1
    assert articles.json()["items"][0]["title"] == "A Dynamic Corpus"

    detail = client.get(f"/api/articles/{article_id}")
    assert detail.status_code == 200
    assert detail.json()["text"].startswith("Reliable reading")

    saved = client.put("/api/vocabulary/sustain/mastery", json={"level": "learning"})
    assert saved.status_code == 200
    assert saved.json()["level"] == "learning"

    vocabulary = client.get("/api/vocabulary?mastery=learning")
    assert vocabulary.status_code == 200
    assert vocabulary.json()["items"]
    assert all(item["mastery"] == "learning" for item in vocabulary.json()["items"])


def test_article_highlights_use_all_text_tokens_and_disjoint_tiers() -> None:
    high_school = next(iter(gaokao_words()))
    core = next(word for word in kaoyan_words() if vocabulary_tier(word) == "core")
    key = next(word for word in common_american_20k() if vocabulary_tier(word) == "key")
    gre = next(word for word in gre_words() if vocabulary_tier(word) == "gre")
    rare = "paleobiogeographically"
    text = f"{high_school} {core} {key} {gre} {rare}"

    highlights = web.article_vocabulary_highlights(
        text,
        [
            {
                "word": rare,
                "lemma": rare,
                "category": "domain terminology",
            }
        ],
    )
    tiers = {item["word"]: item["tier"] for item in highlights}

    assert high_school not in tiers
    assert tiers[core] == "core"
    assert tiers[key] == "key"
    assert tiers[gre] == "gre"
    assert tiers[rare] == "specialized"


def test_high_school_polysemy_is_highlighted_only_for_that_article() -> None:
    ordinary = web.article_vocabulary_highlights("The school opens early.", [])
    contextual = web.article_vocabulary_highlights(
        "This school of thought influenced the debate.",
        [
            {
                "word": "school",
                "lemma": "school",
                "category": "polysemy",
            }
        ],
    )

    assert "school" not in {item["word"] for item in ordinary}
    assert {
        "word": "school",
        "lemma": "school",
        "tier": "specialized",
    } in contextual


def test_llm_cannot_add_high_school_words_to_review_vocabulary() -> None:
    rejected = CorpusDB._extract_llm_vocabulary(
        {
            "vocabulary": [
                {
                    "lemma": "school",
                    "exam_importance": "high",
                    "category": "academic vocabulary",
                    "meaning_in_context": "学校",
                    "source_sentence": "The school opens early.",
                }
            ]
        }
    )
    accepted = CorpusDB._extract_llm_vocabulary(
        {
            "vocabulary": [
                {
                    "lemma": "school",
                    "exam_importance": "high",
                    "category": "polysemy",
                    "meaning_in_context": "学派",
                    "source_sentence": "This school of thought influenced the debate.",
                }
            ]
        }
    )

    assert rejected == []
    assert accepted[0]["category"] == "polysemy"


def test_existing_database_migration_removes_high_school_and_caps_articles(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite"
    db = CorpusDB(path)
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            INSERT INTO articles(
                id, title, source, url, published_at, field, text, metadata_json, created_at
            ) VALUES ('legacy', 'Legacy', 'test', '', '', 'unknown', 'text', '{}', '')
            """
        )
        high_school = [word for word in gaokao_words() if word != "school"][:4]
        eligible = [word for word in kaoyan_words() if word not in gaokao_words()][:45]
        conn.executemany(
            """
            INSERT INTO vocabulary(
                article_id, word, lemma, field, category, frequency, importance
            ) VALUES ('legacy', ?, ?, 'unknown', 'academic/general', 1, 5)
            """,
            [(word, word) for word in high_school + eligible],
        )
        conn.execute(
            """
            INSERT INTO vocabulary(
                article_id, word, lemma, field, category, frequency, importance,
                example_sentence
            ) VALUES (
                'legacy', 'school', 'school', 'unknown', 'polysemy', 1, 1,
                'This school of thought influenced the debate.'
            )
            """
        )
        conn.execute("DELETE FROM app_metadata WHERE key = 'vocabulary_selection_v3'")

    db.init()
    with db.connect() as conn:
        rows = conn.execute("SELECT lemma FROM vocabulary WHERE article_id = 'legacy'").fetchall()

    assert len(rows) == 40
    assert "school" in {row["lemma"] for row in rows}
    assert all(
        vocabulary_tier(row["lemma"]) != "high_school" or row["lemma"] == "school" for row in rows
    )


def test_settings_save_preserves_existing_key(monkeypatch, tmp_path):
    config_path = tmp_path / "local.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "database": {"path": str(tmp_path / "corpus.sqlite")},
                "llm": {
                    "model": "old-model",
                    "base_url": "http://localhost:11434/v1",
                    "api_key": "existing-secret",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web, "LOCAL_CONFIG_PATH", config_path)
    client = TestClient(web.app)

    response = client.put(
        "/api/settings",
        json={
            "model": "new-model",
            "base_url": "http://localhost:11434/v1",
            "api_key": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["model"] == "new-model"
    assert response.json()["api_key_set"] is True
    stored = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert stored["llm"]["api_key"] == "existing-secret"


def test_connection_test_accepts_reasoning_model_response(monkeypatch):
    calls = []

    class FakeMessage:
        content = None
        reasoning_content = '{"ok":true}'

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            choice = type("Choice", (), {"message": FakeMessage()})()
            return type("Response", (), {"choices": [choice]})()

    fake_client = type(
        "Client",
        (),
        {"chat": type("Chat", (), {"completions": FakeCompletions()})()},
    )()
    monkeypatch.setattr(web.LLMAnalyzer, "client", fake_client)
    monkeypatch.setattr(
        web,
        "get_config",
        lambda: AppConfig(llm=LLMConfig(model="m", api_key="key")),
    )
    client = TestClient(web.app)

    response = client.post(
        "/api/settings/test",
        json={"model": "m", "base_url": "https://api.example.com/v1", "api_key": "key"},
    )

    assert response.status_code == 200
    assert calls[0]["max_tokens"] == 128


def test_invalid_llm_record_is_not_reported_as_success(monkeypatch, tmp_path):
    db, article_id = sample_db(tmp_path)
    article = db.get_article(article_id)
    assert article is not None
    db.save_analysis(
        analyze_article(
            article,
            llm_payload={"raw": "truncated", "_meta": {"model": "m"}},
        )
    )
    monkeypatch.setattr(web, "get_db", lambda: db)
    client = TestClient(web.app)

    detail = client.get(f"/api/articles/{article_id}").json()
    history = client.get("/api/analysis-history").json()["items"]

    assert detail["digest"]["status"] == "invalid"
    assert "返回不完整" in detail["digest"]["insight"]
    assert history[0]["mode"] == "LLM 未解析 · NLP"


def test_recent_articles_can_be_cleared_without_deleting_corpus(monkeypatch, tmp_path):
    db, article_id = sample_db(tmp_path)
    monkeypatch.setattr(web, "get_db", lambda: db)
    client = TestClient(web.app)

    saved = client.put(f"/api/articles/{article_id}/progress", json={"progress": 24})
    assert saved.status_code == 200

    recent = client.get("/api/recent-articles")
    assert recent.status_code == 200
    assert recent.json()["items"][0]["id"] == article_id
    assert recent.json()["items"][0]["progress"] == 24

    cleared = client.delete("/api/reading-progress")
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 1
    assert client.get("/api/recent-articles").json()["items"] == []
    assert client.get("/api/articles").json()["total"] == 1


def test_personal_word_mark_is_listed_and_shared_with_article(monkeypatch, tmp_path):
    db, article_id = sample_db(tmp_path)
    monkeypatch.setattr(web, "get_db", lambda: db)
    client = TestClient(web.app)

    marked = client.put(
        "/api/vocabulary/metacognition/mastery",
        json={"level": "learning", "article_id": article_id, "word": "metacognition"},
    )
    assert marked.status_code == 200

    vocabulary = client.get("/api/vocabulary?q=metacognition")
    assert vocabulary.status_code == 200
    assert vocabulary.json()["items"][0]["lemma"] == "metacognition"
    assert vocabulary.json()["items"][0]["mastery"] == "learning"

    detail = client.get(f"/api/articles/{article_id}")
    assert {"lemma": "metacognition", "level": "learning"} in detail.json()["mastery_words"]

    removed = client.put("/api/vocabulary/metacognition/mastery", json={"level": None})
    assert removed.status_code == 200
    assert client.get("/api/vocabulary?q=metacognition").json()["items"] == []


def test_crawler_api_exposes_options_and_imports_analyzed_articles(monkeypatch, tmp_path):
    db, _ = sample_db(tmp_path)
    config = AppConfig(
        crawler=CrawlerConfig(delay_seconds=0, min_text_chars=200),
        sources=[
            SourceConfig(
                name="Example News",
                enabled=True,
                field_hint="science",
                category="science",
                feed_urls=["https://example.com/rss"],
            )
        ],
    )

    def fake_articles(source, crawler, *, existing_urls):
        assert source.name == "Example News"
        assert crawler.max_articles_per_source == 2
        assert crawler.delay_seconds == 0
        yield Article(
            title="Automatically fetched",
            source=source.name,
            url="https://example.com/automatic",
            text=" ".join(["Researchers examine institutions and environmental regulation."] * 80),
        )

    monkeypatch.setattr(web, "get_db", lambda: db)
    monkeypatch.setattr(web, "get_config", lambda: config)
    monkeypatch.setattr(web, "iter_fetch_source_articles", fake_articles)
    client = TestClient(web.app)

    options = client.get("/api/crawler/options")
    assert options.status_code == 200
    assert options.json()["sources"][0]["name"] == "Example News"

    response = client.post(
        "/api/crawler/fetch",
        json={
            "source": "Example News",
            "limit": 2,
            "delay_seconds": 0,
            "request_timeout_seconds": 10,
            "min_text_chars": 200,
            "min_quality_score": 0,
            "use_llm": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert response.json()["items"][0]["title"] == "Automatically fetched"
    assert client.get("/api/articles").json()["total"] == 2

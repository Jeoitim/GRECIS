from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

from grecis import web
from grecis.db import ensure_db
from grecis.models import Article
from grecis.nlp import analyze_article


def sample_db(tmp_path):
    db = ensure_db(tmp_path / "corpus.sqlite")
    article = Article(
        title="A Dynamic Corpus",
        source="test",
        text=(
            "Reliable reading requires sustained attention. "
            "A careful reader compares evidence and revises judgment."
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

    saved = client.put("/api/vocabulary/attention/mastery", json={"level": "learning"})
    assert saved.status_code == 200
    assert saved.json()["level"] == "learning"

    vocabulary = client.get("/api/vocabulary?mastery=learning")
    assert vocabulary.status_code == 200
    assert vocabulary.json()["items"]
    assert all(item["mastery"] == "learning" for item in vocabulary.json()["items"])


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

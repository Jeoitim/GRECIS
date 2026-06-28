from grecis.config import app_config_from_mapping, load_config


def test_app_config_from_mapping_loads_local_cleartext_settings() -> None:
    config = app_config_from_mapping(
        {
            "database": {"path": "data/custom.sqlite"},
            "llm": {"model": "test-model", "api_key": "plain-key", "base_url": "http://x/v1"},
            "crawler": {"max_articles_per_source": 2},
            "sources": [
                {
                    "name": "Example",
                    "enabled": True,
                    "field_hint": "science",
                    "feed_urls": ["https://example.com/rss"],
                }
            ],
        }
    )
    assert config.database.path == "data/custom.sqlite"
    assert config.llm.api_key == "plain-key"
    assert config.llm.base_url == "http://x/v1"
    assert config.crawler.max_articles_per_source == 2
    assert config.sources[0].name == "Example"


def test_load_config_merges_sources_with_local_cleartext_overrides(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(
        """
database:
  path: data/base.sqlite
sources:
  - name: Example
    archive_urls: [https://example.com/archive]
""",
        encoding="utf-8",
    )
    local = config_dir / "local.yaml"
    local.write_text(
        """
database:
  path: data/local.sqlite
llm:
  api_key: plain-local-key
sources: []
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config(local)

    assert config.database.path == "data/local.sqlite"
    assert config.llm.api_key == "plain-local-key"
    assert config.sources[0].name == "Example"
    assert config.sources[0].archive_urls == ["https://example.com/archive"]

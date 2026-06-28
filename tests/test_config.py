from grecis.config import app_config_from_mapping


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

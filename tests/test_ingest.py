from grecis.config import CrawlerConfig, SourceConfig
from grecis.ingest import fetch_source_articles


def test_fetch_source_articles_keeps_metadata_json_serializable(monkeypatch) -> None:
    source = SourceConfig(name="Example", article_urls=["https://example.com/a"])
    crawler = CrawlerConfig(
        max_articles_per_source=1,
        min_text_chars=1,
        delay_seconds=0,
        min_quality_score=0,
    )

    def fake_fetch_url(url, source, *, field_hint, crawler, metadata):
        from grecis.models import Article

        text = " ".join(
            ["This policy study examines education and society because institutions matter."] * 120
        )
        return Article(title="A", source=source, url=url, text=text, metadata=metadata)

    monkeypatch.setattr("grecis.ingest.fetch_url", fake_fetch_url)
    articles = fetch_source_articles(source, crawler)
    assert articles[0].metadata["feed_url"] == ""
    assert articles[0].metadata["quality_keep"] is True

from grecis.config import CrawlerConfig, SourceConfig
from grecis.ingest import discover_page_entries, fetch_source_articles, iter_fetch_source_articles


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


def test_iter_fetch_source_articles_normalizes_tracking_query_urls(monkeypatch) -> None:
    source = SourceConfig(name="Example", article_urls=["https://example.com/a?utm_source=feed"])
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

    articles = list(
        iter_fetch_source_articles(source, crawler, existing_urls={"https://example.com/a"})
    )

    assert articles == []


def test_discover_page_entries_filters_archive_links(monkeypatch) -> None:
    source = SourceConfig(
        name="Example",
        archive_urls=["https://example.com/archive"],
        article_url_patterns=[r"example\.com/articles/[0-9]{4}/"],
    )
    crawler = CrawlerConfig(max_discovery_pages_per_source=1)

    class FakeResponse:
        text = """
        <html><body>
          <a href="/articles/2024/09/policy-analysis">Policy analysis</a>
          <a href="/about">About</a>
          <a href="https://other.example.net/articles/2024/nope">Other</a>
        </body></html>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, timeout, headers):
        assert url == "https://example.com/archive"
        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)

    entries = discover_page_entries(source, crawler, limit=10)

    assert [entry["url"] for entry in entries] == [
        "https://example.com/articles/2024/09/policy-analysis"
    ]
    assert entries[0]["discovery_type"] == "archive_or_search"

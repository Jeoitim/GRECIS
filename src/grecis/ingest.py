from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import CrawlerConfig, SourceConfig
from .models import Article

WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    return WHITESPACE_RE.sub(" ", text).strip()


def load_jsonl(path: str | Path) -> list[Article]:
    articles: list[Article] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            payload: dict[str, Any] = json.loads(line)
            if "text" not in payload:
                raise ValueError(f"Line {line_number} has no 'text' field.")
            articles.append(
                Article(
                    id=payload.get("id"),
                    title=payload.get("title") or f"Untitled {line_number}",
                    source=payload.get("source", "jsonl"),
                    url=payload.get("url", ""),
                    published_at=payload.get("published_at", ""),
                    field=payload.get("field", "unknown"),
                    text=clean_text(payload["text"]),
                    metadata=payload.get("metadata", {}),
                )
            )
    return articles


def fetch_url(
    url: str,
    source: str = "web",
    *,
    field_hint: str = "unknown",
    crawler: CrawlerConfig | None = None,
    metadata: dict[str, Any] | None = None,
) -> Article:
    import requests

    crawler = crawler or CrawlerConfig()
    response = requests.get(
        url,
        timeout=crawler.request_timeout_seconds,
        headers={"User-Agent": crawler.user_agent},
    )
    response.raise_for_status()
    html = response.text

    article_metadata = dict(metadata or {})
    text = ""
    title = url
    try:
        import trafilatura

        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        if extracted:
            text = extracted
        extracted_metadata = trafilatura.extract_metadata(html)
        if extracted_metadata:
            if extracted_metadata.title:
                title = extracted_metadata.title
            article_metadata.update(
                {
                    "site_name": extracted_metadata.sitename or "",
                    "author": extracted_metadata.author or "",
                    "date": extracted_metadata.date or "",
                    "description": extracted_metadata.description or "",
                }
            )
    except Exception:
        text = ""

    if not text:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ")

    return Article(
        title=clean_text(title),
        source=source,
        url=url,
        field=field_hint,
        text=clean_text(text),
        metadata=article_metadata,
    )


def discover_feed_entries(source: SourceConfig, limit: int) -> list[dict[str, Any]]:
    import feedparser

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for feed_url in source.feed_urls:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries:
            url = getattr(entry, "link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            entries.append(
                {
                    "url": url,
                    "title": getattr(entry, "title", ""),
                    "published_at": getattr(entry, "published", "")
                    or getattr(entry, "updated", ""),
                    "feed_url": feed_url,
                }
            )
            if len(entries) >= limit:
                return entries
    return entries


def iter_source_targets(source: SourceConfig, limit: int) -> Iterable[dict[str, Any]]:
    yielded = 0
    for url in source.article_urls:
        if yielded >= limit:
            return
        yielded += 1
        yield {"url": url, "feed_url": "", "title": "", "published_at": ""}

    remaining = max(0, limit - yielded)
    yield from discover_feed_entries(source, remaining)


def fetch_source_articles(
    source: SourceConfig,
    crawler: CrawlerConfig,
    *,
    existing_urls: set[str] | None = None,
) -> list[Article]:
    if not source.enabled:
        return []

    existing_urls = existing_urls or set()
    articles: list[Article] = []
    for target in iter_source_targets(source, crawler.max_articles_per_source):
        url = target["url"]
        if url in existing_urls:
            continue
        try:
            article = fetch_url(
                url,
                source=source.name,
                field_hint=source.field_hint,
                crawler=crawler,
                metadata={
                    "feed_url": target.get("feed_url", ""),
                    "feed_title": target.get("title", ""),
                    "feed_published_at": target.get("published_at", ""),
                },
            )
        except Exception as exc:
            print(f"Skipped {url}: {exc}")
            continue

        if len(article.text) < crawler.min_text_chars:
            print(f"Skipped {url}: extracted text too short ({len(article.text)} chars)")
            continue

        if not article.published_at and target.get("published_at"):
            article.published_at = target["published_at"]
        if target.get("title") and article.title == url:
            article.title = clean_text(target["title"])
        articles.append(article)
        existing_urls.add(url)
        if crawler.delay_seconds > 0:
            time.sleep(crawler.delay_seconds)
    return articles

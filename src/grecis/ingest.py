from __future__ import annotations

import csv
import json
import re
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

from .config import CrawlerConfig, SourceConfig
from .models import Article
from .quality import score_article_quality

WHITESPACE_RE = re.compile(r"\s+")
NON_ARTICLE_EXTENSIONS = re.compile(
    r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|mp3|mp4|mov|zip|css|js)(?:$|\?)",
    re.I,
)


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


def load_exam_corpus(path: str | Path, source_name: str = "kaoyan_exam") -> list[Article]:
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        return _load_exam_jsonl(path, source_name)
    if path.suffix.lower() == ".csv":
        return _load_exam_csv(path, source_name)
    return _load_exam_txt(path, source_name)


def _exam_article_from_payload(payload: dict[str, Any], source_name: str, index: int) -> Article:
    text = payload.get("text") or payload.get("passage") or ""
    if not text:
        raise ValueError(f"Exam corpus item {index} has no text/passage field.")
    year = str(payload.get("year", ""))
    section = payload.get("section", "reading")
    title = payload.get("title") or f"Kaoyan {year} {section}".strip()
    exam_id = payload.get("id") or payload.get("exam_id") or f"kaoyan-{year}-{section}-{index}"
    return Article(
        id=str(exam_id),
        title=title,
        source=source_name,
        url=payload.get("url", ""),
        published_at=year,
        field=payload.get("field", "unknown"),
        text=clean_text(text),
        metadata={
            "corpus_type": "kaoyan_exam",
            "year": year,
            "section": section,
            "question_no": payload.get("question_no", ""),
            "original_source": payload.get("original_source", ""),
            "citation": payload.get("citation", ""),
        },
    )


def _load_exam_jsonl(path: Path, source_name: str) -> list[Article]:
    articles = []
    with path.open("r", encoding="utf-8") as file:
        for index, line in enumerate(file, start=1):
            if line.strip():
                articles.append(_exam_article_from_payload(json.loads(line), source_name, index))
    return articles


def _load_exam_csv(path: Path, source_name: str) -> list[Article]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [
            _exam_article_from_payload(row, source_name, index)
            for index, row in enumerate(csv.DictReader(file), start=1)
        ]


def _load_exam_txt(path: Path, source_name: str) -> list[Article]:
    text = path.read_text(encoding="utf-8")
    chunks = [chunk.strip() for chunk in re.split(r"\n-{3,}\n|\n#{2,}\s+", text) if chunk.strip()]
    return [
        Article(
            id=f"kaoyan-txt-{index}",
            title=f"Kaoyan Passage {index}",
            source=source_name,
            text=clean_text(chunk),
            metadata={"corpus_type": "kaoyan_exam", "citation": str(path)},
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


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
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:
            print(f"Skipped feed {feed_url}: {exc}")
            continue
        for entry in parsed.entries:
            url = _normalize_candidate_url(feed_url, getattr(entry, "link", ""))
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


def discover_page_entries(
    source: SourceConfig,
    crawler: CrawlerConfig,
    limit: int,
) -> list[dict[str, Any]]:
    import requests
    from bs4 import BeautifulSoup

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    discovery_urls = _iter_discovery_urls(source, crawler)
    for discovery_url in discovery_urls:
        if len(entries) >= limit:
            break
        try:
            response = requests.get(
                discovery_url,
                timeout=crawler.request_timeout_seconds,
                headers={"User-Agent": crawler.user_agent},
            )
            response.raise_for_status()
        except Exception as exc:
            print(f"Skipped discovery page {discovery_url}: {exc}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.find_all("a", href=True):
            url = _normalize_candidate_url(discovery_url, anchor["href"])
            if not url or url in seen or not _looks_like_source_article(url, source):
                continue
            seen.add(url)
            entries.append(
                {
                    "url": url,
                    "title": clean_text(anchor.get_text(" ")),
                    "published_at": "",
                    "feed_url": "",
                    "discovery_url": discovery_url,
                    "discovery_type": "archive_or_search",
                }
            )
            if len(entries) >= limit:
                break
    return entries


def iter_source_targets(source: SourceConfig, limit: int) -> Iterable[dict[str, Any]]:
    yield from iter_source_targets_with_crawler(source, CrawlerConfig(), limit)


def iter_source_targets_with_crawler(
    source: SourceConfig, crawler: CrawlerConfig, limit: int
) -> Iterable[dict[str, Any]]:
    yielded = 0
    seen: set[str] = set()
    for url in source.article_urls:
        if yielded >= limit:
            return
        normalized = _normalize_candidate_url(url, url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        yielded += 1
        yield {
            "url": normalized,
            "feed_url": "",
            "title": "",
            "published_at": "",
            "discovery_url": "",
            "discovery_type": "explicit",
        }

    remaining = max(0, limit - yielded)
    for target in discover_page_entries(source, crawler, remaining):
        if target["url"] in seen:
            continue
        seen.add(target["url"])
        yielded += 1
        yield target
        if yielded >= limit:
            return

    remaining = max(0, limit - yielded)
    for target in discover_feed_entries(source, remaining):
        if target["url"] in seen:
            continue
        target.setdefault("discovery_url", target.get("feed_url", ""))
        target.setdefault("discovery_type", "feed")
        seen.add(target["url"])
        yielded += 1
        yield target
        if yielded >= limit:
            return


def fetch_source_articles(
    source: SourceConfig,
    crawler: CrawlerConfig,
    *,
    existing_urls: set[str] | None = None,
) -> list[Article]:
    return list(iter_fetch_source_articles(source, crawler, existing_urls=existing_urls))


def iter_fetch_source_articles(
    source: SourceConfig,
    crawler: CrawlerConfig,
    *,
    existing_urls: set[str] | None = None,
) -> Iterable[Article]:
    if not source.enabled:
        return

    existing_urls = existing_urls or set()
    target_count = max(1, crawler.max_articles_per_source)
    candidate_limit = target_count * max(1, crawler.candidate_multiplier)
    min_quality_score = (
        source.min_quality_score
        if source.min_quality_score is not None
        else crawler.min_quality_score
    )
    accepted = 0
    for target in iter_source_targets_with_crawler(source, crawler, candidate_limit):
        if accepted >= target_count:
            break
        url = _normalize_candidate_url(target.get("discovery_url", ""), target["url"])
        if not url:
            continue
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
                    "discovery_url": target.get("discovery_url", ""),
                    "discovery_type": target.get("discovery_type", ""),
                },
            )
        except Exception as exc:
            print(f"Skipped {url}: {exc}")
            continue

        if len(article.text) < crawler.min_text_chars:
            print(f"Skipped {url}: extracted text too short ({len(article.text)} chars)")
            continue

        article.metadata.update(
            {
                "source_category": source.category,
                "source_reliability": source.reliability,
                "source_quality_weight": source.quality_weight,
                "min_quality_score": min_quality_score,
                "prefer_keywords": source.prefer_keywords,
                "exclude_keywords": source.exclude_keywords,
            }
        )
        quality = score_article_quality(article, source)
        article.metadata.update(quality)
        if quality["quality_score"] < min_quality_score or not quality["quality_keep"]:
            print(
                f"Skipped {url}: quality_score={quality['quality_score']} "
                f"reasons={';'.join(quality['quality_reasons'])}"
            )
            continue

        if not article.published_at and target.get("published_at"):
            article.published_at = target["published_at"]
        if target.get("title") and article.title == url:
            article.title = clean_text(target["title"])
        accepted += 1
        existing_urls.add(url)
        yield article
        if crawler.delay_seconds > 0:
            time.sleep(crawler.delay_seconds)


def _iter_discovery_urls(source: SourceConfig, crawler: CrawlerConfig) -> Iterable[str]:
    max_pages = crawler.max_discovery_pages_per_source
    yielded = 0

    search_capacity = (
        len(source.search_url_templates)
        * len(source.topic_queries)
        * max(1, crawler.max_search_pages_per_query)
    )
    reserved_search = min(max_pages // 3, search_capacity) if search_capacity else 0
    non_search_budget = max_pages - reserved_search

    for url in source.archive_urls:
        if yielded >= non_search_budget:
            break
        yielded += 1
        yield url

    template_pages = max(1, non_search_budget // max(len(source.archive_url_templates), 1))
    for template in source.archive_url_templates:
        for page in range(1, template_pages + 1):
            if yielded >= non_search_budget:
                break
            yielded += 1
            yield template.format(page=page)

    for template in source.search_url_templates:
        for query in source.topic_queries:
            for page in range(1, crawler.max_search_pages_per_query + 1):
                if yielded >= max_pages:
                    return
                yielded += 1
                yield template.format(
                    page=page,
                    query=query,
                    query_plus=quote_plus(query),
                    query_quote=quote_plus(f'"{query}"'),
                )


def _normalize_candidate_url(base_url: str, href: str) -> str:
    if not href or href.startswith(("mailto:", "tel:", "javascript:")):
        return ""
    url = urljoin(base_url, href)
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http") or not parsed.netloc:
        return ""
    if NON_ARTICLE_EXTENSIONS.search(parsed.path):
        return ""
    path = re.sub(r"/+$", "", parsed.path)
    return parsed._replace(path=path, params="", query="", fragment="").geturl()


def _looks_like_source_article(url: str, source: SourceConfig) -> bool:
    parsed = urlparse(url)
    if not parsed.netloc:
        return False

    configured_hosts = [
        urlparse(item).netloc.lower()
        for item in [*source.archive_urls, *source.feed_urls, *source.article_urls]
        if urlparse(item).netloc
    ]
    if configured_hosts and not any(
        parsed.netloc.lower().endswith(host) for host in configured_hosts
    ):
        return False

    lowered = url.lower()
    if any(re.search(pattern, lowered) for pattern in source.article_url_exclude_patterns):
        return False
    if source.article_url_patterns:
        return any(re.search(pattern, lowered) for pattern in source.article_url_patterns)

    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2:
        return False
    blocked = {
        "about",
        "advertising",
        "archive",
        "archives",
        "author",
        "authors",
        "category",
        "contact",
        "feed",
        "feeds",
        "help",
        "login",
        "newsletter",
        "podcasts",
        "privacy",
        "search",
        "subscribe",
        "subscription",
        "tag",
        "tags",
        "video",
    }
    return not any(segment.lower() in blocked for segment in segments)

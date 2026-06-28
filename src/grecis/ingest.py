from __future__ import annotations

import csv
import json
import re
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import CrawlerConfig, SourceConfig
from .models import Article
from .quality import score_article_quality

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

        article.metadata.update(
            {
                "source_category": source.category,
                "source_reliability": source.reliability,
                "source_quality_weight": source.quality_weight,
                "min_quality_score": crawler.min_quality_score,
                "prefer_keywords": source.prefer_keywords,
                "exclude_keywords": source.exclude_keywords,
            }
        )
        quality = score_article_quality(article, source)
        article.metadata.update(quality)
        if quality["quality_score"] < crawler.min_quality_score or not quality["quality_keep"]:
            print(
                f"Skipped {url}: quality_score={quality['quality_score']} "
                f"reasons={';'.join(quality['quality_reasons'])}"
            )
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

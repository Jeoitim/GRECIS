from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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


def fetch_url(url: str, source: str = "web") -> Article:
    import requests

    response = requests.get(url, timeout=20, headers={"User-Agent": "GRECIS/0.1"})
    response.raise_for_status()
    html = response.text

    text = ""
    title = url
    try:
        import trafilatura

        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        if extracted:
            text = extracted
        metadata = trafilatura.extract_metadata(html)
        if metadata and metadata.title:
            title = metadata.title
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

    return Article(title=clean_text(title), source=source, url=url, text=clean_text(text))

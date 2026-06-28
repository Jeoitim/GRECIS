from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .models import Article

BASE_URL = "https://pastpapers.cn"
KAOYAN_URL = f"{BASE_URL}/kaoyan"


@dataclass(slots=True)
class PastPaper:
    slug: str
    title: str
    url: str
    pdf_url: str = ""


def discover_pastpapers(limit: int | None = None, probe_years: bool = True) -> list[PastPaper]:
    response = requests.get(KAOYAN_URL, timeout=30, headers={"User-Agent": "GRECIS/0.1"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    papers: list[PastPaper] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        match = re.search(r"/paper/([0-9]{4}-[12])", href)
        if not match:
            continue
        slug = match.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        title = anchor.get_text(" ", strip=True) or slug
        papers.append(PastPaper(slug=slug, title=title, url=urljoin(BASE_URL, href)))

    papers.sort(key=lambda item: item.slug, reverse=True)
    if probe_years:
        papers = merge_papers(papers, probe_paper_slugs())
    if limit:
        return papers[:limit]
    return papers


def probe_paper_slugs(start_year: int = 1998, end_year: int = 2025) -> list[PastPaper]:
    papers: list[PastPaper] = []
    for year in range(end_year, start_year - 1, -1):
        for series in (1, 2):
            slug = f"{year}-{series}"
            url = f"{BASE_URL}/paper/{slug}"
            try:
                find_pdf_url(url)
            except Exception:
                continue
            papers.append(PastPaper(slug=slug, title=slug, url=url))
    return papers


def merge_papers(first: list[PastPaper], second: list[PastPaper]) -> list[PastPaper]:
    by_slug = {paper.slug: paper for paper in first}
    for paper in second:
        by_slug.setdefault(paper.slug, paper)
    return sorted(by_slug.values(), key=lambda item: item.slug, reverse=True)


def import_pastpapers(limit: int | None = None) -> list[Article]:
    articles: list[Article] = []
    for paper in discover_pastpapers(limit=limit):
        try:
            articles.extend(import_paper(paper))
        except Exception as exc:
            print(f"Skipped {paper.url}: {exc}")
    return articles


def import_paper(paper: PastPaper) -> list[Article]:
    paper.pdf_url = find_pdf_url(paper.url)
    with TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / f"{paper.slug}.pdf"
        download_file(paper.pdf_url, pdf_path)
        text = extract_pdf_text(pdf_path)
    passages = extract_reading_part_a(text)
    return [
        Article(
            id=f"pastpapers-{paper.slug}-text-{index}",
            title=f"{paper.slug} 考研英语阅读 Text {index}",
            source="pastpapers.cn",
            url=paper.url,
            published_at=paper.slug[:4],
            field="unknown",
            text=passage,
            metadata={
                "corpus_type": "kaoyan_exam",
                "year": paper.slug[:4],
                "paper_slug": paper.slug,
                "section": f"reading-text-{index}",
                "citation": f"pastpapers.cn {paper.slug} Reading Text {index}: {paper.url}",
                "pdf_url": paper.pdf_url,
            },
        )
        for index, passage in enumerate(passages, start=1)
    ]


def find_pdf_url(paper_url: str) -> str:
    response = requests.get(paper_url, timeout=30, headers={"User-Agent": "GRECIS/0.1"})
    response.raise_for_status()
    match = re.search(r"/uploads/[^\"'<> ]+?\.pdf", response.text)
    if not match:
        raise ValueError("No PDF URL found.")
    return urljoin(BASE_URL, match.group(0).replace("\\", ""))


def download_file(url: str, path: Path) -> None:
    response = requests.get(url, timeout=60, headers={"User-Agent": "GRECIS/0.1"})
    response.raise_for_status()
    path.write_bytes(response.content)


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) < 1000:
        raise ValueError("PDF appears to be scanned or text extraction failed.")
    return normalize_pdf_text(text)


def normalize_pdf_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"-\n(?=[a-z])", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_reading_part_a(text: str) -> list[str]:
    marker = re.search(r"Section\s+II\s+Reading\s+Comprehension", text, re.I)
    if marker:
        text = text[marker.start() :]
    end = re.search(r"\n\s*Part\s+B\b|\n\s*Section\s+III\b", text, re.I)
    if end:
        text = text[: end.start()]

    matches = list(re.finditer(r"\bText\s+([1-4])\b", text, re.I))
    passages: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        stop = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        candidate = clean_passage(text[start:stop])
        if is_valid_reading_passage(candidate):
            passages.append(candidate)
    return passages[:4]


def clean_passage(text: str) -> str:
    text = re.split(r"\n\s*(?:21|26|31|36)\s*[.．、]", text, maxsplit=1)[0]
    text = re.sub(r"\n\s*\d+\s*[.．、].*", "", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_valid_reading_passage(text: str) -> bool:
    english_tokens = re.findall(r"[A-Za-z]{3,}", text)
    return len(english_tokens) >= 120 and len(text) >= 600


def summarize_import(articles: list[Article]) -> dict[str, Any]:
    years = sorted({article.published_at for article in articles if article.published_at})
    return {
        "articles": len(articles),
        "years": years,
        "papers": sorted({article.metadata.get("paper_slug", "") for article in articles}),
    }

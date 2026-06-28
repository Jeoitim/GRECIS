from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, datetime
from hashlib import sha1
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def stable_id(*parts: str) -> str:
    source = "\n".join(part or "" for part in parts)
    return sha1(source.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class Article:
    title: str
    text: str
    source: str = "unknown"
    id: str | None = None
    url: str = ""
    published_at: str = ""
    field: str = "unknown"
    created_at: str = dc_field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = dc_field(default_factory=dict)

    def normalized_id(self) -> str:
        if self.id:
            return self.id
        return stable_id(self.source, self.title, self.text[:500])


@dataclass(slots=True)
class AnalysisResult:
    article_id: str
    field: str
    field_scores: dict[str, float]
    difficulty: float
    exam_value: float
    word_frequencies: list[dict[str, Any]]
    collocations: list[dict[str, Any]]
    polysemy: list[dict[str, Any]]
    sentence_patterns: list[dict[str, Any]]
    llm: dict[str, Any] = dc_field(default_factory=dict)
    created_at: str = dc_field(default_factory=utc_now_iso)

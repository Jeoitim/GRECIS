from __future__ import annotations

import re
from typing import Any

from .config import SourceConfig
from .models import Article
from .nlp import content_tokens, extract_polysemy, extract_sentence_patterns, split_sentences

DEFAULT_EXCLUDE_KEYWORDS = {
    "sport",
    "sports",
    "football",
    "soccer",
    "cricket",
    "tennis",
    "golf",
    "celebrity",
    "entertainment",
    "movie",
    "tv",
    "recipe",
    "travel",
    "crossword",
    "puzzle",
    "quiz",
    "live",
}

EXAM_TOPIC_KEYWORDS = {
    "policy",
    "regulation",
    "court",
    "science",
    "research",
    "study",
    "climate",
    "education",
    "economy",
    "market",
    "business",
    "technology",
    "society",
    "culture",
    "psychology",
    "environment",
    "inequality",
    "health",
    "law",
}

SECOND_TIER_SOURCES = {
    "the christian science monitor",
    "the guardian",
    "the atlantic",
}


def score_article_quality(article: Article, source: SourceConfig | None = None) -> dict[str, Any]:
    text = article.text or ""
    title_blob = f"{article.title} {article.url}".lower()
    tokens = content_tokens(text)
    sentences = split_sentences(text)
    token_count = len(tokens)
    sentence_count = len(sentences)
    avg_sentence_len = token_count / max(sentence_count, 1)
    polysemy_count = len(extract_polysemy(text))
    pattern_count = len(extract_sentence_patterns(text))
    if article.metadata.get("corpus_type") == "kaoyan_exam":
        return {
            "quality_score": 10.0,
            "quality_keep": True,
            "quality_reasons": ["kaoyan_exam_corpus"],
            "token_count": token_count,
            "sentence_count": sentence_count,
            "avg_sentence_len": round(token_count / max(sentence_count, 1), 2),
            "polysemy_count": polysemy_count,
            "pattern_count": pattern_count,
        }

    source_name = (source.name if source else article.source).lower()
    source_reliability = (
        source.reliability if source else article.metadata.get("source_reliability", 0.75)
    )
    quality_weight = (
        source.quality_weight if source else article.metadata.get("source_quality_weight", 1.0)
    )
    if source_name in SECOND_TIER_SOURCES:
        quality_weight = max(float(quality_weight), 1.1)
    else:
        quality_weight = min(float(quality_weight), 0.75)
    prefer_keywords = set(
        source.prefer_keywords if source else article.metadata.get("prefer_keywords", [])
    )
    exclude_keywords = set(
        source.exclude_keywords if source else article.metadata.get("exclude_keywords", [])
    )
    exclude_keywords |= DEFAULT_EXCLUDE_KEYWORDS

    reasons: list[str] = []
    score = 0.0

    reliability_score = min(max(float(source_reliability), 0.0), 1.0) * 2.0
    score += reliability_score
    reasons.append(f"source_reliability={reliability_score:.2f}")

    if token_count >= 900:
        score += 1.5
        reasons.append("substantial_text")
    elif token_count >= 450:
        score += 0.8
        reasons.append("medium_text")
    else:
        score -= 1.5
        reasons.append("short_text")

    if 18 <= avg_sentence_len <= 38:
        score += 1.2
        reasons.append("exam_like_sentence_length")
    elif avg_sentence_len > 38:
        score += 0.6
        reasons.append("complex_long_sentences")

    keyword_blob = f"{title_blob} {' '.join(tokens[:250])}"
    preferred_hits = keyword_hits(keyword_blob, prefer_keywords | EXAM_TOPIC_KEYWORDS)
    if preferred_hits:
        score += min(1.4, 0.25 * len(preferred_hits))
        reasons.append(f"preferred_topics={','.join(preferred_hits[:5])}")

    excluded_hits = keyword_hits(title_blob, exclude_keywords)
    if excluded_hits:
        score -= 3.0
        reasons.append(f"excluded_topics={','.join(excluded_hits[:5])}")

    if polysemy_count:
        score += min(1.2, 0.25 * polysemy_count)
        reasons.append(f"polysemy={polysemy_count}")

    if pattern_count:
        score += min(1.0, 0.18 * pattern_count)
        reasons.append(f"rhetorical_patterns={pattern_count}")

    if looks_like_wire_brief(text):
        score -= 1.0
        reasons.append("wire_brief_style")

    score *= float(quality_weight)
    score = round(max(0.0, min(score, 10.0)), 2)
    keep = not excluded_hits and token_count >= 450
    return {
        "quality_score": score,
        "quality_keep": keep,
        "quality_reasons": reasons,
        "token_count": token_count,
        "sentence_count": sentence_count,
        "avg_sentence_len": round(avg_sentence_len, 2),
        "polysemy_count": polysemy_count,
        "pattern_count": pattern_count,
    }


def keyword_hits(text: str, keywords: set[str]) -> list[str]:
    hits = []
    for keyword in sorted(keywords):
        if not keyword:
            continue
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        if re.search(pattern, text):
            hits.append(keyword)
    return hits


def looks_like_wire_brief(text: str) -> bool:
    sentences = split_sentences(text)
    if len(sentences) <= 5:
        return True
    first = text[:400].lower()
    return "reuters" in first or "associated press" in first

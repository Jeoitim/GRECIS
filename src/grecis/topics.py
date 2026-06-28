from __future__ import annotations

from collections import Counter

from .models import Article
from .nlp import STOPWORDS, content_tokens

DOMAIN_SEED_TERMS = {
    "climate",
    "court",
    "economy",
    "education",
    "environment",
    "government",
    "health",
    "market",
    "policy",
    "public",
    "research",
    "science",
    "social",
    "society",
    "technology",
}


def exam_topic_queries(articles: list[Article], limit: int = 24) -> list[str]:
    exam_texts = [
        article.text
        for article in articles
        if article.metadata.get("corpus_type") == "kaoyan_exam"
        or article.source.lower() in {"kaoyan_exam", "pastpapers.cn"}
    ]
    if not exam_texts:
        return []

    tokens = [token for text in exam_texts for token in content_tokens(text)]
    counts: Counter[tuple[str, ...]] = Counter()
    for n in (2, 3):
        for index in range(len(tokens) - n + 1):
            gram = tuple(tokens[index : index + n])
            if any(part in STOPWORDS or len(part) < 4 for part in gram):
                continue
            if not (set(gram) & DOMAIN_SEED_TERMS):
                continue
            counts[gram] += 1

    queries: list[str] = []
    for gram, frequency in counts.most_common(limit * 4):
        if frequency < 2:
            continue
        query = " ".join(gram)
        if query not in queries:
            queries.append(query)
        if len(queries) >= limit:
            break
    return queries

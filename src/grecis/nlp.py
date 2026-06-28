from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .models import AnalysisResult, Article

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "he",
    "her",
    "his",
    "in",
    "is",
    "it",
    "its",
    "may",
    "more",
    "not",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "which",
    "with",
    "would",
}

DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "politics": {
        "administration",
        "congress",
        "senate",
        "election",
        "policy",
        "minister",
        "campaign",
        "vote",
        "governor",
        "parliament",
    },
    "law": {
        "court",
        "judge",
        "ruling",
        "lawsuit",
        "litigation",
        "statute",
        "jurisdiction",
        "precedent",
        "appeal",
        "legal",
    },
    "economics": {
        "market",
        "capital",
        "inflation",
        "merger",
        "acquisition",
        "takeover",
        "tariff",
        "subsidy",
        "firm",
        "shareholder",
    },
    "science": {
        "study",
        "research",
        "evidence",
        "experiment",
        "data",
        "hypothesis",
        "scientist",
        "sample",
        "significant",
        "robust",
    },
    "environment": {
        "climate",
        "carbon",
        "emissions",
        "biodiversity",
        "ecosystem",
        "renewable",
        "conservation",
        "sustainability",
        "mitigation",
        "adaptation",
    },
    "education": {
        "school",
        "student",
        "teacher",
        "college",
        "curriculum",
        "learning",
        "education",
        "campus",
        "degree",
    },
    "psychology": {
        "behavior",
        "cognitive",
        "emotion",
        "memory",
        "bias",
        "motivation",
        "attention",
        "mental",
        "perception",
    },
    "sociology": {
        "society",
        "culture",
        "inequality",
        "community",
        "identity",
        "class",
        "race",
        "gender",
        "social",
    },
}

POLYSEMY_LEXICON: dict[str, dict[str, str]] = {
    "address": {"ordinary": "地址；发表演说", "context": "处理；探讨"},
    "case": {"ordinary": "情况；盒子", "context": "案件；论证依据"},
    "charge": {"ordinary": "收费；充电", "context": "指控；职责"},
    "concern": {"ordinary": "担心", "context": "涉及；企业"},
    "discipline": {"ordinary": "纪律", "context": "学科；训练体系"},
    "drive": {"ordinary": "驾驶", "context": "驱动因素；推动"},
    "find": {"ordinary": "找到", "context": "裁定；研究发现"},
    "hold": {"ordinary": "持有", "context": "裁定；认为"},
    "issue": {"ordinary": "问题", "context": "争议焦点；发布；发行"},
    "margin": {"ordinary": "边缘", "context": "优势；利润空间"},
    "move": {"ordinary": "移动", "context": "举措"},
    "novel": {"ordinary": "小说", "context": "新颖的"},
    "position": {"ordinary": "位置", "context": "立场；观点"},
    "robust": {"ordinary": "强壮的", "context": "稳健可靠的"},
    "school": {"ordinary": "学校", "context": "学派"},
    "significant": {"ordinary": "重要的", "context": "统计显著的"},
    "subject": {"ordinary": "主题；科目", "context": "使遭受；受制于"},
    "yield": {"ordinary": "产出；让步", "context": "收益率；产生结果"},
}

SENTENCE_PATTERNS: list[tuple[str, str, str]] = [
    ("concession", "让步", r"\b(although|though|even though|while|whereas)\b"),
    ("contrast", "转折/对比", r"\b(however|nevertheless|nonetheless|rather than|instead|but)\b"),
    (
        "causality",
        "因果",
        r"\b(because|since|therefore|thus|lead to|result in|account for|due to)\b",
    ),
    ("stance", "作者态度", r"\b(suggest|argue|claim|appear|likely|may|seem|should)\b"),
    ("emphasis", "强调", r"\b(not so much\b.+\bas|not only\b.+\bbut also|what matters is)\b"),
]

IRREGULAR_LEMMAS = {
    "held": "hold",
    "found": "find",
    "drove": "drive",
    "driven": "drive",
    "dealt": "deal",
    "argued": "argue",
    "studies": "study",
}


def split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in SENTENCE_RE.split(text.strip()) if sentence.strip()]


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower().strip("'") for match in TOKEN_RE.finditer(text)]


def simple_lemma(token: str) -> str:
    if token in IRREGULAR_LEMMAS:
        return IRREGULAR_LEMMAS[token]
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def content_tokens(text: str) -> list[str]:
    return [
        simple_lemma(token) for token in tokenize(text) if token not in STOPWORDS and len(token) > 2
    ]


def infer_domain(tokens: list[str]) -> tuple[str, dict[str, float]]:
    token_counts = Counter(tokens)
    raw_scores: dict[str, float] = {}
    for field, keywords in DOMAIN_KEYWORDS.items():
        raw_scores[field] = float(sum(token_counts[word] for word in keywords))

    total = sum(raw_scores.values())
    if total == 0:
        return "unknown", {field: 0.0 for field in DOMAIN_KEYWORDS}

    scores = {field: round(score / total, 4) for field, score in raw_scores.items()}
    best = max(scores.items(), key=lambda item: item[1])[0]
    return best, scores


def estimate_difficulty(tokens: list[str], sentence_count: int) -> float:
    if not tokens:
        return 1.0
    unique_ratio = len(set(tokens)) / len(tokens)
    avg_sentence_tokens = len(tokens) / max(sentence_count, 1)
    long_word_ratio = sum(1 for token in tokens if len(token) >= 9) / len(tokens)
    score = 2.0 + unique_ratio * 2.0 + min(avg_sentence_tokens / 18, 1.5) + long_word_ratio * 4.0
    return round(min(score, 10.0), 1)


def word_frequencies(tokens: list[str], field: str, limit: int = 40) -> list[dict[str, Any]]:
    counts = Counter(tokens)
    rows = []
    domain_words = DOMAIN_KEYWORDS.get(field, set())
    for word, frequency in counts.most_common(limit):
        category = "domain terminology" if word in domain_words else "academic/general"
        if word in POLYSEMY_LEXICON:
            category = "polysemy"
        rows.append(
            {
                "word": word,
                "lemma": word,
                "frequency": frequency,
                "category": category,
                "field": field,
                "importance": min(5, 1 + frequency),
            }
        )
    return rows


def extract_collocations(tokens: list[str], limit: int = 35) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, ...]] = Counter()
    for n in (2, 3):
        for index in range(len(tokens) - n + 1):
            gram = tuple(tokens[index : index + n])
            if any(part in STOPWORDS for part in gram):
                continue
            counts[gram] += 1

    rows = []
    for gram, frequency in counts.most_common(limit):
        if frequency < 1:
            continue
        rows.append(
            {
                "expression": " ".join(gram),
                "frequency": frequency,
                "type": f"{len(gram)}-gram",
                "importance": min(5, 1 + frequency),
            }
        )
    return rows


def extract_polysemy(text: str) -> list[dict[str, Any]]:
    sentences = split_sentences(text)
    hits: dict[str, dict[str, Any]] = {}
    for sentence in sentences:
        sentence_tokens = set(content_tokens(sentence))
        for word, meanings in POLYSEMY_LEXICON.items():
            if word in sentence_tokens and word not in hits:
                hits[word] = {
                    "word": word,
                    "ordinary_meaning": meanings["ordinary"],
                    "contextual_meaning": meanings["context"],
                    "sentence": sentence,
                    "exam_risk": "high",
                }
    return list(hits.values())


def extract_sentence_patterns(text: str) -> list[dict[str, Any]]:
    rows = []
    for sentence in split_sentences(text):
        lowered = sentence.lower()
        for code, label, pattern in SENTENCE_PATTERNS:
            if re.search(pattern, lowered):
                rows.append(
                    {
                        "type": code,
                        "function": label,
                        "sentence": sentence,
                        "importance": 4 if code in {"concession", "contrast", "causality"} else 3,
                    }
                )
                break
    return rows[:30]


def estimate_exam_value(
    frequencies: list[dict[str, Any]],
    polysemy: list[dict[str, Any]],
    patterns: list[dict[str, Any]],
) -> float:
    domain_terms = sum(1 for item in frequencies if item["category"] == "domain terminology")
    score = 3.0 + min(domain_terms, 10) * 0.25 + min(len(polysemy), 10) * 0.35
    score += min(len(patterns), 10) * 0.2
    return round(min(score, 10.0), 1)


def analyze_article(article: Article, llm_payload: dict[str, Any] | None = None) -> AnalysisResult:
    tokens = content_tokens(article.text)
    sentences = split_sentences(article.text)
    field, field_scores = infer_domain(tokens)
    frequencies = word_frequencies(tokens, field)
    polysemy = extract_polysemy(article.text)
    patterns = extract_sentence_patterns(article.text)
    collocations = extract_collocations(tokens)
    difficulty = estimate_difficulty(tokens, len(sentences))
    exam_value = estimate_exam_value(frequencies, polysemy, patterns)

    return AnalysisResult(
        article_id=article.normalized_id(),
        field=field,
        field_scores=field_scores,
        difficulty=difficulty,
        exam_value=exam_value,
        word_frequencies=frequencies,
        collocations=collocations,
        polysemy=polysemy,
        sentence_patterns=patterns,
        llm=llm_payload or {},
    )


def pmi_collocations(
    texts: list[str], min_frequency: int = 2, limit: int = 50
) -> list[dict[str, Any]]:
    tokens = [token for text in texts for token in content_tokens(text)]
    unigram = Counter(tokens)
    bigram = Counter(zip(tokens, tokens[1:], strict=False))
    total = max(len(tokens), 1)
    rows = []
    for (first, second), frequency in bigram.items():
        if frequency < min_frequency:
            continue
        probability_xy = frequency / total
        probability_x = unigram[first] / total
        probability_y = unigram[second] / total
        score = math.log2(probability_xy / (probability_x * probability_y))
        rows.append(
            {"expression": f"{first} {second}", "frequency": frequency, "pmi": round(score, 3)}
        )
    return sorted(rows, key=lambda item: (item["pmi"], item["frequency"]), reverse=True)[:limit]

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .models import AnalysisResult, Article

try:
    from wordfreq import zipf_frequency
except Exception:  # pragma: no cover - optional fallback
    zipf_frequency = None

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

EXAM_PHRASES: list[dict[str, str]] = [
    {
        "expression": "at issue",
        "pattern": r"\bat issue\b",
        "meaning": "争议焦点在于",
        "type": "legal/political expression",
    },
    {
        "expression": "take issue with",
        "pattern": r"\btak(?:e|es|ing)? issue with\b|\btook issue with\b|\btaken issue with\b",
        "meaning": "反对；质疑某观点",
        "type": "stance expression",
    },
    {
        "expression": "at stake",
        "pattern": r"\bat stake\b",
        "meaning": "利害攸关；处于风险中",
        "type": "argument expression",
    },
    {
        "expression": "subject to",
        "pattern": r"\bsubject to\b",
        "meaning": "受制于；可能遭受",
        "type": "polysemy phrase",
    },
    {
        "expression": "account for",
        "pattern": r"\baccount(?:s|ed|ing)? for\b",
        "meaning": "解释；占比",
        "type": "academic expression",
    },
    {
        "expression": "result in",
        "pattern": r"\bresult(?:s|ed|ing)? in\b",
        "meaning": "导致",
        "type": "causality expression",
    },
    {
        "expression": "lead to",
        "pattern": r"\blead(?:s|ing)? to\b|\bled to\b",
        "meaning": "导致；通向",
        "type": "causality expression",
    },
    {
        "expression": "not so much A as B",
        "pattern": r"\bnot so much\b.+\bas\b",
        "meaning": "与其说是 A，不如说是 B",
        "type": "comparison pattern",
    },
]

IRREGULAR_LEMMAS = {
    "held": "hold",
    "found": "find",
    "drove": "drive",
    "driven": "drive",
    "dealt": "deal",
    "argued": "argue",
    "studies": "study",
    # Common verb mappings to correct lemmatization errors
    "making": "make", "made": "make",
    "using": "use", "used": "use",
    "taking": "take", "took": "take", "taken": "take",
    "ruling": "rule", "ruled": "rule",
    "giving": "give", "gave": "give", "given": "give",
    "writing": "write", "wrote": "write", "written": "write",
    "creating": "create", "created": "create",
    "sharing": "share", "shared": "share",
    "reducing": "reduce", "reduced": "reduce",
    "providing": "provide", "provided": "provide",
    "requiring": "require", "required": "require",
    "producing": "produce", "produced": "produce",
    "deciding": "decide", "decided": "decide",
    "judging": "judge", "judged": "judge",
    "stating": "state", "stated": "state",
    "acquiring": "acquire", "acquired": "acquire",
    "improving": "improve", "improved": "improve",
    "increasing": "increase", "increased": "increase",
    "decreasing": "decrease", "decreased": "decrease",
    "declining": "decline", "declined": "decline",
    "rising": "rise", "rose": "rise", "risen": "rise",
    "falling": "fall", "fell": "fall", "fallen": "fall",
    "choosing": "choose", "chose": "choose", "chosen": "choose",
    "coming": "come", "came": "come",
    "having": "have", "had": "have",
    "going": "go", "went": "go", "gone": "go",
    "being": "be", "was": "be", "were": "be", "been": "be",
    "challenging": "challenge", "challenged": "challenge",
    "consolidating": "consolidate", "consolidated": "consolidate",
    "solving": "solve", "solved": "solve",
    "evaluating": "evaluate", "evaluated": "evaluate",
}

HIGH_SCHOOL_WORD_ZIPF_THRESHOLD = 5.5
HIGH_VALUE_PHRASES = {
    "at issue",
    "take issue with",
    "at stake",
    "subject to",
    "account for",
    "result in",
    "lead to",
    "not so much A as B",
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


def find_example_sentence(word: str, sentences: list[str]) -> str:
    for sentence in sentences:
        if word in set(content_tokens(sentence)):
            return sentence
    return ""


def word_frequencies(
    tokens: list[str], field: str, sentences: list[str], limit: int = 40
) -> list[dict[str, Any]]:
    counts = Counter(tokens)
    rows = []
    domain_words = DOMAIN_KEYWORDS.get(field, set())
    for word, frequency in counts.most_common(limit):
        category = "domain terminology" if word in domain_words else "academic/general"
        if word in POLYSEMY_LEXICON:
            category = "polysemy"
        if category != "polysemy" and _is_common_high_school_word(word):
            continue
        rows.append(
            {
                "word": word,
                "lemma": word,
                "frequency": frequency,
                "category": category,
                "field": field,
                "importance": min(5, 1 + frequency),
                "example_sentence": find_example_sentence(word, sentences),
            }
        )
    return rows


def extract_collocations(text: str, tokens: list[str], limit: int = 35) -> list[dict[str, Any]]:
    sentences = split_sentences(text)
    phrase_rows: list[dict[str, Any]] = []
    lowered = text.lower()
    for phrase in EXAM_PHRASES:
        matches = re.findall(phrase["pattern"], lowered)
        if not matches:
            continue
        example = next(
            (sentence for sentence in sentences if re.search(phrase["pattern"], sentence.lower())),
            "",
        )
        phrase_rows.append(
            {
                "expression": phrase["expression"],
                "frequency": len(matches),
                "type": phrase["type"],
                "importance": 5,
                "meaning": phrase["meaning"],
                "example_sentence": example,
            }
        )

    counts: Counter[tuple[str, ...]] = Counter()
    for n in (2, 3):
        for index in range(len(tokens) - n + 1):
            gram = tuple(tokens[index : index + n])
            if any(part in STOPWORDS for part in gram):
                continue
            counts[gram] += 1

    rows = phrase_rows.copy()
    existing = {row["expression"] for row in rows}
    for gram, frequency in counts.most_common(limit):
        if frequency < 1:
            continue
        expression = " ".join(gram)
        if expression in existing:
            continue
        if not _is_high_value_expression(expression, frequency, text, sentences):
            continue
        rows.append(
            {
                "expression": expression,
                "frequency": frequency,
                "type": f"{len(gram)}-gram",
                "importance": min(5, 1 + frequency),
                "meaning": "",
                "example_sentence": find_ngram_example(expression, sentences),
            }
        )
    rows.sort(key=lambda item: (item["frequency"], item.get("importance", 0)), reverse=True)
    return rows[:limit]


def find_ngram_example(expression: str, sentences: list[str]) -> str:
    parts = expression.split()
    for sentence in sentences:
        tokens = content_tokens(sentence)
        for index in range(len(tokens) - len(parts) + 1):
            if tokens[index : index + len(parts)] == parts:
                return sentence
    return ""


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


def _is_common_high_school_word(word: str) -> bool:
    if not zipf_frequency:
        return False
    if word in POLYSEMY_LEXICON:
        return False
    return zipf_frequency(word, "en") >= HIGH_SCHOOL_WORD_ZIPF_THRESHOLD


def _is_high_value_expression(
    expression: str, frequency: int, text: str, sentences: list[str]
) -> bool:
    if expression in HIGH_VALUE_PHRASES:
        return True
    if frequency >= 4:
        return True
    if " " not in expression:
        return False
    if zipf_frequency:
        terms = [term for term in expression.split() if term]
        if len(terms) >= 2 and any(zipf_frequency(term, "en") < 5.0 for term in terms):
            return True
    pattern = r"\b" + re.escape(expression) + r"\b"
    if any(re.search(pattern, sentence.lower()) for sentence in sentences):
        return len(expression.split()) >= 2 and len(expression) >= 10
    return False


def analyze_article(article: Article, llm_payload: dict[str, Any] | None = None) -> AnalysisResult:
    tokens = content_tokens(article.text)
    sentences = split_sentences(article.text)
    field, field_scores = infer_domain(tokens)
    frequencies = word_frequencies(tokens, field, sentences)
    polysemy = extract_polysemy(article.text)
    patterns = extract_sentence_patterns(article.text)
    collocations = extract_collocations(article.text, tokens)
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

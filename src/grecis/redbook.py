from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .db import CorpusDB
from .dictionary import query_word
from .export import is_exportable_expression, is_exportable_vocabulary, stars, table, truncate
from .patterns import (
    infer_sentence_pattern_template,
    normalize_sentence_pattern_type,
    pattern_metadata,
    pattern_priority,
    sentence_example_quality,
)

try:
    from wordfreq import zipf_frequency
except Exception:  # pragma: no cover - optional fallback
    zipf_frequency = None

DOMAIN_ALIASES = {
    "politics": "politics_law",
    "law": "politics_law",
    "politics_law": "politics_law",
    "economics": "economics_business",
    "business": "economics_business",
    "finance": "economics_business",
    "economics_business": "economics_business",
    "environment": "environment",
    "climate": "environment",
    "education": "society_education_psychology",
    "psychology": "society_education_psychology",
    "sociology": "society_education_psychology",
    "society": "society_education_psychology",
    "society_education_psychology": "society_education_psychology",
    "science": "research_methods",
    "academic": "research_methods",
    "science_academic": "research_methods",
    "academic_science": "research_methods",
    "technology": "technology_ai",
    "tech": "technology_ai",
    "ai": "technology_ai",
    "health": "health_biomedicine",
    "medicine": "health_biomedicine",
    "biomedicine": "health_biomedicine",
    "media": "media_culture",
    "culture": "media_culture",
    "unknown": "general_academic",
    "general": "general_academic",
    "general_academic": "general_academic",
}

DOMAIN_PROFILES: dict[str, set[str]] = {
    "politics_law": {
        "administration",
        "agency",
        "appeal",
        "authority",
        "campaign",
        "case",
        "coalition",
        "complaint",
        "congress",
        "constitution",
        "court",
        "democracy",
        "federal",
        "govern",
        "government",
        "judge",
        "jurisdiction",
        "law",
        "legal",
        "legislation",
        "liability",
        "litigation",
        "mandate",
        "minister",
        "parliament",
        "policy",
        "political",
        "public",
        "regulation",
        "regulator",
        "ruling",
        "senate",
        "statute",
        "vote",
    },
    "economics_business": {
        "acquisition",
        "asset",
        "bank",
        "bond",
        "business",
        "capital",
        "company",
        "competition",
        "consumer",
        "corporate",
        "cost",
        "deal",
        "economy",
        "financial",
        "firm",
        "inflation",
        "investment",
        "market",
        "merger",
        "monetize",
        "profit",
        "revenue",
        "shareholder",
        "stock",
        "subsidy",
        "takeover",
        "tariff",
        "tax",
        "trade",
        "yield",
    },
    "research_methods": {
        "analysis",
        "assumption",
        "benchmark",
        "citation",
        "conclusion",
        "data",
        "evidence",
        "experiment",
        "finding",
        "findings",
        "hypothesis",
        "indicate",
        "investigation",
        "method",
        "model",
        "parameter",
        "peer-reviewed",
        "research",
        "researcher",
        "result",
        "robust",
        "sample",
        "significant",
        "study",
        "suggest",
        "theory",
        "underlie",
    },
    "technology_ai": {
        "ai",
        "algorithm",
        "artificial",
        "attribution",
        "automation",
        "born-digital",
        "code",
        "computational",
        "copyright",
        "cyber",
        "cybersecurity",
        "data",
        "dataset",
        "digital",
        "hacker",
        "internet",
        "model",
        "online",
        "platform",
        "privacy",
        "prompt",
        "prompts",
        "protocol",
        "software",
        "technology",
        "tech",
        "vulnerability",
        "web",
    },
    "health_biomedicine": {
        "acute",
        "antibiotic",
        "care",
        "cell",
        "clinical",
        "cognitive",
        "disease",
        "disorder",
        "efficacy",
        "gene",
        "genetic",
        "health",
        "insurance",
        "medical",
        "medicine",
        "mental",
        "obesity",
        "outbreak",
        "pathogen",
        "patient",
        "primary",
        "primary care",
        "public health",
        "therapy",
        "treatment",
        "vaccine",
    },
    "environment": {
        "adaptation",
        "biodiversity",
        "carbon",
        "climate",
        "conservation",
        "ecological",
        "ecosystem",
        "emissions",
        "energy",
        "environment",
        "greenhouse",
        "habitat",
        "mitigation",
        "pollution",
        "renewable",
        "resilience",
        "sustainability",
        "sustainable",
    },
    "society_education_psychology": {
        "bias",
        "class",
        "college",
        "community",
        "culture",
        "curriculum",
        "degree",
        "education",
        "emotion",
        "family",
        "gender",
        "identity",
        "inequality",
        "learning",
        "memory",
        "mental",
        "motivation",
        "pedagogy",
        "perception",
        "psychology",
        "race",
        "school",
        "social",
        "society",
        "student",
        "teacher",
    },
    "media_culture": {
        "archive",
        "art",
        "author",
        "book",
        "copyright",
        "culture",
        "digital",
        "film",
        "historical",
        "journal",
        "library",
        "media",
        "narrative",
        "pirate",
        "pirates",
        "public domain",
        "publish",
        "publishing",
        "reading",
        "story",
        "text",
    },
    "general_academic": {
        "address",
        "challenge",
        "concern",
        "factor",
        "issue",
        "major",
        "process",
        "provide",
        "require",
        "role",
        "shift",
        "trend",
    },
}

DOMAIN_LIMITS = {
    "politics_law": 320,
    "economics_business": 240,
    "research_methods": 240,
    "technology_ai": 220,
    "health_biomedicine": 220,
    "environment": 180,
    "society_education_psychology": 280,
    "media_culture": 160,
    "general_academic": 120,
}

HIGH_VALUE_PHRASES = {
    "account for",
    "at issue",
    "at stake",
    "be subject to",
    "crack down on",
    "lead to",
    "make the case for",
    "not so much a as b",
    "primary care",
    "public domain",
    "result in",
    "shy of",
    "social determinants of health",
    "subject to",
    "take issue with",
}

HIGH_VALUE_TERMS = {
    "acquisition",
    "adaptation",
    "algorithm",
    "bias",
    "biodiversity",
    "capital",
    "case",
    "challenge",
    "consolidation",
    "court",
    "efficacy",
    "emissions",
    "evidence",
    "indicate",
    "jurisdiction",
    "liability",
    "mandate",
    "margin",
    "merger",
    "mitigation",
    "policy",
    "regulation",
    "regulator",
    "resilience",
    "robust",
    "ruling",
    "significant",
    "subject",
    "sustainability",
    "threshold",
    "vulnerability",
    "yield",
}

LOW_VALUE_REDBOOK_WORDS = {
    "book",
    "critic",
    "edit",
    "gig",
    "image",
    "journal",
    "labor",
    "older",
    "people",
    "rev",
    "snap",
    "supplement",
    "turf",
    "volume",
    "weapon",
}

NOISE_WORDS = {
    "cas",
    "chang",
    "davunetide",
    "haddock",
    "http",
    "mak",
    "mpox",
    "near-infrar",
    "phy",
}


def safe_print(msg: str, end: str = "\n", flush: bool = True) -> None:
    try:
        print(msg, end=end, flush=flush)
    except UnicodeEncodeError:
        try:
            import sys

            encoding = sys.stdout.encoding or "utf-8"
            encoded_bytes = (msg + end).encode(encoding, errors="backslashreplace")
            sys.stdout.buffer.write(encoded_bytes)
            if flush:
                sys.stdout.flush()
        except Exception:
            try:
                ascii_msg = msg.encode("ascii", errors="backslashreplace").decode("ascii")
                print(ascii_msg, end=end, flush=flush)
            except Exception:
                pass


def highlight_word(sentence: str, word: str) -> str:
    if not sentence or not word:
        return sentence

    extra_forms = []
    word_lower = word.strip().lower()
    if word_lower == "hold":
        extra_forms = ["held"]
    elif word_lower == "find":
        extra_forms = ["found"]
    elif word_lower == "take":
        extra_forms = ["took", "taken"]
    elif word_lower == "drive":
        extra_forms = ["drove", "driven"]
    elif word_lower == "take issue with":
        extra_forms = [
            "took issue with",
            "takes issue with",
            "taken issue with",
            "taking issue with",
        ]

    forms = [word_lower] + extra_forms
    forms.sort(key=len, reverse=True)

    pattern_parts = []
    for form in forms:
        escaped = re.escape(form)
        if " " in form:
            pattern_parts.append(rf"\b{escaped}\b")
        else:
            pattern_parts.append(rf"\b{escaped}(?:s|es|ed|ing|d|r|er)?\b")

    pattern = re.compile("(" + "|".join(pattern_parts) + ")", re.IGNORECASE)
    return pattern.sub(r"**\1**", sentence)


DEFAULT_REDBOOK_SEED = "data/redbook_seed.yaml"


def write_redbook(
    db: CorpusDB,
    output_dir: str | Path,
    seed_path: str | Path = DEFAULT_REDBOOK_SEED,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for stale_file in output.glob("GRECIS-考研外刊词汇红宝书*.md"):
        stale_file.unlink()
    seed = load_seed(seed_path)
    corpus = build_corpus_index(db)

    metadata = seed.get("metadata", {})
    domains = normalize_redbook_domains(seed.get("domains", {}))

    seed_words = set()
    for domain in domains.values():
        for entry in domain.get("entries", []):
            if entry.get("headword"):
                seed_words.add(entry["headword"].lower().strip())

    corpus_vocab = rank_vocabulary_for_redbook(corpus["vocabulary"], seed_words)

    grouped_corpus: dict[str, list[dict[str, Any]]] = defaultdict(list)
    safe_print(
        f"[Export] Categorizing and querying {len(corpus_vocab)} corpus vocabulary items...",
        flush=True,
    )
    rejected_entries: list[dict[str, Any]] = []
    for idx, item in enumerate(corpus_vocab):
        if idx % 50 == 0 or idx == len(corpus_vocab) - 1:
            safe_print(
                f"[Export] Processing corpus vocab: {idx + 1}/{len(corpus_vocab)} ({item['word']})",
                flush=True,
            )
        classified = classify_redbook_entry(item)
        domain_key = classified["domain"]
        item.update(
            {
                "redbook_domain": domain_key,
                "redbook_score": classified["score"],
                "redbook_confidence": classified["confidence"],
                "redbook_reasons": classified["reasons"],
            }
        )
        if not is_high_quality_redbook_entry(item):
            rejected_entries.append(item)
            continue
        grouped_corpus[domain_key].append(item)

    grouped_corpus, overflow_entries = apply_domain_limits(grouped_corpus)
    rejected_entries.extend(overflow_entries)

    for domain_key, domain in domains.items():
        title = domain["title"].replace("\n", "").replace("\r", "").strip()
        overview = domain.get("overview", "")

        seed_entries = []
        for entry in domain.get("entries", []):
            entry_copy = dict(entry)
            entry_copy["is_seed"] = True
            seed_entries.append(entry_copy)

        corpus_entries = []
        for item in grouped_corpus[domain_key]:
            item_copy = dict(item)
            item_copy["is_seed"] = False
            corpus_entries.append(item_copy)

        combined_entries = seed_entries + corpus_entries
        combined_entries.sort(
            key=lambda x: (
                _vocabulary_category_priority(x),
                int(x.get("importance") or 0),
                int(x.get("frequency") or 0),
            ),
            reverse=True,
        )

        domain_lines = [
            f"# {metadata.get('title', 'GRECIS 考研外刊词汇红宝书')} - {title}",
            "",
            overview,
            "",
            "---",
            "",
        ]
        domain_lines.extend(render_unified_domain(title, overview, combined_entries, corpus))

        domain_file_path = output / f"GRECIS-考研外刊词汇红宝书-{title}.md"
        domain_file_path.write_text("\n".join(domain_lines), encoding="utf-8")

    _write_sentence_patterns_file(
        output,
        metadata,
        seed.get("sentence_patterns", []),
        corpus,
    )

    app_lines = [
        f"# {metadata.get('title', 'GRECIS 考研外刊词汇红宝书')} - 未归类学术词汇附录",
        "",
        "语料库中提取出的高频但领域置信度较低的核心词汇，作为补充备考使用。",
        "",
        "---",
        "",
    ]
    app_lines.extend(render_corpus_appendix(corpus, seed_words, rejected_entries))
    app_file_path = output / "GRECIS-考研外刊词汇红宝书-未归类附录.md"
    app_file_path.write_text("\n".join(app_lines), encoding="utf-8")

    rp_lines = [
        f"# {metadata.get('title', 'GRECIS 考研外刊词汇红宝书')} - 7天复习计划",
        "",
        "合理规划，高效突破。以下是为你量身定制的7天红宝书背诵与复习计划建议。",
        "",
        "---",
        "",
    ]
    rp_lines.extend(render_review_plan())
    rp_file_path = output / "GRECIS-考研外刊词汇红宝书-7天复习计划.md"
    rp_file_path.write_text("\n".join(rp_lines), encoding="utf-8")

    index_lines = [
        f"# {metadata.get('title', 'GRECIS 考研外刊词汇红宝书')}",
        "",
        metadata.get("subtitle", ""),
        "",
        "## 使用说明",
        "",
        "- 本红宝书词汇量大、内容丰富，已按**学科专业板块**拆分为多个子文件，方便日常背诵与阅读。",
        "- 先背各板块的熟词生义和固定搭配，再看领域术语。",
        "- 每个词条优先记“考研义”和“误译风险”，不要只背中文对照。",
        "- 例句分为项目例句 and 语料库例句；语料库例句来自本地已抓取文章的短摘录。",
        "",
        "## 快速背诵清单",
        "",
        render_quick_list(domains),
        "",
        "## 📖 板块目录",
        "",
    ]
    for idx, (_domain_key, domain) in enumerate(domains.items(), start=1):
        title = domain["title"]
        index_lines.append(f"{idx}. [{title}](./GRECIS-考研外刊词汇红宝书-{title}.md)")

    index_lines.extend(
        [
            f"{len(domains) + 1}. [常见句型与表达](./GRECIS-考研外刊词汇红宝书-常见句型与表达.md)",
            f"{len(domains) + 2}. [未归类学术词汇附录](./GRECIS-考研外刊词汇红宝书-未归类附录.md)",
            f"{len(domains) + 3}. [7天复习计划](./GRECIS-考研外刊词汇红宝书-7天复习计划.md)",
            "",
            "---",
            "",
            "**祝各位考研学子金榜题名！**",
        ]
    )

    main_index_path = output / "GRECIS-考研外刊词汇红宝书.md"
    main_index_path.write_text("\n".join(index_lines), encoding="utf-8")

    return main_index_path


def write_sentence_patterns_guide(
    db: CorpusDB,
    output_dir: str | Path,
    seed_path: str | Path = DEFAULT_REDBOOK_SEED,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    seed = load_seed(seed_path)
    corpus = build_corpus_index(db)
    return _write_sentence_patterns_file(
        output,
        seed.get("metadata", {}),
        seed.get("sentence_patterns", []),
        corpus,
    )


def _write_sentence_patterns_file(
    output: Path,
    metadata: dict[str, Any],
    seed_patterns: list[dict[str, Any]],
    corpus: dict[str, Any],
) -> Path:
    lines = [
        f"# {metadata.get('title', 'GRECIS 考研外刊词汇红宝书')} - 常见句型与表达",
        "",
        "外刊中常见且在考研中极其重要的长难句及特殊句型结构分析。",
        "",
        "---",
        "",
    ]
    lines.extend(render_sentence_patterns(seed_patterns, corpus))
    path = output / "GRECIS-考研外刊词汇红宝书-常见句型与表达.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def load_seed(path: str | Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def normalize_redbook_domains(domains: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(domains)
    additions = {
        "research_methods": {
            "title": "研究方法与学术论证",
            "overview": "研究报道、实证分析和议论文中用于呈现证据、结论与因果链的高频词汇。",
            "entries": [],
        },
        "technology_ai": {
            "title": "科技互联网与AI",
            "overview": "人工智能、数字平台、数据治理、网络安全和版权技术文本中的核心表达。",
            "entries": [],
        },
        "health_biomedicine": {
            "title": "医学健康与生命科学",
            "overview": "公共健康、医学研究、心理健康和生命科学报道中的高频考研词汇。",
            "entries": [],
        },
        "media_culture": {
            "title": "媒体文化与数字版权",
            "overview": "阅读、出版、媒体、文化记忆和数字版权文章中的常见表达。",
            "entries": [],
        },
        "general_academic": {
            "title": "泛学术核心词",
            "overview": "跨领域反复出现、对理解论证结构有帮助的泛学术词汇。",
            "entries": [],
        },
    }

    if "science_academic" in normalized:
        science_domain = normalized.pop("science_academic")
        merged = additions["research_methods"]
        merged["entries"] = list(science_domain.get("entries", [])) + merged["entries"]
        if science_domain.get("overview"):
            merged["overview"] = science_domain["overview"]

    for key, value in additions.items():
        normalized.setdefault(key, value)
    return normalized


def build_corpus_index(db: CorpusDB) -> dict[str, Any]:
    vocabulary = db.aggregate_vocabulary()
    collocations = db.aggregate_collocations()
    polysemy = db.aggregate_polysemy()
    sentence_patterns = db.aggregate_sentence_patterns()
    llm_rows = db.fetch_llm_rows()

    by_word = defaultdict(list)
    for item in vocabulary:
        by_word[item["word"].lower()].append(item)

    by_expression = defaultdict(list)
    for item in collocations:
        by_expression[item["expression"].lower()].append(item)

    gloss_index = build_gloss_index(vocabulary, llm_rows)
    return {
        "vocabulary": vocabulary,
        "collocations": collocations,
        "polysemy": polysemy,
        "sentence_patterns": sentence_patterns,
        "by_word": by_word,
        "by_expression": by_expression,
        "gloss_index": gloss_index,
    }


def map_field_to_domain_key(field: str, word: str = "") -> str:
    f = str(field).lower().strip()
    w = word.strip().lower()
    if f in DOMAIN_ALIASES:
        return DOMAIN_ALIASES[f]
    if not w:
        return "general_academic"

    from .nlp import DOMAIN_KEYWORDS

    for domain_name, keywords in DOMAIN_KEYWORDS.items():
        if w in keywords:
            return DOMAIN_ALIASES.get(domain_name, "general_academic")

    try:
        from .dictionary import query_word

        dict_data = query_word(w)
        zh = dict_data.get("zh", "").lower()

        politics_law_zh = {
            "法",
            "诉讼",
            "裁决",
            "审理",
            "政府",
            "政治",
            "竞选",
            "议会",
            "宪法",
            "条例",
            "监管",
        }
        economics_business_zh = {
            "经济",
            "金融",
            "公司",
            "企业",
            "商业",
            "贸易",
            "资本",
            "资金",
            "收购",
            "合并",
            "投资",
            "税",
            "银行",
        }
        science_academic_zh = {
            "科学",
            "研究",
            "学者",
            "实验",
            "数据",
            "理论",
            "技术",
            "学术",
            "发现",
            "基因",
            "细胞",
            "分析",
        }
        environment_zh = {
            "环境",
            "气候",
            "温室",
            "排放",
            "生态",
            "污染",
            "碳",
            "减缓",
            "适应",
            "生物",
        }
        society_education_zh = {
            "社会",
            "教育",
            "学校",
            "心理",
            "认知",
            "家庭",
            "群体",
            "文化",
            "学生",
            "教学",
        }

        scores = {
            "politics_law": sum(1 for k in politics_law_zh if k in zh),
            "economics_business": sum(1 for k in economics_business_zh if k in zh),
            "research_methods": sum(1 for k in science_academic_zh if k in zh),
            "environment": sum(1 for k in environment_zh if k in zh),
            "society_education_psychology": sum(1 for k in society_education_zh if k in zh),
        }

        max_score = max(scores.values())
        if max_score > 0:
            return [k for k, v in scores.items() if v == max_score][0]
    except Exception:
        pass

    return DOMAIN_ALIASES.get(f, "general_academic")


def classify_redbook_entry(item: dict[str, Any]) -> dict[str, Any]:
    word = normalize_entry_word(item)
    field = str(item.get("field") or "").lower().strip()
    category = str(item.get("category") or item.get("kind") or "").lower()
    example = str(item.get("example_sentence") or item.get("gloss") or "").lower()
    sources = str(item.get("sources") or item.get("citation") or "").lower()
    text = " ".join(part for part in [word, example, sources, category] if part)

    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)

    field_domain = DOMAIN_ALIASES.get(field)
    if field_domain:
        scores[field_domain] += 2.0
        reasons[field_domain].append(f"field:{field}")

    for domain, keywords in DOMAIN_PROFILES.items():
        for keyword in keywords:
            if keyword in word:
                scores[domain] += 4.0 if " " in keyword else 3.0
                reasons[domain].append(f"word:{keyword}")
            elif keyword in text:
                scores[domain] += 1.0
                reasons[domain].append(f"context:{keyword}")

    if "legal" in category or "political" in category:
        scores["politics_law"] += 2.5
        reasons["politics_law"].append("category:legal/political")
    if "academic" in category:
        scores["research_methods"] += 1.2
        reasons["research_methods"].append("category:academic")
    if "domain terminology" in category or category == "term":
        for domain, score in list(scores.items()):
            scores[domain] = score + 0.8

    if not scores:
        domain = map_field_to_domain_key(field, word)
        return {"domain": domain, "score": 0.0, "confidence": 0.0, "reasons": ["fallback"]}

    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    domain, score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = round((score - runner_up) / max(score, 1.0), 3)
    if score < 2.5 or confidence < 0.18:
        domain = "general_academic"
    return {
        "domain": domain,
        "score": round(score, 2),
        "confidence": confidence,
        "reasons": reasons.get(domain, [])[:5],
    }


def normalize_entry_word(item: dict[str, Any]) -> str:
    return str(item.get("headword") or item.get("word") or "").strip().lower()


def is_high_quality_redbook_entry(item: dict[str, Any]) -> bool:
    word = normalize_entry_word(item)
    if not word or word in LOW_VALUE_REDBOOK_WORDS or word in NOISE_WORDS:
        return False
    if any(part in NOISE_WORDS for part in word.split()):
        return False
    if re.search(r"https?://|www\.|[^a-z0-9 '&-]", word):
        return False
    if len(word) <= 2 and word not in {"ai"}:
        return False
    if len(word) > 48:
        return False

    category = str(item.get("category") or item.get("kind") or "").lower()
    frequency = int(item.get("frequency") or 0)
    article_count = int(item.get("article_count") or 0)
    importance = int(item.get("importance") or 0)

    if "polysemy" in category or "熟词" in category:
        return True
    if word in HIGH_VALUE_PHRASES or word in HIGH_VALUE_TERMS:
        return frequency >= 1 or importance >= 4
    if " " in word:
        return is_high_quality_phrase(item)

    zfreq = zipf_frequency(word, "en") if zipf_frequency else 4.0
    if zfreq <= 2.8:
        return False
    if zfreq >= 5.45 and word not in HIGH_VALUE_TERMS:
        return False

    if item.get("redbook_domain") == "general_academic":
        return (article_count >= 4 and frequency >= 6) or importance >= 5
    if "llm" in category:
        return importance >= 5 and (word in HIGH_VALUE_TERMS or article_count >= 2 or zfreq >= 3.2)
    if "domain terminology" in category or "term" in category:
        return importance >= 4 or article_count >= 2
    if "academic" in category:
        return article_count >= 2 and frequency >= 3 and importance >= 4
    return importance >= 5 and article_count >= 2


def is_high_quality_phrase(item: dict[str, Any]) -> bool:
    word = normalize_entry_word(item)
    frequency = int(item.get("frequency") or 0)
    article_count = int(item.get("article_count") or 0)
    importance = int(item.get("importance") or 0)
    if word in HIGH_VALUE_PHRASES:
        return True
    tokens = [token for token in re.findall(r"[a-z]+", word) if token]
    if len(tokens) > 5:
        return False
    if not tokens:
        return False
    if zipf_frequency:
        scores = [zipf_frequency(token, "en") for token in tokens]
        if min(scores) <= 2.6 and word not in HIGH_VALUE_PHRASES:
            return False
    return importance >= 5 or (frequency >= 3 and article_count >= 2)


def apply_domain_limits(
    grouped: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    limited: dict[str, list[dict[str, Any]]] = defaultdict(list)
    overflow: list[dict[str, Any]] = []
    for domain, entries in grouped.items():
        entries.sort(key=redbook_entry_sort_key, reverse=True)
        limit = DOMAIN_LIMITS.get(domain, 160)
        limited[domain] = entries[:limit]
        overflow.extend(entries[limit:])
    return limited, overflow


def redbook_entry_sort_key(item: dict[str, Any]) -> tuple[float, int, int, int, int]:
    word = normalize_entry_word(item)
    category_priority = _vocabulary_category_priority(item)
    high_value = 1 if word in HIGH_VALUE_TERMS or word in HIGH_VALUE_PHRASES else 0
    return (
        float(item.get("redbook_score") or 0.0),
        high_value,
        category_priority,
        int(item.get("article_count") or 0),
        int(item.get("frequency") or 0),
    )


def clean_category(category: str) -> str:
    c = str(category).lower().strip()
    if c in {"polysemy", "熟词生义"}:
        return "熟词生义"
    if c in {"phrase", "idiomatic expression", "llm vocabulary phrase", "高频短语"}:
        return "高频短语"
    if c in {
        "domain terminology",
        "institutional vocabulary",
        "legal or political vocabulary",
        "领域术语",
        "term",
    }:
        return "领域术语"
    if c in {"academic", "academic vocabulary", "academic/general"}:
        return "学术词汇"
    return "核心词汇"


def render_redbook(seed: dict[str, Any], corpus: dict[str, Any]) -> str:
    metadata = seed.get("metadata", {})
    domains = normalize_redbook_domains(seed.get("domains", {}))

    seed_words = set()
    for domain in domains.values():
        for entry in domain.get("entries", []):
            if entry.get("headword"):
                seed_words.add(entry["headword"].lower().strip())

    corpus_vocab = rank_vocabulary_for_redbook(corpus["vocabulary"], seed_words)

    grouped_corpus: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejected_entries: list[dict[str, Any]] = []
    for item in corpus_vocab:
        classified = classify_redbook_entry(item)
        domain_key = classified["domain"]
        item.update(
            {
                "redbook_domain": domain_key,
                "redbook_score": classified["score"],
                "redbook_confidence": classified["confidence"],
                "redbook_reasons": classified["reasons"],
            }
        )
        if not is_high_quality_redbook_entry(item):
            rejected_entries.append(item)
            continue
        grouped_corpus[domain_key].append(item)

    grouped_corpus, overflow_entries = apply_domain_limits(grouped_corpus)
    rejected_entries.extend(overflow_entries)

    lines = [
        f"# {metadata.get('title', 'GRECIS 考研外刊词汇红宝书')}",
        "",
        metadata.get("subtitle", ""),
        "",
        "## 使用说明",
        "",
        "- 先背每章的熟词生义和固定搭配，再看领域术语。",
        "- 每个词条优先记“考研义”和“误译风险”，不要只背中文对照。",
        "- 例句分为项目例句 and 语料库例句；语料库例句来自本地已抓取文章的短摘录。",
        "- 权威词典释义字段预留给你本地接入的授权词典 API，本文件内置的是学习用简明释义。",
        "",
        "## 快速背诵清单",
        "",
        render_quick_list(domains),
        "",
        "## 目录",
        "",
    ]

    for index, domain in enumerate(domains.values(), start=1):
        lines.append(f"{index}. [{domain['title']}](#{markdown_anchor(domain['title'])})")
    lines.extend(["", "---", ""])

    for domain_key, domain in domains.items():
        seed_entries = []
        for entry in domain.get("entries", []):
            entry_copy = dict(entry)
            entry_copy["is_seed"] = True
            seed_entries.append(entry_copy)

        corpus_entries = []
        for item in grouped_corpus[domain_key]:
            item_copy = dict(item)
            item_copy["is_seed"] = False
            corpus_entries.append(item_copy)

        combined_entries = seed_entries + corpus_entries
        combined_entries.sort(
            key=lambda x: (
                _vocabulary_category_priority(x),
                int(x.get("importance") or 0),
                int(x.get("frequency") or 0),
            ),
            reverse=True,
        )

        lines.extend(
            render_unified_domain(
                domain["title"], domain.get("overview", ""), combined_entries, corpus
            )
        )

    lines.extend(render_sentence_patterns(seed.get("sentence_patterns", []), corpus))
    lines.extend(render_corpus_appendix(corpus, seed_words, rejected_entries))
    lines.extend(render_review_plan())
    return "\n".join(line for line in lines if line is not None)


def markdown_anchor(title: str) -> str:
    normalized = title.strip().lower().replace(" ", "-")
    return "".join(char for char in normalized if char.isalnum() or char in "-_")


def render_quick_list(domains: dict[str, Any]) -> str:
    rows = []
    for domain in domains.values():
        for entry in domain.get("entries", []):
            if entry.get("importance", 0) >= 5:
                rows.append(
                    [
                        entry["headword"],
                        domain["title"],
                        entry.get("chinese", ""),
                        entry.get("risk", ""),
                    ]
                )
    return table(["词条", "领域", "核心义", "先记风险"], rows)


def resolve_vocab_details(item: dict[str, Any]) -> tuple[str, str, str]:
    """Retrieve phonetic symbol, Chinese gloss, and English gloss with caching."""
    word = item.get("headword") or item.get("word")
    phonetic = item.get("phonetic") or ""
    zh_val = item.get("exam") or item.get("chinese") or item.get("gloss") or ""
    en_val = item.get("english") or item.get("english_gloss") or ""

    if not phonetic or not zh_val or not en_val:
        dict_data = query_word(word)
        if not phonetic:
            phonetic = dict_data.get("phonetic") or ""
        if not zh_val:
            zh_val = dict_data.get("zh") or ""
        if not en_val:
            en_val = dict_data.get("en") or ""

    return phonetic, zh_val, en_val


def render_unified_domain(
    title: str, overview: str, entries: list[dict[str, Any]], corpus: dict[str, Any]
) -> list[str]:
    lines = [
        f"## {title}",
        "",
        overview,
        "",
        "| 词条 | 类型 | 词性 | 考研重要度 | 核心义 |",
        "|---|---|---|---|---|",
    ]
    for entry in entries:
        word = entry.get("headword") or entry.get("word")
        category = entry.get("kind") or entry.get("category") or ""
        pos = entry.get("pos") or ""
        importance = stars(entry.get("importance", 0))
        cat_clean = clean_category(category)

        _, zh_val, _ = resolve_vocab_details(entry)
        zh_short = truncate(zh_val, 40)

        lines.append(f"| {word} | {cat_clean} | {pos} | {importance} | {zh_short} |")
    lines.append("")

    for entry in entries:
        lines.extend(render_unified_entry(entry, corpus))
    return lines


def render_unified_entry(item: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    is_seed = item.get("is_seed", False)
    word = item.get("headword") or item.get("word")

    phonetic, zh_val, en_val = resolve_vocab_details(item)
    phonetic_str = f" `[{phonetic}]`" if phonetic else ""

    category = item.get("kind") or item.get("category") or ""
    category_chinese = clean_category(category)
    pos = item.get("pos") or ""
    importance_stars = stars(item.get("importance", 0))

    attr_parts = []
    if pos:
        attr_parts.append(f"`{pos}`")
    if category_chinese:
        attr_parts.append(f"`{category_chinese}`")
    if importance_stars:
        attr_parts.append(f"重要度：{importance_stars}")
    if not is_seed:
        frequency = item.get("frequency", 0)
        article_count = item.get("article_count", 0)
        if frequency:
            attr_parts.append(f"频次：{frequency}次")
        if article_count:
            attr_parts.append(f"文章：{article_count}篇")

    attr_line = " · ".join(attr_parts)
    common_val = item.get("common") or ""

    lines = [
        f"### {word}{phonetic_str}",
        "",
        f"*   **词汇属性**：{attr_line}" if attr_line else None,
        f"*   🎯 **核心考研义**：**{zh_val}**",
    ]

    if common_val:
        lines.append(f"*   🔹 **普通基础义**：{common_val}")
    if en_val:
        lines.append(f"*   🌐 **英英释义**：`{en_val}`")

    risk_val = item.get("risk") or ""
    if risk_val:
        lines.append(f"*   ⚠️ **误译风险**：{risk_val}")

    collocations = item.get("collocations") or []
    if collocations:
        colloc_str = " | ".join(f"`{c}`" for c in collocations)
        lines.append(f"*   💡 **高频搭配**：{colloc_str}")

    contrast = item.get("contrast") or []
    if contrast:
        lines.append("*   👥 **近义辨析**：")
        for c in contrast:
            lines.append(f"    *   `{c['term']}`: {c['note']}")

    examples = item.get("examples") or []
    if examples:
        lines.append("*   📖 **真题/经典例句**：")
        for ex in examples:
            hl_s = highlight_word(ex["sentence"], word)
            lines.append(f"    > {hl_s}")
            if ex.get("zh"):
                lines.append(f"    > *译：{ex['zh']}*")

    example_sentence = item.get("example_sentence") or ""
    if example_sentence:
        hl_s = highlight_word(example_sentence, word)
        lines.append("*   📰 **语料库例句**：")
        lines.append(f"    > {truncate(hl_s, 220)}")
        source = describe_corpus_hit(item)
        lines.append(f"    > *来源：{source}*")

    if not examples and not example_sentence:
        corpus_hits = lookup_corpus_hits(word, corpus)
        if corpus_hits:
            lines.append("*   📰 **语料库例句**：")
            for hit in corpus_hits[:1]:
                hl_s = highlight_word(hit["example_sentence"], word)
                lines.append(f"    > {truncate(hl_s, 220)}")
                source = describe_corpus_hit(hit)
                lines.append(f"    > *来源：{source}*")

    lines.append("")
    lines.append("---")
    lines.append("")
    return [line for line in lines if line is not None]


def lookup_corpus_hits(headword: str, corpus: dict[str, Any]) -> list[dict[str, Any]]:
    key = headword.lower()
    hits = []
    hits.extend(corpus["by_word"].get(key, []))
    hits.extend(corpus["by_expression"].get(key, []))
    return [hit for hit in hits if hit.get("example_sentence")]


def describe_corpus_hit(hit: dict[str, Any]) -> str:
    if hit.get("citation"):
        return hit["citation"]
    if hit.get("sources"):
        return hit["sources"]
    parts = []
    if hit.get("field"):
        parts.append(f"领域 {hit['field']}")
    if hit.get("article_count"):
        parts.append(f"{hit['article_count']} 篇文章")
    if hit.get("frequency"):
        parts.append(f"频次 {hit['frequency']}")
    return "，".join(parts) or "本地语料库"


def render_sentence_patterns(
    seed_patterns: list[dict[str, Any]], corpus: dict[str, Any]
) -> list[str]:
    lines = ["## 句式模板", "", "这些结构优先用于阅读定位：让步、转折、因果、作者态度。", ""]
    for pattern in seed_patterns:
        lines.extend(
            [
                f"### {pattern['pattern']}",
                "",
                f"- 功能：{pattern['function']}",
                f"- 中文：{pattern['chinese']}",
                f"- 重要度：{stars(pattern['importance'])}",
                "",
                f"> {pattern['example']}",
                "",
            ]
        )

    selected = select_sentence_patterns(corpus.get("sentence_patterns", []))
    if selected:
        lines.extend(
            [
                "## 语料驱动句型库",
                "",
                "以下结构由本地规则与 LLM 结果统一归类，并优先选取真题或高质量外刊例句。",
                "频次用于判断常见程度，阅读提示用于快速定位作者真正的论证落点。",
                "",
            ]
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in selected:
            grouped[item["type"]].append(item)

        for pattern_type in sorted(grouped, key=pattern_priority, reverse=True):
            metadata = pattern_metadata(pattern_type)
            lines.extend(
                [
                    f"### {metadata['label']}",
                    "",
                    f"- 核心功能：{metadata['function']}",
                    f"- 阅读提示：{metadata['reading_tip']}",
                    "",
                ]
            )
            for item in grouped[pattern_type]:
                coverage = (
                    f"{int(item.get('frequency') or 0)} 次，"
                    f"覆盖 {int(item.get('article_count') or 0)} 篇文章"
                )
                source = str(item.get("example_source") or "").strip()
                lines.extend(
                    [
                        f"#### {item['pattern']}",
                        "",
                        f"- 语料覆盖：{coverage}",
                        f"- 重要度：{stars(int(item.get('importance') or 3))}",
                    ]
                )
                if source:
                    lines.append(f"- 例句来源：{source}")
                lines.extend(
                    [
                        "",
                        f"> {summarize_sentence(item.get('example_sentence', ''), limit=240)}",
                        "",
                    ]
                )
    return lines


# Corpus entries rendering logic has been unified into render_unified_entry above


def render_corpus_appendix(
    corpus: dict[str, Any],
    seed_words: set[str] | None = None,
    rejected_entries: list[dict[str, Any]] | None = None,
) -> list[str]:
    if seed_words is None:
        seed_words = set()
    rejected_entries = rejected_entries or []
    collocations = select_expression_candidates(corpus["collocations"])[:80]
    review_vocab = select_appendix_vocabulary(corpus, seed_words, rejected_entries)[:120]
    lines = [
        "## 待复核高频核心词",
        "",
        "以下词条未进入正式章节，通常是领域证据不足、章节超额或泛学术属性较强；保留作查漏补缺。",
        "",
        table(
            ["词条", "建议领域", "类型", "频次", "文章数", "保留原因"],
            [
                [
                    item.get("word", ""),
                    item.get("redbook_domain")
                    or map_field_to_domain_key(item.get("field", ""), item.get("word", "")),
                    clean_category(item.get("category", "")),
                    item.get("frequency", 0),
                    item.get("article_count", 0),
                    "; ".join(item.get("redbook_reasons") or []) or "high_frequency",
                ]
                for item in review_vocab
            ],
        ),
        "",
        "## 本地语料补充表达",
        "",
        "以下是本地语料分析识别出的高频表达与固定搭配。",
        "",
        table(
            ["表达", "类型", "含义", "频次", "例句"],
            [
                [
                    item["expression"],
                    item["type"],
                    item.get("meaning", ""),
                    item["frequency"],
                    summarize_sentence(item.get("example_sentence", "")),
                ]
                for item in collocations
            ],
        ),
        "",
    ]
    return lines


def select_appendix_vocabulary(
    corpus: dict[str, Any],
    seed_words: set[str],
    rejected_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for item in rejected_entries:
        word = normalize_entry_word(item)
        if not word or word in seed_words:
            continue
        if is_appendix_worthy(item):
            candidates[word] = dict(item)

    if not candidates:
        for item in rank_vocabulary_for_redbook(corpus.get("vocabulary", []), seed_words):
            word = normalize_entry_word(item)
            if not word or word in seed_words:
                continue
            classified = classify_redbook_entry(item)
            item = dict(item)
            item.update(
                {
                    "redbook_domain": classified["domain"],
                    "redbook_score": classified["score"],
                    "redbook_confidence": classified["confidence"],
                    "redbook_reasons": classified["reasons"],
                }
            )
            if is_appendix_worthy(item):
                candidates[word] = item
    rows = list(candidates.values())
    rows.sort(key=redbook_entry_sort_key, reverse=True)
    return rows


def is_appendix_worthy(item: dict[str, Any]) -> bool:
    word = normalize_entry_word(item)
    if not word or word in LOW_VALUE_REDBOOK_WORDS or word in NOISE_WORDS:
        return False
    if " " in word:
        return is_high_quality_phrase(item)
    if re.search(r"[^a-z0-9'-]", word):
        return False
    frequency = int(item.get("frequency") or 0)
    article_count = int(item.get("article_count") or 0)
    importance = int(item.get("importance") or 0)
    zfreq = zipf_frequency(word, "en") if zipf_frequency else 4.0
    if zfreq <= 2.8 or zfreq >= 5.55:
        return False
    return word in HIGH_VALUE_TERMS or importance >= 5 or article_count >= 3 or frequency >= 8


def rank_vocabulary_for_redbook(
    rows: list[dict[str, Any]], seed_words: set[str] | None = None
) -> list[dict[str, Any]]:
    if seed_words is None:
        seed_words = set()

    filtered = [item for item in rows if is_exportable_vocabulary(item)]
    deduped: dict[str, dict[str, Any]] = {}
    for item in filtered:
        word = str(item.get("word", "")).strip().lower()
        if not word or word in seed_words:
            continue
        if word not in deduped:
            deduped[word] = dict(item)
        else:
            existing = deduped[word]
            # Merge stats
            existing["frequency"] = existing.get("frequency", 0) + item.get("frequency", 0)
            existing["article_count"] = max(
                existing.get("article_count", 0), item.get("article_count", 0)
            )
            existing["importance"] = max(existing.get("importance", 0), item.get("importance", 0))
            if not existing.get("example_sentence") and item.get("example_sentence"):
                existing["example_sentence"] = item["example_sentence"]
            if not existing.get("gloss") and item.get("gloss"):
                existing["gloss"] = item["gloss"]

    filtered = list(deduped.values())
    filtered.sort(
        key=lambda item: (
            _vocabulary_category_priority(item),
            int(item.get("importance") or 0),
            int(item.get("article_count") or 0),
            int(item.get("frequency") or 0),
        ),
        reverse=True,
    )
    return filtered


def _vocabulary_category_priority(item: dict[str, Any]) -> int:
    category = str(item.get("kind") or item.get("category") or "").lower()
    if category == "polysemy" or "熟词" in category:
        return 5
    if "phrase" in category or "短语" in category or "idiom" in category:
        return 4
    if (
        "term" in category
        or "术语" in category
        or "institutional" in category
        or "legal" in category
        or "political" in category
    ):
        return 3
    if "academic" in category or "学术" in category:
        return 2
    return 1


def build_gloss_index(
    vocabulary: list[dict[str, Any]], llm_rows: list[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for entry in vocabulary:
        word = str(entry.get("word", "")).strip().lower()
        if not word:
            continue
        index[word] = {
            "zh": str(entry.get("contextual_meaning") or entry.get("common_meaning") or ""),
            "en_short": str(entry.get("english_gloss") or ""),
            "en_long": str(entry.get("english_gloss") or ""),
            "common": str(entry.get("common_meaning") or ""),
            "exam": str(entry.get("contextual_meaning") or ""),
        }
    for row in llm_rows:
        payload = _load_llm_payload(row.get("llm_json", "{}"))
        for item in payload.get("vocabulary", []):
            if not isinstance(item, dict):
                continue
            lemma = str(item.get("lemma", "")).strip().lower()
            if not lemma:
                continue
            zh = str(item.get("meaning_in_context", "")).strip()
            common = str(item.get("common_meaning", "")).strip()
            exam = str(item.get("why_chinese_students_misunderstand_it", "")).strip()
            index.setdefault(lemma, {})
            entry = index[lemma]
            entry["zh"] = entry.get("zh") or zh
            entry["common"] = entry.get("common") or common
            entry["exam"] = entry.get("exam") or exam
            entry["en_short"] = entry.get("en_short") or _shorten_english(zh or common or lemma)
            entry["en_long"] = entry.get("en_long") or _shorten_english(
                common or zh or lemma, limit=120
            )
    return index


def resolve_gloss(headword: str, entry: dict[str, Any], corpus: dict[str, Any]) -> dict[str, str]:
    key = headword.strip().lower()
    gloss = dict(corpus.get("gloss_index", {}).get(key, {}))
    if not gloss:
        dict_data = query_word(key)
        gloss = {
            "zh": dict_data["zh"] or str(entry.get("chinese", "")),
            "en_short": dict_data["en"] or str(entry.get("english", "")),
            "en_long": dict_data["en"] or str(entry.get("english", "")),
            "common": str(entry.get("common", "")),
            "exam": str(entry.get("exam", "")),
            "phonetic": dict_data["phonetic"] or str(entry.get("phonetic", "")),
        }
    else:
        if not gloss.get("phonetic"):
            dict_data = query_word(key)
            gloss["phonetic"] = dict_data["phonetic"]

    gloss.setdefault("zh", "")
    gloss.setdefault("en_short", "")
    gloss.setdefault("en_long", "")
    gloss.setdefault("common", "")
    gloss.setdefault("exam", "")
    gloss.setdefault("phonetic", "")
    return gloss


def _load_llm_payload(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _shorten_english(text: str, limit: int = 80) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def summarize_sentence(sentence: str, limit: int = 110) -> str:
    text = " ".join(str(sentence).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def select_sentence_patterns(
    rows: list[dict[str, Any]],
    *,
    per_type: int = 4,
    limit: int = 40,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_patterns: set[tuple[str, str]] = set()

    for raw_item in rows:
        item = dict(raw_item)
        canonical = normalize_sentence_pattern_type(
            str(item.get("type", "")),
            str(item.get("function", "")),
        )
        template = infer_sentence_pattern_template(
            str(item.get("example_sentence", "")),
            canonical,
            provided_template=str(item.get("pattern", "")),
        )
        key = (canonical, template.lower())
        if key in seen_patterns:
            continue
        seen_patterns.add(key)
        metadata = pattern_metadata(canonical)
        item.update(
            {
                "type": canonical,
                "label": item.get("label") or metadata["label"],
                "function": item.get("function") or metadata["function"],
                "reading_tip": item.get("reading_tip") or metadata["reading_tip"],
                "pattern": template,
                "example_quality": item.get("example_quality")
                or sentence_example_quality(
                    str(item.get("example_sentence", "")),
                    template=template,
                    source=str(item.get("example_source", "")),
                ),
            }
        )
        buckets[canonical].append(item)

    for pattern_type, items in buckets.items():
        items.sort(
            key=lambda item: (
                1 if item["pattern"] != pattern_metadata(pattern_type)["label"] else 0,
                int(item.get("article_count") or 0),
                int(item.get("frequency") or 0),
                float(item.get("example_quality") or 0.0),
                int(item.get("importance") or 0),
            ),
            reverse=True,
        )

    type_order = sorted(
        (pattern_type for pattern_type in buckets if pattern_type != "other"),
        key=lambda pattern_type: (
            pattern_priority(pattern_type),
            len(buckets[pattern_type]),
        ),
        reverse=True,
    )
    if "other" in buckets:
        type_order.append("other")

    selected: list[dict[str, Any]] = []
    next_index = {pattern_type: 0 for pattern_type in type_order}
    selected_per_type = {pattern_type: 0 for pattern_type in type_order}
    seen_examples: set[str] = set()
    for _round in range(max(per_type, 1)):
        for pattern_type in type_order:
            allowed = 2 if pattern_type == "other" else per_type
            if selected_per_type[pattern_type] >= allowed:
                continue
            candidate = None
            while next_index[pattern_type] < len(buckets[pattern_type]):
                item = buckets[pattern_type][next_index[pattern_type]]
                next_index[pattern_type] += 1
                example_key = " ".join(str(item.get("example_sentence", "")).lower().split())
                if example_key and example_key in seen_examples:
                    continue
                candidate = item
                if example_key:
                    seen_examples.add(example_key)
                break
            if candidate is None:
                continue
            selected.append(candidate)
            selected_per_type[pattern_type] += 1
            if len(selected) >= limit:
                return selected
    return selected


def select_expression_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [item for item in rows if is_exportable_expression(item)]
    selected.sort(
        key=lambda item: (
            1 if item.get("meaning") else 0,
            int(item.get("article_count") or 0),
            int(item.get("frequency") or 0),
        ),
        reverse=True,
    )
    return selected


def _resolve_corpus_gloss(item: dict[str, Any], corpus: dict[str, Any] | None = None) -> str:
    text = item.get("gloss", "") or ""
    if not text and corpus:
        word = str(item.get("word", "")).strip().lower()
        gloss_entry = corpus.get("gloss_index", {}).get(word, {})
        if gloss_entry:
            text = gloss_entry.get("zh", "") or gloss_entry.get("common", "") or ""
    return text


def _resolve_corpus_egloss(item: dict[str, Any], corpus: dict[str, Any] | None = None) -> str:
    text = item.get("english_gloss", "") or ""
    if not text and corpus:
        word = str(item.get("word", "")).strip().lower()
        gloss_entry = corpus.get("gloss_index", {}).get(word, {})
        if gloss_entry:
            text = gloss_entry.get("en_short", "") or gloss_entry.get("en_long", "") or ""
    return text


def render_review_plan() -> list[str]:
    return [
        "## 7 天复习安排",
        "",
        "| 天数 | 任务 |",
        "|---|---|",
        "| Day 1 | 政治法律：issue, hold, find, case, challenge；背 at issue / take issue with。 |",
        "| Day 2 | 经贸金融：acquisition, merger, takeover, capital, yield, regulation。 |",
        "| Day 3 | 学术科技：suggest, indicate, significant, robust, account for, underlie。 |",
        "| Day 4 | 环境气候：emissions, mitigation, adaptation, resilience, biodiversity。 |",
        "| Day 5 | 教育社会心理：school, position, concern, subject, "
        "discipline, bias, drive, move。 |",
        "| Day 6 | 句式模板：while/whereas, rather than, not so much A as B；回看所有例句。 |",
        "| Day 7 | 遮住中文复述英文例句，整理仍会误译的词条。 |",
        "",
    ]

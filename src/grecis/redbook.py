from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .db import CorpusDB
from .export import is_exportable_expression, is_exportable_vocabulary, stars, table, truncate
from .dictionary import query_word

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
        extra_forms = ["took issue with", "takes issue with", "taken issue with", "taking issue with"]
        
    forms = [word_lower] + extra_forms
    forms.sort(key=len, reverse=True)
    
    pattern_parts = []
    for form in forms:
        escaped = re.escape(form)
        if " " in form:
            pattern_parts.append(rf"\b{escaped}\b")
        else:
            pattern_parts.append(rf"\b{escaped}(?:s|es|ed|ing|d|r|er)?\b")
            
    pattern = re.compile(f"(" + "|".join(pattern_parts) + ")", re.IGNORECASE)
    return pattern.sub(r"**\1**", sentence)

DEFAULT_REDBOOK_SEED = "data/redbook_seed.yaml"


def write_redbook(
    db: CorpusDB,
    output_dir: str | Path,
    seed_path: str | Path = DEFAULT_REDBOOK_SEED,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    seed = load_seed(seed_path)
    corpus = build_corpus_index(db)
    markdown = render_redbook(seed, corpus)
    path = output / "GRECIS-考研外刊词汇红宝书.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def load_seed(path: str | Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


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
    if f in {"politics", "law", "politics_law"}:
        return "politics_law"
    if f in {"economics", "business", "economics_business"}:
        return "economics_business"
    if f in {"science", "academic", "science_academic", "academic_science", "science_academic_academic"}:
        return "science_academic"
    if f in {"environment", "climate"}:
        return "environment"
    if f in {"education", "psychology", "sociology", "society", "society_education_psychology"}:
        return "society_education_psychology"
        
    from .nlp import DOMAIN_KEYWORDS
    w = word.strip().lower()
    for domain_name, keywords in DOMAIN_KEYWORDS.items():
        if w in keywords:
            if domain_name in {"politics", "law"}:
                return "politics_law"
            if domain_name == "economics":
                return "economics_business"
            if domain_name == "science":
                return "science_academic"
            if domain_name == "environment":
                return "environment"
            if domain_name in {"education", "psychology", "sociology"}:
                return "society_education_psychology"
                
    return "science_academic"

def clean_category(category: str) -> str:
    c = str(category).lower().strip()
    if c in {"polysemy", "熟词生义"}:
        return "熟词生义"
    if c in {"phrase", "idiomatic expression", "llm vocabulary phrase", "高频短语"}:
        return "高频短语"
    if c in {"domain terminology", "institutional vocabulary", "legal or political vocabulary", "领域术语", "term"}:
        return "领域术语"
    if c in {"academic", "academic vocabulary", "academic/general", "academic/general"}:
        return "学术词汇"
    return "核心词汇"

def render_redbook(seed: dict[str, Any], corpus: dict[str, Any]) -> str:
    metadata = seed.get("metadata", {})
    domains = seed.get("domains", {})
    
    seed_words = set()
    for domain in domains.values():
        for entry in domain.get("entries", []):
            if entry.get("headword"):
                seed_words.add(entry["headword"].lower().strip())
                
    corpus_vocab = rank_vocabulary_for_redbook(corpus["vocabulary"], seed_words)
    
    grouped_corpus: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in corpus_vocab:
        domain_key = map_field_to_domain_key(item.get("field", ""), item["word"])
        grouped_corpus[domain_key].append(item)

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
        
        lines.extend(render_unified_domain(domain["title"], domain.get("overview", ""), combined_entries, corpus))

    lines.extend(render_sentence_patterns(seed.get("sentence_patterns", []), corpus))
    lines.extend(render_corpus_appendix(corpus, seed_words))
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

def render_unified_domain(title: str, overview: str, entries: list[dict[str, Any]], corpus: dict[str, Any]) -> list[str]:
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
        
        lines.append(
            f"| {word} | {cat_clean} | {pos} | {importance} | {zh_short} |"
        )
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

    if corpus["sentence_patterns"]:
        lines.extend(["### 本地语料中识别到的高频句式", ""])
        lines.append(
            table(
                ["类型", "功能", "频次", "例句"],
                [
                    [
                        item["type"],
                        item["function"],
                        item["frequency"],
                        summarize_sentence(item["example_sentence"]),
                    ]
                    for item in select_sentence_patterns(corpus["sentence_patterns"])
                ],
            )
        )
        lines.append("")
    return lines


# Corpus entries rendering logic has been unified into render_unified_entry above


def render_corpus_appendix(corpus: dict[str, Any], seed_words: set[str] | None = None) -> list[str]:
    collocations = select_expression_candidates(corpus["collocations"])[:80]
    lines = [
        "## 本地语料补充表达",
        "",
        "以下是本地语料分析识别出的高频学术表达与固定搭配。",
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
            existing["article_count"] = max(existing.get("article_count", 0), item.get("article_count", 0))
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
    if "term" in category or "术语" in category or "institutional" in category or "legal" in category or "political" in category:
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


def select_sentence_patterns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"concession": 5, "contrast": 5, "causality": 5, "stance": 4, "emphasis": 3}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(
        rows,
        key=lambda row: (
            priority.get(str(row.get("type", "")).lower(), 1),
            row.get("frequency", 0),
        ),
        reverse=True,
    ):
        key = str(item.get("type", "")).lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) >= 5:
            break
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

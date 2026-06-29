from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .db import CorpusDB
from .export import is_exportable_expression, is_exportable_vocabulary, stars, table, truncate

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


def render_redbook(seed: dict[str, Any], corpus: dict[str, Any]) -> str:
    metadata = seed.get("metadata", {})
    domains = seed.get("domains", {})
    lines = [
        f"# {metadata.get('title', 'GRECIS 考研外刊词汇红宝书')}",
        "",
        metadata.get("subtitle", ""),
        "",
        "## 使用说明",
        "",
        "- 先背每章的熟词生义和固定搭配，再看领域术语。",
        "- 每个词条优先记“考研义”和“误译风险”，不要只背中文对照。",
        "- 例句分为项目例句和语料库例句；语料库例句来自本地已抓取文章的短摘录。",
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

    for domain in domains.values():
        lines.extend(render_domain(domain, corpus))

    lines.extend(render_corpus_lexicon(corpus))
    lines.extend(render_sentence_patterns(seed.get("sentence_patterns", []), corpus))
    lines.extend(render_corpus_appendix(corpus))
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


def render_domain(domain: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    lines = [
        f"## {domain['title']}",
        "",
        domain.get("overview", ""),
        "",
        "| 词条 | 类型 | 考研重要度 | 核心义 |",
        "|---|---|---|---|",
    ]
    for entry in domain.get("entries", []):
        lines.append(
            f"| {entry['headword']} | {entry.get('kind', '')} | "
            f"{stars(entry.get('importance', 0))} | {entry.get('chinese', '')} |"
        )
    lines.append("")

    for entry in domain.get("entries", []):
        lines.extend(render_entry(entry, corpus))
    return lines


def render_entry(entry: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    headword = entry["headword"]
    corpus_hits = lookup_corpus_hits(headword, corpus)
    gloss = resolve_gloss(headword, entry, corpus)
    lines = [
        f"### {headword}",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        f"| 类型 | {entry.get('kind', '')} |",
        f"| 词性 | {entry.get('pos', '')} |",
        f"| 考研重要度 | {stars(entry.get('importance', 0))} |",
        f"| 核心中文义 | {gloss['zh'] or entry.get('chinese', '')} |",
        f"| 简明英英义 | {gloss['en_short'] or entry.get('english', '')} |",
        f"| 英英补充 | {gloss['en_long'] or entry.get('english', '')} |",
        "",
        "**常见义**",
        "",
        gloss["common"] or entry.get("common", ""),
        "",
        "**考研义**",
        "",
        gloss["exam"] or entry.get("exam", ""),
        "",
        "**误译风险**",
        "",
        entry.get("risk", ""),
        "",
    ]

    if entry.get("collocations"):
        lines.extend(["**高频搭配**", ""])
        for item in entry["collocations"]:
            lines.append(f"- {item}")
        lines.append("")

    if entry.get("contrast"):
        lines.extend(["**近义辨析**", ""])
        lines.append(
            table(
                ["词/表达", "区别"],
                [[item["term"], item["note"]] for item in entry["contrast"]],
            )
        )
        lines.append("")

    lines.extend(["**例句**", ""])
    for example in entry.get("examples", []):
        lines.append(f"> {example['sentence']}")
        if example.get("zh"):
            lines.append("")
            lines.append(f"释义：{example['zh']}")
        lines.append("")

    if corpus_hits:
        lines.extend(["**本地语料例句**", ""])
        for hit in corpus_hits[:1]:
            lines.append(f"> {truncate(hit['example_sentence'], 220)}")
            source = describe_corpus_hit(hit)
            lines.append("")
            lines.append(f"来源：{source}")
            lines.append("")

    lines.extend(["---", ""])
    return lines


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


def render_corpus_lexicon(corpus: dict[str, Any]) -> list[str]:
    vocabulary = rank_vocabulary_for_redbook(corpus["vocabulary"])[:80]
    lines = [
        "## 语料库新增核心词条",
        "",
        (
            "本节来自本地考研真题与外刊语料的自动分析，"
            "优先保留熟词生义、领域术语和 LLM 判定的高价值词条。"
        ),
        "",
    ]
    if not vocabulary:
        lines.extend(["暂无新增词条。", ""])
        return lines

    for item in vocabulary:
        lines.extend(render_corpus_entry(item))
    return lines


def render_corpus_entry(item: dict[str, Any]) -> list[str]:
    lines = [
        f"### {item['word']}",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        f"| 领域 | {item.get('field', '')} |",
        f"| 类别 | {item.get('category', '')} |",
        f"| 语料频次 | {item.get('frequency', 0)} |",
        f"| 覆盖文章 | {item.get('article_count', 0)} |",
        f"| 重要度 | {stars(item.get('importance', 0))} |",
        f"| 词条释义 | {item.get('gloss', '')} |",
        f"| 英英释义 | {item.get('english_gloss', '')} |",
        "",
    ]
    example = item.get("example_sentence", "")
    if example:
        lines.extend(
            [
                "**可溯源例句**",
                "",
                f"> {truncate(example, 220)}",
                "",
                f"来源：{describe_corpus_hit(item)}",
                "",
            ]
        )
    lines.extend(["---", ""])
    return lines


def render_corpus_appendix(corpus: dict[str, Any]) -> list[str]:
    vocabulary = rank_vocabulary_for_redbook(corpus["vocabulary"])[80:140]
    collocations = select_expression_candidates(corpus["collocations"])[:80]
    lines = [
        "## 本地语料补充词条",
        "",
        "以下是未进入主章节的补充候选，只保留少量高价值项。",
        "",
        table(
            ["词", "领域", "类别", "频次", "文章数", "词义"],
            [
                [
                    item["word"],
                    item["field"],
                    item["category"],
                    item["frequency"],
                    item["article_count"],
                    item.get("gloss", ""),
                ]
                for item in vocabulary
            ],
        ),
        "",
        "## 本地语料补充表达",
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


def rank_vocabulary_for_redbook(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = [item for item in rows if is_exportable_vocabulary(item)]
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
    category = str(item.get("category", ""))
    if category == "polysemy":
        return 5
    if category in {"domain terminology", "institutional vocabulary"}:
        return 4
    if "llm" in category:
        return 3
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
        gloss = {
            "zh": str(entry.get("chinese", "")),
            "en_short": str(entry.get("english", "")),
            "en_long": str(entry.get("english", "")),
            "common": str(entry.get("common", "")),
            "exam": str(entry.get("exam", "")),
        }
    gloss.setdefault("zh", "")
    gloss.setdefault("en_short", "")
    gloss.setdefault("en_long", "")
    gloss.setdefault("common", "")
    gloss.setdefault("exam", "")
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

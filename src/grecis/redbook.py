from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .db import CorpusDB
from .export import stars, table, truncate

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

    by_word = defaultdict(list)
    for item in vocabulary:
        by_word[item["word"].lower()].append(item)

    by_expression = defaultdict(list)
    for item in collocations:
        by_expression[item["expression"].lower()].append(item)

    return {
        "vocabulary": vocabulary,
        "collocations": collocations,
        "polysemy": polysemy,
        "sentence_patterns": sentence_patterns,
        "by_word": by_word,
        "by_expression": by_expression,
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
    lines = [
        f"### {headword}",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        f"| 类型 | {entry.get('kind', '')} |",
        f"| 词性 | {entry.get('pos', '')} |",
        f"| 考研重要度 | {stars(entry.get('importance', 0))} |",
        f"| 核心中文义 | {entry.get('chinese', '')} |",
        f"| 简明英英义 | {entry.get('english', '')} |",
        f"| 常见义 | {entry.get('common', '')} |",
        f"| 考研义 | {entry.get('exam', '')} |",
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
        for hit in corpus_hits[:2]:
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
        lines.extend(["### 本地语料中识别到的句式", ""])
        lines.append(
            table(
                ["类型", "功能", "频次", "例句"],
                [
                    [
                        item["type"],
                        item["function"],
                        item["frequency"],
                        truncate(item["example_sentence"], 180),
                    ]
                    for item in corpus["sentence_patterns"]
                ],
            )
        )
        lines.append("")
    return lines


def render_corpus_appendix(corpus: dict[str, Any]) -> list[str]:
    vocabulary = [
        item
        for item in corpus["vocabulary"]
        if item["category"] in {"polysemy", "domain terminology"}
    ][:80]
    collocations = [item for item in corpus["collocations"] if item.get("meaning")][:80]
    lines = [
        "## 本地语料新增词条",
        "",
        "以下来自本地数据库统计，可作为下一轮人工精选或 LLM 深度释义的候选。",
        "",
        table(
            ["词", "领域", "类别", "频次", "文章数", "例句"],
            [
                [
                    item["word"],
                    item["field"],
                    item["category"],
                    item["frequency"],
                    item["article_count"],
                    truncate(item.get("example_sentence", ""), 140),
                ]
                for item in vocabulary
            ],
        ),
        "",
        "## 本地语料新增表达",
        "",
        table(
            ["表达", "类型", "含义", "频次", "例句"],
            [
                [
                    item["expression"],
                    item["type"],
                    item.get("meaning", ""),
                    item["frequency"],
                    truncate(item.get("example_sentence", ""), 140),
                ]
                for item in collocations
            ],
        ),
        "",
    ]
    return lines


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

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .db import CorpusDB


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or "untitled"


def write_markdown_report(db: CorpusDB, output_dir: str | Path) -> None:
    output = Path(output_dir)
    article_dir = output / "articles"
    fields_dir = output / "fields"
    article_dir.mkdir(parents=True, exist_ok=True)
    fields_dir.mkdir(parents=True, exist_ok=True)

    reports = db.fetch_report_rows()
    vocabulary = db.aggregate_vocabulary()
    collocations = db.aggregate_collocations()

    for report in reports:
        article = report["article"]
        path = article_dir / f"{slugify(article['id'] + '-' + article['title'])}.md"
        path.write_text(render_article(report), encoding="utf-8")

    for field, rows in group_by(vocabulary, "field").items():
        (fields_dir / f"{slugify(field)}.md").write_text(
            render_field_vocabulary(field, rows), encoding="utf-8"
        )

    (output / "expressions.md").write_text(render_expressions(collocations), encoding="utf-8")
    (output / "index.md").write_text(
        render_index(reports, vocabulary, collocations), encoding="utf-8"
    )
    write_anki(db, output.parent / "anki" / "grecis_cards.tsv")


def render_article(report: dict[str, Any]) -> str:
    article = report["article"]
    analysis_field = article.get("analysis_field") or article.get("field") or "unknown"
    lines = [
        f"# {article['title']}",
        "",
        "## 基本信息",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        f"| 来源 | {article['source']} |",
        f"| URL | {article['url'] or '-'} |",
        f"| 日期 | {article['published_at'] or '-'} |",
        f"| 领域 | {analysis_field} |",
        f"| 难度 | {article.get('difficulty') or '-'} / 10 |",
        f"| 考研价值 | {article.get('exam_value') or '-'} / 10 |",
        "",
        "## 高频词",
        "",
        table(
            ["词", "类别", "频次", "重要度"],
            [
                [item["word"], item["category"], item["frequency"], stars(item["importance"])]
                for item in report["vocabulary"][:25]
            ],
        ),
        "",
        "## 熟词生义",
        "",
    ]
    if report["polysemy"]:
        for item in report["polysemy"]:
            lines.extend(
                [
                    f"### {item['word']}",
                    "",
                    f"- 常见义：{item['ordinary_meaning']}",
                    f"- 文中义：{item['contextual_meaning']}",
                    f"- 风险：{item['exam_risk']}",
                    "",
                    f"> {item['sentence']}",
                    "",
                ]
            )
    else:
        lines.extend(["暂无自动识别结果。", ""])

    lines.extend(
        [
            "## 高频表达",
            "",
            table(
                ["表达", "类型", "频次", "重要度"],
                [
                    [item["expression"], item["type"], item["frequency"], stars(item["importance"])]
                    for item in report["collocations"][:25]
                ],
            ),
            "",
            "## 句式与论证结构",
            "",
        ]
    )
    if report["sentence_patterns"]:
        for item in report["sentence_patterns"]:
            lines.extend(
                [
                    f"### {item['function']}",
                    "",
                    f"- 类型：{item['type']}",
                    f"- 重要度：{stars(item['importance'])}",
                    "",
                    f"> {item['sentence']}",
                    "",
                ]
            )
    else:
        lines.extend(["暂无自动识别结果。", ""])

    llm_json = article.get("llm_json")
    if llm_json and llm_json != "{}":
        lines.extend(
            [
                "## LLM 分析",
                "",
                "```json",
                json.dumps(json.loads(llm_json), ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )

    lines.extend(["## 原文", "", article["text"], ""])
    return "\n".join(lines)


def render_field_vocabulary(field: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# {field}",
        "",
        "## 领域词汇",
        "",
        table(
            ["词", "词形", "类别", "频次", "文章数", "重要度"],
            [
                [
                    item["word"],
                    item["lemma"],
                    item["category"],
                    item["frequency"],
                    item["article_count"],
                    stars(item["importance"]),
                ]
                for item in rows
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def render_expressions(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "# Expressions",
            "",
            table(
                ["表达", "类型", "频次", "文章数", "重要度"],
                [
                    [
                        item["expression"],
                        item["type"],
                        item["frequency"],
                        item["article_count"],
                        stars(item["importance"]),
                    ]
                    for item in rows
                ],
            ),
            "",
        ]
    )


def render_index(
    reports: list[dict[str, Any]],
    vocabulary: list[dict[str, Any]],
    collocations: list[dict[str, Any]],
) -> str:
    article_rows = []
    for report in reports:
        article = report["article"]
        article_rows.append(
            [
                article["title"],
                article["source"],
                article.get("analysis_field") or article["field"],
                article.get("difficulty") or "-",
                article.get("exam_value") or "-",
            ]
        )
    return "\n".join(
        [
            "# GRECIS Index",
            "",
            f"- 文章数：{len(reports)}",
            f"- 词条数：{len(vocabulary)}",
            f"- 表达数：{len(collocations)}",
            "",
            "## Articles",
            "",
            table(["标题", "来源", "领域", "难度", "考研价值"], article_rows),
            "",
        ]
    )


def write_anki(db: CorpusDB, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = db.aggregate_vocabulary()
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t")
        writer.writerow(["front", "back", "tags"])
        for item in rows:
            front = item["word"]
            back = (
                f"Field: {item['field']}<br>"
                f"Category: {item['category']}<br>"
                f"Frequency: {item['frequency']}<br>"
                f"Importance: {stars(item['importance'])}"
            )
            writer.writerow(
                [front, back, f"grecis {item['field']} {item['category'].replace(' ', '_')}"]
            )


def table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "暂无数据。"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def stars(value: int | float | None) -> str:
    count = int(value or 0)
    return "★" * max(0, min(count, 5))


def group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return dict(grouped)

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from wordfreq import zipf_frequency
except ImportError:  # pragma: no cover
    zipf_frequency = None

from .db import CorpusDB

LOW_VALUE_EXPRESSIONS = {
    "you can",
    "she say",
    "she said",
    "you know",
    "last year",
    "last week",
    "year ago",
    "people who",
    "those who",
    "what you",
    "what they",
    "when they",
    "when you",
    "because they",
    "how much",
    "about how",
    "said they",
    "they can",
    "they had",
    "each other",
}

COMMON_PHRASE_WHITELIST = {
    "account for",
    "at issue",
    "at stake",
    "be subject to",
    "make the case for",
    "result in",
    "take issue with",
    "lead to",
    "in effect",
}


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
    polysemy = db.aggregate_polysemy()
    sentence_patterns = db.aggregate_sentence_patterns()

    for report in reports:
        article = report["article"]
        path = article_dir / f"{slugify(article['id'] + '-' + article['title'])}.md"
        path.write_text(render_article(report), encoding="utf-8")

    for field, rows in group_by(vocabulary, "field").items():
        (fields_dir / f"{slugify(field)}.md").write_text(
            render_field_vocabulary(field, rows), encoding="utf-8"
        )

    (output / "expressions.md").write_text(render_expressions(collocations), encoding="utf-8")
    (output / "polysemy.md").write_text(render_polysemy(polysemy), encoding="utf-8")
    (output / "sentence-patterns.md").write_text(
        render_sentence_patterns(sentence_patterns), encoding="utf-8"
    )
    (output / "index.md").write_text(
        render_index(reports, vocabulary, collocations, polysemy), encoding="utf-8"
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
            ["词", "类别", "频次", "重要度", "例句"],
            [
                [
                    item["word"],
                    item["category"],
                    item["frequency"],
                    stars(item["importance"]),
                    truncate(item.get("example_sentence", ""), 120),
                ]
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
                ["表达", "类型", "含义", "频次", "重要度", "例句"],
                [
                    [
                        item["expression"],
                        item["type"],
                        item.get("meaning", ""),
                        item["frequency"],
                        stars(item["importance"]),
                        truncate(item.get("example_sentence", ""), 120),
                    ]
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
            ["词", "词形", "类别", "频次", "文章数", "重要度", "原文例句"],
            [
                [
                    item["word"],
                    item["lemma"],
                    item["category"],
                    item["frequency"],
                    item["article_count"],
                    stars(item["importance"]),
                    truncate(item.get("example_sentence", ""), 120),
                ]
                for item in rows
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def render_expressions(rows: list[dict[str, Any]]) -> str:
    rows = [item for item in rows if is_exportable_expression(item)]
    return "\n".join(
        [
            "# Expressions",
            "",
            table(
                ["表达", "类型", "含义", "频次", "文章数", "重要度", "例句"],
                [
                    [
                        item["expression"],
                        item["type"],
                        item.get("meaning", ""),
                        item["frequency"],
                        item["article_count"],
                        stars(item["importance"]),
                        truncate(item.get("example_sentence", ""), 140),
                    ]
                    for item in rows
                ],
            ),
            "",
        ]
    )


def is_exportable_expression(item: dict[str, Any]) -> bool:
    expression = str(item.get("expression", ""))
    normalized = expression.lower().strip()
    if normalized in LOW_VALUE_EXPRESSIONS:
        return False
    expression_type = str(item.get("type", ""))
    frequency = int(item.get("frequency") or 0)
    article_count = int(item.get("article_count") or 0)
    if normalized in COMMON_PHRASE_WHITELIST:
        return True
    if any(char.isdigit() for char in normalized):
        return False
    tokens = [token for token in normalized.split() if token]
    if len(tokens) >= 2 and zipf_frequency:
        token_scores = [zipf_frequency(token, "en") for token in tokens]
        common_token_count = sum(score >= 5.5 for score in token_scores)
        if expression_type == "2-gram":
            if frequency >= 8 and article_count >= 2 and min(token_scores) < 5.2:
                return True
            if frequency >= 12 and article_count >= 4 and common_token_count < len(tokens):
                return True
            return False
        if expression_type == "3-gram":
            if frequency >= 4 and article_count >= 2 and min(token_scores) < 5.2:
                return True
            return False
    if item.get("meaning"):
        return expression_type not in {"2-gram", "3-gram"} and frequency >= 2
    if expression_type == "2-gram":
        return frequency >= 8 and article_count >= 2 and len(expression) >= 10
    if expression_type == "3-gram":
        return frequency >= 4 and article_count >= 2
    return frequency >= 3


_GAOKAO_3500_WORDS: set[str] | None = None

def load_gaokao_3500() -> set[str]:
    global _GAOKAO_3500_WORDS
    if _GAOKAO_3500_WORDS is not None:
        return _GAOKAO_3500_WORDS
    
    _GAOKAO_3500_WORDS = set()
    path = Path("data/gaokao_3500.txt")
    if not path.exists():
        return _GAOKAO_3500_WORDS
        
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('[') and line.endswith(']'):
                continue
            if any('\u4e00' <= c <= '\u9fff' for c in line):
                continue
            words_in_line = re.findall(r"[A-Za-z]+", line)
            for w in words_in_line:
                w_clean = w.lower().strip()
                if len(w_clean) > 1:
                    _GAOKAO_3500_WORDS.add(w_clean)
                elif w_clean in {'a', 'i'}:
                    _GAOKAO_3500_WORDS.add(w_clean)
    except Exception:
        pass
    return _GAOKAO_3500_WORDS


COMMON_NAMES_AND_PLACES = {
    # Names
    "john", "mary", "james", "charles", "robert", "william", "david", "richard", "joseph", 
    "thomas", "donald", "paul", "mark", "george", "steven", "brian", "kevin", "edward", 
    "biden", "trump", "obama", "bush", "clinton", "reagan", "carter", "ford", "nixon", 
    "kennedy", "eisenhower", "truman", "roosevelt", "hoover", "coolidge", "harding", 
    "wilson", "taft", "mckinley", "cleveland", "harrison", "arthur", "garfield", "hayes", 
    "grant", "johnson", "lincoln", "buchanan", "pierce", "fillmore", "taylor", "polk", 
    "tyler", "jackson", "adams", "jefferson", "washington", "smith", "jones", "miller", 
    "davis", "garcia", "rodriguez", "wilson", "martinez", "anderson", "taylor", "thomas", 
    "hernandez", "moore", "martin", "jackson", "thompson", "white", "lopez", "lee", 
    "gonzalez", "harris", "clark", "lewis", "robinson", "walker", "perez", "hall", 
    "young", "allen", "musk", "bezos", "jobs", "gates", "zuckerberg", "cook", "nadella", 
    "pichai", "altman", "boris", "theresa", "angela", "emmanuel", "macron", "putin", "xi",
    # Places & Countries
    "china", "america", "britain", "england", "london", "europe", "asia", "africa", 
    "france", "germany", "italy", "japan", "india", "canada", "australia", "paris", 
    "berlin", "tokyo", "beijing", "washington", "new york", "york", "boston", "chicago", 
    "california", "texas", "florida", "silicon", "valley", "russia", "uk", "usa", "us",
    # Months & Days
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", 
    "january", "february", "march", "april", "may", "june", "july", "august", 
    "september", "october", "november", "december",
}

def is_proper_noun_or_name(word: str, example_sentence: str) -> bool:
    if word in COMMON_NAMES_AND_PLACES:
        return True
        
    if example_sentence:
        pattern = r"\b" + re.escape(word) + r"(?:s|es|ed|ing|d)?\b"
        match = re.search(pattern, example_sentence, re.IGNORECASE)
        if match:
            matched_str = match.group(0)
            start_index = example_sentence.find(matched_str)
            if matched_str[0].isupper() and not matched_str.isupper() and start_index > 0:
                return True
    return False

def is_uncommon_abbreviation(word: str, example_sentence: str) -> bool:
    abbreviation_whitelist = {"gdp", "ai", "ceo", "r&d", "rd", "it", "pr", "pc", "diy", "dna", "rna", "cpu", "covid"}
    if word in abbreviation_whitelist:
        return False
        
    if example_sentence:
        pattern = r"\b" + re.escape(word) + r"(?:s|es|ed|ing|d)?\b"
        match = re.search(pattern, example_sentence, re.IGNORECASE)
        if match:
            matched_str = match.group(0)
            if matched_str.isupper() and len(matched_str) >= 2:
                return True
                
    if "." in word or (len(word) <= 3 and not any(c in "aeiouy" for c in word)):
        return True
        
    return False

def is_uncommon_professional_term(word: str) -> bool:
    try:
        from .nlp import DOMAIN_KEYWORDS
        domain_words = set()
        for keywords in DOMAIN_KEYWORDS.values():
            domain_words.update(keywords)
    except Exception:
        domain_words = set()
        
    if word in domain_words:
        return False
        
    if zipf_frequency:
        freq = zipf_frequency(word, "en")
        if freq > 0 and freq < 2.5:
            return True
            
    return False

def is_exportable_vocabulary(item: dict[str, Any]) -> bool:
    word = str(item.get("word", "")).strip().lower()
    category = str(item.get("category", "")).lower()
    kind = str(item.get("kind", "")).lower()
    
    if "polysemy" in category or "熟词" in category or "polysemy" in kind or "熟词" in kind:
        return True
        
    if not word:
        return False
        
    if word in {"can", "people", "thing", "make", "good", "big", "small"}:
        return False
        
    # Gaokao 3500 filter
    gaokao_words = load_gaokao_3500()
    if word in gaokao_words:
        return False
        
    # Proper nouns/names filter
    if is_proper_noun_or_name(word, item.get("example_sentence", "")):
        return False
        
    # Uncommon abbreviations filter
    if is_uncommon_abbreviation(word, item.get("example_sentence", "")):
        return False
        
    # Uncommon professional terms filter
    if is_uncommon_professional_term(word):
        return False
        
    # Zipf high frequency filter
    if zipf_frequency and zipf_frequency(word, "en") >= 5.5:
        return False
        
    return int(item.get("importance") or 0) >= 4 or int(item.get("article_count") or 0) >= 2


def render_polysemy(rows: list[dict[str, Any]]) -> str:
    lines = ["# Polysemy", "", "## 熟词生义风险词", ""]
    lines.append(
        table(
            ["词", "常见义", "文中高频义", "文章数", "例句", "来源"],
            [
                [
                    item["word"],
                    item["ordinary_meaning"],
                    item["contextual_meaning"],
                    item["article_count"],
                    truncate(item["example_sentence"], 140),
                    item["sources"],
                ]
                for item in rows
            ],
        )
    )
    lines.append("")
    return "\n".join(lines)


def render_sentence_patterns(rows: list[dict[str, Any]]) -> str:
    lines = ["# Sentence Patterns", "", "## 句式与论证功能", ""]
    lines.append(
        table(
            ["类型", "功能", "频次", "重要度", "例句"],
            [
                [
                    item["type"],
                    item["function"],
                    item["frequency"],
                    stars(item["importance"]),
                    truncate(item["example_sentence"], 160),
                ]
                for item in rows
            ],
        )
    )
    lines.append("")
    return "\n".join(lines)


def render_index(
    reports: list[dict[str, Any]],
    vocabulary: list[dict[str, Any]],
    collocations: list[dict[str, Any]],
    polysemy: list[dict[str, Any]],
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
            f"- 熟词生义词条数：{len(polysemy)}",
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
                f"Importance: {stars(item['importance'])}<br>"
                f"Example: {item.get('example_sentence', '')}"
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


def truncate(value: str | None, limit: int) -> str:
    if not value:
        return ""
    normalized = str(value).replace("\n", " ").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def stars(value: int | float | None) -> str:
    count = int(value or 0)
    return "★" * max(0, min(count, 5))


def group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return dict(grouped)

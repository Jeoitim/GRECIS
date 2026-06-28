from __future__ import annotations

import argparse
import os
from pathlib import Path

from .db import ensure_db, upsert_articles
from .export import write_markdown_report
from .ingest import fetch_url, load_jsonl
from .llm import LLMAnalyzer
from .nlp import analyze_article

DEFAULT_DB = "data/grecis.sqlite"
DEFAULT_OUTPUT = "output/markdown"
SAMPLE_JSONL = "data/sample_articles.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grecis")
    parser.add_argument("--db", default=os.getenv("GRECIS_DB_PATH", DEFAULT_DB))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create local directories and SQLite schema.")

    ingest_jsonl = subparsers.add_parser("ingest-jsonl", help="Import articles from JSONL.")
    ingest_jsonl.add_argument("path")

    ingest_url = subparsers.add_parser("ingest-url", help="Fetch and import one web article.")
    ingest_url.add_argument("url")
    ingest_url.add_argument("--source", default="web")

    analyze = subparsers.add_parser("analyze", help="Analyze imported articles.")
    analyze.add_argument("--article-id", default="all")
    analyze.add_argument("--use-llm", action="store_true")

    export = subparsers.add_parser("export", help="Export Markdown and Anki files.")
    export.add_argument("--out", default=os.getenv("GRECIS_OUTPUT_DIR", DEFAULT_OUTPUT))

    demo = subparsers.add_parser("run-demo", help="Run init, sample ingest, analysis, and export.")
    demo.add_argument("--out", default=os.getenv("GRECIS_OUTPUT_DIR", DEFAULT_OUTPUT))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = ensure_db(args.db)

    if args.command == "init":
        Path("data").mkdir(exist_ok=True)
        Path("output").mkdir(exist_ok=True)
        print(f"Initialized database: {args.db}")
        return 0

    if args.command == "ingest-jsonl":
        articles = load_jsonl(args.path)
        ids = upsert_articles(db, articles)
        print(f"Imported {len(ids)} articles.")
        return 0

    if args.command == "ingest-url":
        article = fetch_url(args.url, source=args.source)
        article_id = db.upsert_article(article)
        print(f"Imported {article_id}: {article.title}")
        return 0

    if args.command == "analyze":
        analyzer = LLMAnalyzer.from_env() if args.use_llm else None
        articles = db.list_articles()
        if args.article_id != "all":
            article = db.get_article(args.article_id)
            articles = [article] if article else []
        for article in articles:
            llm_payload = analyzer.analyze(article) if analyzer else {}
            result = analyze_article(article, llm_payload=llm_payload)
            db.save_analysis(result)
            print(
                f"Analyzed {result.article_id}: field={result.field}, "
                f"difficulty={result.difficulty}, exam_value={result.exam_value}"
            )
        print(f"Analyzed {len(articles)} articles.")
        return 0

    if args.command == "export":
        write_markdown_report(db, args.out)
        print(f"Exported reports to {args.out}")
        return 0

    if args.command == "run-demo":
        sample = Path(SAMPLE_JSONL)
        if not sample.exists():
            raise FileNotFoundError(f"Sample file not found: {sample}")
        ids = upsert_articles(db, load_jsonl(sample))
        print(f"Imported {len(ids)} sample articles.")
        for article in db.list_articles():
            result = analyze_article(article)
            db.save_analysis(result)
            print(f"Analyzed {result.article_id}: field={result.field}")
        write_markdown_report(db, args.out)
        print(f"Demo exported reports to {args.out}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

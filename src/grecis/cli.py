from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .db import ensure_db, upsert_articles
from .export import write_markdown_report
from .ingest import fetch_url, iter_fetch_source_articles, load_exam_corpus, load_jsonl
from .llm import LLMAnalyzer
from .nlp import analyze_article
from .pastpapers import import_pastpapers, summarize_import
from .redbook import write_redbook
from .topics import exam_topic_queries

DEFAULT_DB = "data/grecis.sqlite"
DEFAULT_OUTPUT = "output/markdown"
SAMPLE_JSONL = "data/sample_articles.jsonl"
SECOND_TIER_SOURCES = {
    "the christian science monitor",
    "the guardian",
    "the atlantic",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grecis")
    parser.add_argument("--config", default=None, help="YAML or JSON config path.")
    parser.add_argument("--db", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create local directories and SQLite schema.")

    ingest_jsonl = subparsers.add_parser("ingest-jsonl", help="Import articles from JSONL.")
    ingest_jsonl.add_argument("path")

    ingest_exam = subparsers.add_parser("ingest-exam", help="Import local Kaoyan passages.")
    ingest_exam.add_argument("path")
    ingest_exam.add_argument("--source", default="kaoyan_exam")

    ingest_pastpapers = subparsers.add_parser(
        "ingest-pastpapers", help="Import Kaoyan papers from pastpapers.cn."
    )
    ingest_pastpapers.add_argument("--limit", type=int, default=None)

    ingest_url = subparsers.add_parser("ingest-url", help="Fetch and import one web article.")
    ingest_url.add_argument("url")
    ingest_url.add_argument("--source", default="web")

    fetch_sources = subparsers.add_parser(
        "fetch-sources", help="Fetch articles from configured feeds."
    )
    fetch_sources.add_argument("--source", default="all", help="Source name or 'all'.")
    fetch_sources.add_argument("--limit", type=int, default=None, help="Override per-source limit.")

    analyze = subparsers.add_parser("analyze", help="Analyze imported articles.")
    analyze.add_argument("--article-id", default="all")
    analyze.add_argument("--use-llm", action="store_true")

    curate = subparsers.add_parser("curate-corpus", help="Remove low-value analyzed articles.")
    curate.add_argument("--min-exam-value", type=float, default=None)
    curate.add_argument("--min-difficulty", type=float, default=None)
    curate.add_argument("--dry-run", action="store_true")

    export = subparsers.add_parser("export", help="Export Markdown and Anki files.")
    export.add_argument("--out", default=None)

    redbook = subparsers.add_parser("export-redbook", help="Export a red-book style review guide.")
    redbook.add_argument("--out", default=None)
    redbook.add_argument("--seed", default="data/redbook_seed.yaml")

    update = subparsers.add_parser("update-corpus", help="Fetch, analyze, and export in one run.")
    update.add_argument("--source", default="all")
    update.add_argument("--limit", type=int, default=None)
    update.add_argument("--use-llm", action="store_true")
    update.add_argument("--out", default=None)
    update.add_argument("--redbook-out", default=None)

    build_corpus = subparsers.add_parser(
        "build-corpus", help="Build the prioritized Kaoyan review corpus end to end."
    )
    build_corpus.add_argument("--second-tier-limit", type=int, default=100)
    build_corpus.add_argument("--third-tier-limit", type=int, default=20)
    build_corpus.add_argument("--skip-pastpapers", action="store_true")
    build_corpus.add_argument("--refresh-pastpapers", action="store_true")
    build_corpus.add_argument("--exam-topic-limit", type=int, default=24)
    build_corpus.add_argument("--use-llm", action="store_true")
    build_corpus.add_argument("--out", default=None)
    build_corpus.add_argument("--redbook-out", default=None)

    demo = subparsers.add_parser("run-demo", help="Run init, sample ingest, analysis, and export.")
    demo.add_argument("--out", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    db_path = args.db or config.database.path or DEFAULT_DB
    db = ensure_db(db_path)

    if args.command == "init":
        Path("data").mkdir(exist_ok=True)
        Path("output").mkdir(exist_ok=True)
        print(f"Initialized database: {db_path}")
        return 0

    if args.command == "ingest-jsonl":
        articles = load_jsonl(args.path)
        ids = upsert_articles(db, articles)
        print(f"Imported {len(ids)} articles.")
        return 0

    if args.command == "ingest-exam":
        articles = load_exam_corpus(args.path, source_name=args.source)
        ids = upsert_articles(db, articles)
        print(f"Imported {len(ids)} exam passages.")
        return 0

    if args.command == "ingest-pastpapers":
        articles = import_pastpapers(limit=args.limit)
        ids = upsert_articles(db, articles)
        summary = summarize_import(articles)
        print(f"Imported {len(ids)} pastpapers.cn reading passages.")
        print(f"Papers: {', '.join(summary['papers'])}")
        return 0

    if args.command == "ingest-url":
        article = fetch_url(args.url, source=args.source, crawler=config.crawler)
        article_id = db.upsert_article(article)
        print(f"Imported {article_id}: {article.title}")
        return 0

    if args.command == "fetch-sources":
        imported = fetch_configured_sources(db, config, source_name=args.source, limit=args.limit)
        print(f"Imported {imported} fetched articles.")
        return 0

    if args.command == "analyze":
        count = analyze_articles(db, config, use_llm=args.use_llm, article_id=args.article_id)
        print(f"Analyzed {count} articles.")
        return 0

    if args.command == "curate-corpus":
        min_exam = args.min_exam_value or config.crawler.min_exam_value
        min_diff = args.min_difficulty or config.crawler.min_difficulty
        article_ids = db.low_quality_article_ids(
            min_exam, min_diff, config.crawler.min_quality_score
        )
        if args.dry_run:
            print(f"Would remove {len(article_ids)} low-value articles.")
        else:
            removed = db.delete_articles(article_ids)
            print(f"Removed {removed} low-value articles.")
        return 0

    if args.command == "export":
        out = args.out or config.output.markdown_dir or DEFAULT_OUTPUT
        write_markdown_report(db, out)
        print(f"Exported reports to {out}")
        return 0

    if args.command == "export-redbook":
        out = args.out or config.output.redbook_dir
        path = write_redbook(db, out, seed_path=args.seed)
        print(f"Exported redbook to {path}")
        return 0

    if args.command == "update-corpus":
        imported = fetch_configured_sources(db, config, source_name=args.source, limit=args.limit)
        print(f"Imported {imported} fetched articles.")
        count = analyze_articles(db, config, use_llm=args.use_llm)
        print(f"Analyzed {count} articles.")
        out = args.out or config.output.markdown_dir or DEFAULT_OUTPUT
        write_markdown_report(db, out)
        print(f"Exported reports to {out}")
        redbook_out = args.redbook_out or config.output.redbook_dir
        path = write_redbook(db, redbook_out)
        print(f"Exported redbook to {path}")
        return 0

    if args.command == "build-corpus":
        existing_exam_count = _count_exam_articles(db)
        if not args.skip_pastpapers and (args.refresh_pastpapers or existing_exam_count == 0):
            articles = import_pastpapers()
            ids = upsert_articles(db, articles)
            print(f"Imported {len(ids)} pastpapers.cn reading passages.")
        elif existing_exam_count:
            print(f"Using {existing_exam_count} existing exam reading passages.")

        topic_queries = exam_topic_queries(db.list_articles(), limit=args.exam_topic_limit)
        if topic_queries:
            print(f"Expanded source searches with {len(topic_queries)} exam-derived topics.")
            _apply_exam_topic_queries(config, topic_queries)

        second_tier = [
            source.name
            for source in config.sources
            if source.enabled and source.name.lower() in SECOND_TIER_SOURCES
        ]
        third_tier = [
            source.name
            for source in config.sources
            if source.enabled and source.name.lower() not in SECOND_TIER_SOURCES
        ]
        imported = 0
        for source_name in second_tier:
            imported += fetch_configured_sources(
                db, config, source_name=source_name, limit=args.second_tier_limit
            )
        for source_name in third_tier:
            imported += fetch_configured_sources(
                db, config, source_name=source_name, limit=args.third_tier_limit
            )
        print(f"Imported {imported} fetched articles.")

        count = analyze_articles(db, config, use_llm=args.use_llm)
        print(f"Analyzed {count} articles.")
        out = args.out or config.output.markdown_dir or DEFAULT_OUTPUT
        write_markdown_report(db, out)
        print(f"Exported reports to {out}")
        redbook_out = args.redbook_out or config.output.redbook_dir
        path = write_redbook(db, redbook_out)
        print(f"Exported redbook to {path}")
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
        out = args.out or config.output.markdown_dir or DEFAULT_OUTPUT
        write_markdown_report(db, out)
        write_redbook(db, config.output.redbook_dir)
        print(f"Demo exported reports to {out}")
        return 0

    return 1


def fetch_configured_sources(
    db, config, *, source_name: str = "all", limit: int | None = None
) -> int:
    selected = [
        source
        for source in config.sources
        if source.enabled and (source_name == "all" or source.name.lower() == source_name.lower())
    ]
    if not selected:
        print("No enabled sources matched.")
        return 0

    original_limit = config.crawler.max_articles_per_source
    if limit is not None:
        config.crawler.max_articles_per_source = limit

    imported = 0
    existing_urls = {article.url for article in db.list_articles() if article.url}
    try:
        for source in selected:
            source_imported = 0
            for article in iter_fetch_source_articles(
                source, config.crawler, existing_urls=existing_urls
            ):
                db.upsert_article(article)
                source_imported += 1
            imported += source_imported
            print(f"{source.name}: imported {source_imported} articles.")
    finally:
        config.crawler.max_articles_per_source = original_limit
    return imported


def _apply_exam_topic_queries(config, topic_queries: list[str]) -> None:
    for source in config.sources:
        if not source.search_url_templates:
            continue
        if source.name.lower() not in SECOND_TIER_SOURCES and source.quality_weight < 0.75:
            continue
        merged = list(dict.fromkeys([*topic_queries, *source.topic_queries]))
        source.topic_queries = merged


def _count_exam_articles(db) -> int:
    return sum(
        1
        for article in db.list_articles()
        if article.source.lower() in {"pastpapers.cn", "kaoyan_exam"}
        or article.metadata.get("corpus_type") == "kaoyan_exam"
    )


def analyze_articles(db, config, *, use_llm: bool = False, article_id: str = "all") -> int:
    analyzer = (
        LLMAnalyzer.from_config(config.llm.model, config.llm.api_key, config.llm.base_url)
        if use_llm
        else None
    )
    articles = db.list_articles()
    if article_id != "all":
        article = db.get_article(article_id)
        articles = [article] if article else []
    for article in articles:
        llm_payload = analyzer.analyze(article) if analyzer else {}
        result = analyze_article(article, llm_payload=llm_payload)
        db.save_analysis(result)
        print(
            f"Analyzed {result.article_id}: field={result.field}, "
            f"difficulty={result.difficulty}, exam_value={result.exam_value}"
        )
    return len(articles)


if __name__ == "__main__":
    raise SystemExit(main())

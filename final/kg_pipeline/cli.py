"""Command line entry point: crawl, extract, load, query, ask, refresh, run-all."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from . import graphrag, pipeline
from .config import PROJECT_ROOT, load_settings
from .discover import MAX_PAGES
from .load import clear_graph
from .queries import company_communities, run_all_queries

DEFAULT_SEEDS = PROJECT_ROOT / "data" / "seed_small.csv"


def print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cmd_crawl(args: argparse.Namespace) -> None:
    pages = pipeline.crawl(load_settings(), pipeline.read_seeds(args.seeds), args.max_pages)
    print(f"Fetched {len(pages)} pages. Saved to {pipeline.PAGES_FILE}")


def cmd_extract(args: argparse.Namespace) -> None:
    records = pipeline.extract(load_settings(), pipeline.read_json(pipeline.PAGES_FILE))
    kept = sum(r["kept"] for r in records)
    dropped = sum(len(r["dropped"]) for r in records)
    print(f"Extracted {len(records)} pages: kept {kept} items, dropped {dropped} by the quote guard.")


def cmd_load(args: argparse.Namespace) -> None:
    settings = load_settings()
    if args.reset:
        driver = pipeline.make_driver(settings)
        clear_graph(driver)
        driver.close()
    result = pipeline.load(settings, pipeline.read_json(pipeline.EXTRACTIONS_FILE), pipeline.read_seeds(args.seeds))
    print(f"Merged {len(result['merges'])} near-duplicate names.")
    print(f"Graph now has {result['counts']['nodes']} nodes and {result['counts']['relationships']} relationships.")


def cmd_query(args: argparse.Namespace) -> None:
    driver = pipeline.make_driver(load_settings())
    try:
        for name, rows in run_all_queries(driver).items():
            print(f"\n== {name} ({len(rows)} rows)")
            print_json(rows[: args.limit])
        print("\n== communities (networkx, shared integrations)")
        print_json(company_communities(driver))
    finally:
        driver.close()


def cmd_ask(args: argparse.Namespace) -> None:
    settings = load_settings()
    driver = pipeline.make_driver(settings)
    try:
        result = graphrag.ask(pipeline.make_llm(settings), settings.openai_model, driver, args.question)
    finally:
        driver.close()
    print(f"Cypher:\n{result.cypher}\n")
    print(f"Answer:\n{result.answer}\n")
    print("Sources:")
    print_json(result.sources[:10])


def cmd_refresh(args: argparse.Namespace) -> None:
    records = pipeline.refresh(load_settings(), pipeline.read_json(pipeline.PAGES_FILE))
    print(f"Re-extracted {len(records)} pages from Crawlbase Storage without crawling.")


def cmd_run_all(args: argparse.Namespace) -> None:
    cmd_crawl(args)
    cmd_extract(args)
    cmd_load(args)
    cmd_query(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kg", description="Build a knowledge graph from company websites.")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=func)
        return p

    for name, func, help_text in (("crawl", cmd_crawl, "discover and fetch pages"),
                                  ("run-all", cmd_run_all, "crawl, extract, load, and query")):
        p = add(name, func, help_text)
        p.add_argument("--seeds", type=Path, default=DEFAULT_SEEDS)
        p.add_argument("--max-pages", type=int, default=MAX_PAGES)
        if name == "run-all":
            p.add_argument("--reset", action="store_true", help="delete all graph data before loading")
            p.add_argument("--limit", type=int, default=5)
    add("extract", cmd_extract, "run LLM extraction on fetched pages")
    p = add("load", cmd_load, "normalize names and MERGE into Neo4j")
    p.add_argument("--seeds", type=Path, default=DEFAULT_SEEDS)
    p.add_argument("--reset", action="store_true", help="delete all graph data before loading")
    p = add("query", cmd_query, "run the cross-company Cypher queries")
    p.add_argument("--limit", type=int, default=5)
    p = add("ask", cmd_ask, "ask a question in plain English (GraphRAG)")
    p.add_argument("question")
    add("refresh", cmd_refresh, "re-extract from Crawlbase Storage by rid")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.func(args)


if __name__ == "__main__":
    main()

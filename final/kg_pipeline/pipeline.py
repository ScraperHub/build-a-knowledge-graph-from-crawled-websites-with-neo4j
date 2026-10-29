"""Stage functions the CLI calls: crawl, extract, load, query, ask, refresh."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from neo4j import Driver, GraphDatabase

from .cache import JsonCache
from .config import PROJECT_ROOT, Settings
from .crawl import CrawlbaseClient, CrawlError
from .discover import MAX_PAGES, discover_pages
from .extract import extract_page
from .load import load_records
from .normalize import normalize_records

log = logging.getLogger("kg_pipeline")
OUTPUT_DIR = PROJECT_ROOT / "output"
PAGES_FILE = OUTPUT_DIR / "pages.json"
EXTRACTIONS_FILE = OUTPUT_DIR / "extractions.json"


def read_seeds(path: Path) -> list[dict[str, Any]]:
    """Read name,homepage,use_js rows from a CSV file."""
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {"name": row["name"].strip(), "homepage": row["homepage"].strip(),
             "use_js": row.get("use_js", "").strip().lower() in ("1", "true", "yes")}
            for row in csv.DictReader(handle)
            if row.get("name") and row.get("homepage")
        ]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def make_crawler(settings: Settings, use_cache: bool = True) -> CrawlbaseClient:
    return CrawlbaseClient(settings.crawlbase_token, settings.crawlbase_js_token,
                           JsonCache(settings.cache_dir / "crawl", enabled=use_cache))


def make_driver(settings: Settings) -> Driver:
    return GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))


def make_llm(settings: Settings) -> Any:
    from openai import OpenAI

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env")
    return OpenAI(api_key=settings.openai_api_key, timeout=120, max_retries=3)


def crawl(settings: Settings, seeds: list[dict[str, Any]], max_pages: int = MAX_PAGES) -> list[dict[str, Any]]:
    """Discover pages per company with generic-extractor, then fetch each one as stored Markdown."""
    crawler = make_crawler(settings)
    pages: list[dict[str, Any]] = []
    for seed in seeds:
        try:
            home = crawler.scrape_generic(seed["homepage"], use_js=seed["use_js"])
        except CrawlError as error:
            log.warning("discovery failed for %s: %s", seed["name"], error)
            continue
        found = discover_pages(seed["homepage"], home.get("links") or [], max_pages, final_url=home.get("final_url"))
        targets = [{"url": seed["homepage"], "page_type": "home"}] + found
        log.info("%s: %d pages", seed["name"], len(targets))
        for target in targets:
            try:
                page = crawler.fetch_markdown(target["url"], use_js=seed["use_js"])
            except CrawlError as error:
                log.warning("fetch failed for %s: %s", target["url"], error)
                continue
            pages.append({"company": seed["name"], "page_type": target["page_type"], **page.to_dict()})
    write_json(PAGES_FILE, pages)
    return pages


def extract(settings: Settings, pages: list[dict[str, Any]], use_cache: bool = True) -> list[dict[str, Any]]:
    """Run guarded LLM extraction on every fetched page."""
    client = make_llm(settings)
    cache = JsonCache(settings.cache_dir / "llm", enabled=use_cache)
    records = []
    for page in pages:
        if not page["markdown"].strip():
            continue
        record = extract_page(client, settings.openai_model, cache, page["company"], page["url"], page["rid"],
                              page["markdown"])
        log.info("%s: kept %d, dropped %d", page["url"], record["kept"], len(record["dropped"]))
        records.append(record)
    write_json(EXTRACTIONS_FILE, records)
    return records


def load(settings: Settings, records: list[dict[str, Any]], seeds: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize names across pages, then MERGE everything into Neo4j."""
    normalized, merges = normalize_records(records, [s["name"] for s in seeds])
    driver = make_driver(settings)
    try:
        counts = load_records(driver, normalized, seeds)
    finally:
        driver.close()
    return {"counts": counts, "merges": merges}


def refresh(settings: Settings, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-extract from Crawlbase Storage by rid. No new crawl requests are made."""
    crawler = make_crawler(settings)
    refreshed = []
    for page in pages:
        if not page.get("rid"):
            continue
        stored = crawler.get_stored(page["rid"])
        refreshed.append({**page, "markdown": stored["body"]})
    return extract(settings, refreshed, use_cache=False)

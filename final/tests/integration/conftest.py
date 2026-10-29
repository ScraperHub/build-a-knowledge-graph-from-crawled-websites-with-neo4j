"""Live fixtures. These tests call Crawlbase and OpenAI, and they wipe the Neo4j database."""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from neo4j import Driver

from helpers import FIXTURES, load_fixture
from kg_pipeline.cache import JsonCache
from kg_pipeline.config import PROJECT_ROOT, Settings, load_settings
from kg_pipeline.crawl import CrawlbaseClient
from kg_pipeline.load import clear_graph, load_records
from kg_pipeline.normalize import normalize_records
from kg_pipeline.pipeline import make_driver, make_llm, read_seeds

SEEDS = PROJECT_ROOT / "data" / "seed_small.csv"


@pytest.fixture(scope="session")
def settings() -> Settings:
    loaded = load_settings()
    assert loaded.crawlbase_token and loaded.crawlbase_js_token, "Crawlbase tokens missing from .env"
    return loaded


@pytest.fixture(scope="session")
def live_crawler(settings: Settings) -> CrawlbaseClient:
    """No cache, so every call really reaches Crawlbase."""
    return CrawlbaseClient(settings.crawlbase_token, settings.crawlbase_js_token, JsonCache(FIXTURES, enabled=False))


@pytest.fixture(scope="session")
def seeds() -> list[dict[str, Any]]:
    return read_seeds(SEEDS)


@pytest.fixture(scope="session")
def driver(settings: Settings) -> Iterator[Driver]:
    drv = make_driver(settings)
    drv.verify_connectivity()
    yield drv
    drv.close()


@pytest.fixture(scope="session")
def recorded_records(seeds) -> list[dict[str, Any]]:
    normalized, _ = normalize_records(load_fixture("extractions_small.json"), [s["name"] for s in seeds])
    return normalized


@pytest.fixture(scope="session")
def loaded_graph(driver: Driver, recorded_records, seeds) -> dict[str, int]:
    """A clean graph built from the recorded extraction of the small seed list."""
    clear_graph(driver)
    return load_records(driver, recorded_records, seeds)


@pytest.fixture(scope="session")
def llm(settings: Settings) -> Any:
    return make_llm(settings)

"""Copy real pages and their cached LLM output into tests/fixtures for offline guard tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from kg_pipeline.cache import JsonCache
from kg_pipeline.config import load_settings
from kg_pipeline.extract import PROMPT_VERSION
from kg_pipeline.pipeline import PAGES_FILE

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
TARGETS = {
    "https://www.pipedrive.com/": "pipedrive_home",
    "https://www.pipedrive.com/en/marketplace": "pipedrive_marketplace",
}


def main() -> None:
    settings = load_settings()
    cache = JsonCache(settings.cache_dir / "llm")
    pages = {p["url"]: p for p in json.loads(PAGES_FILE.read_text(encoding="utf-8"))}
    for url, name in TARGETS.items():
        page = pages[url]
        digest = hashlib.sha256(page["markdown"].encode("utf-8")).hexdigest()
        cached = cache.get("llm", f"{settings.openai_model}|{PROMPT_VERSION}|{page['company']}|{digest}")
        page_fixture = {k: page[k] for k in ("company", "url", "rid", "markdown")}
        (FIXTURES / f"page_{name}.json").write_text(json.dumps(page_fixture, indent=2, ensure_ascii=False), encoding="utf-8")
        (FIXTURES / f"llm_{name}.json").write_text(json.dumps(cached["raw"], indent=2, ensure_ascii=False), encoding="utf-8")
        print(name, len(page["markdown"]), {k: len(v) for k, v in cached["raw"].items()})


if __name__ == "__main__":
    main()

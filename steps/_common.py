"""Shared helpers for the step scripts: settings from .env and JSON files that pass data between steps."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache"
load_dotenv(HERE / ".env", override=True)

CRAWLBASE_TOKEN = os.environ["CRAWLBASE_TOKEN"]
CRAWLBASE_JS_TOKEN = os.environ["CRAWLBASE_JS_TOKEN"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", ""))

SEEDS = [
    {"name": "Basecamp", "homepage": "https://basecamp.com/"},
    {"name": "HEY", "homepage": "https://www.hey.com/"},
    {"name": "Pipedrive", "homepage": "https://www.pipedrive.com/"},
    {"name": "Zendesk", "homepage": "https://www.zendesk.com/"},
]


def save(name: str, data: Any) -> Path:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load(name: str) -> Any:
    path = CACHE / name
    if not path.exists():
        raise SystemExit(f"{path} not found. Run the previous step first.")
    return json.loads(path.read_text(encoding="utf-8"))

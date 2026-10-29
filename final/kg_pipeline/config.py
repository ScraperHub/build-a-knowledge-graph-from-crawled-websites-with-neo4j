"""Settings loaded from the environment and a local .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    crawlbase_token: str = field(repr=False)
    crawlbase_js_token: str = field(repr=False)
    openai_api_key: str = field(repr=False)
    openai_model: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str = field(repr=False)
    cache_dir: Path


def load_settings(env_file: Path | None = None) -> Settings:
    """Read settings from `.env`. Values in `.env` win over variables already set in the shell."""
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=True)
    return Settings(
        crawlbase_token=os.getenv("CRAWLBASE_TOKEN", ""),
        crawlbase_js_token=os.getenv("CRAWLBASE_JS_TOKEN", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
        cache_dir=Path(os.getenv("KG_CACHE_DIR", PROJECT_ROOT / ".cache")),
    )

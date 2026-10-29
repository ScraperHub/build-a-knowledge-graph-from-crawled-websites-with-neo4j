"""Compare Normal and JS tokens with format=md on pages that may render in the browser."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
load_dotenv(ROOT / ".env", override=True)
TOKENS = {"normal": os.environ["CRAWLBASE_TOKEN"], "js": os.environ["CRAWLBASE_JS_TOKEN"]}


def main(urls: list[str]) -> None:
    for url in urls:
        name = httpx.URL(url).host.replace("www.", "").replace(".", "_") + httpx.URL(url).path.replace("/", "_").rstrip("_")
        for label, token in TOKENS.items():
            params = {"token": token, "url": url, "format": "md", "md_readability": "true"}
            resp = httpx.get("https://api.crawlbase.com/", params=params, timeout=90)
            keep = {k: v for k, v in resp.headers.items() if k in ("cb_status", "original_status", "url", "content-type")}
            (FIXTURES / f"md_token_{name}_{label}.json").write_text(
                json.dumps({"status_code": resp.status_code, "headers": keep, "body": resp.text}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"{url} [{label}] http={resp.status_code} cb={keep.get('cb_status')} chars={len(resp.text)} "
                  f"start={resp.text[:100]!r}")
            time.sleep(1)


if __name__ == "__main__":
    main(sys.argv[1:])

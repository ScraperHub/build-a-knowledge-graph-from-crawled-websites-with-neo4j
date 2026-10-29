"""Compare format=md with and without md_readability=true on team and integration pages."""

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
TOKEN = os.environ["CRAWLBASE_TOKEN"]


def main(urls: list[str]) -> None:
    for url in urls:
        parsed = httpx.URL(url)
        name = (parsed.host.replace("www.", "") + parsed.path).replace(".", "_").replace("/", "_").rstrip("_")
        for label, readability in (("readability", "true"), ("plain", "false")):
            params = {"token": TOKEN, "url": url, "format": "md", "md_readability": readability}
            resp = httpx.get("https://api.crawlbase.com/", params=params, timeout=90)
            keep = {k: v for k, v in resp.headers.items() if k in ("cb_status", "original_status", "url", "content-type")}
            (FIXTURES / f"md_{label}_{name}.json").write_text(
                json.dumps({"status_code": resp.status_code, "headers": keep, "body": resp.text}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"{url} [{label}] cb={keep.get('cb_status')} chars={len(resp.text)}")
            time.sleep(1)


if __name__ == "__main__":
    main(sys.argv[1:])

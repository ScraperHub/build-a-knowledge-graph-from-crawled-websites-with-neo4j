"""Live checks for the three Crawlbase assumptions. Saves raw responses as test fixtures."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
API = "https://api.crawlbase.com/"
STORAGE = "https://api.crawlbase.com/storage"
KEEP_HEADERS = ("cb_status", "original_status", "url", "rid", "storage_url", "content-type")

load_dotenv(ROOT / ".env", override=True)
NORMAL = os.environ["CRAWLBASE_TOKEN"]
JS = os.environ["CRAWLBASE_JS_TOKEN"]


def call(token: str, url: str, **params: str) -> dict:
    """One Crawling API GET. Returns status, kept headers, and body."""
    resp = httpx.get(API, params={"token": token, "url": url, **params}, timeout=90)
    headers = {k: v for k, v in resp.headers.items() if k.lower() in KEEP_HEADERS}
    return {"status_code": resp.status_code, "headers": headers, "body": resp.text}


def scrub(text: str) -> str:
    """Remove every token from saved fixtures, including the one inside storage_url."""
    text = re.sub(r"(storage\?token=)[A-Za-z0-9_-]+", r"\1YOUR_CRAWLBASE_TOKEN", text)
    return text.replace(NORMAL, "YOUR_CRAWLBASE_TOKEN").replace(JS, "YOUR_CRAWLBASE_JS_TOKEN")


def save(name: str, data: dict) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    text = scrub(json.dumps(data, indent=2, ensure_ascii=False))
    (FIXTURES / name).write_text(text, encoding="utf-8")
    print(f"saved {name}")


def href_kinds(links: list[dict]) -> dict[str, int]:
    kinds = {"absolute": 0, "root_relative": 0, "fragment": 0, "mailto_tel": 0, "other_relative": 0}
    for link in links:
        href = (link.get("href") if isinstance(link, dict) else link or "").strip()
        if href.startswith(("http://", "https://", "//")):
            kinds["absolute"] += 1
        elif href.startswith("/"):
            kinds["root_relative"] += 1
        elif href.startswith("#"):
            kinds["fragment"] += 1
        elif href.startswith(("mailto:", "tel:")):
            kinds["mailto_tel"] += 1
        else:
            kinds["other_relative"] += 1
    return kinds


def check_hrefs(urls: list[str]) -> None:
    for url in urls:
        result = call(NORMAL, url, scraper="generic-extractor")
        name = httpx.URL(url).host.replace("www.", "").replace(".", "_")
        save(f"generic_extractor_{name}.json", result)
        try:
            envelope = json.loads(result["body"])
            links = (envelope.get("body") or {}).get("links") or []
            print(url, envelope.get("original_status"), "links:", len(links), href_kinds(links))
            print("  sample:", links[:8])
        except json.JSONDecodeError:
            print(url, "non-JSON body", result["status_code"], result["body"][:200])
        time.sleep(1)


def rid_from_storage_url(storage_url: str | None) -> str | None:
    return httpx.URL(storage_url).params.get("rid") if storage_url else None


def check_store(url: str) -> None:
    scraped = call(NORMAL, url, scraper="generic-extractor", store="true")
    save("store_with_scraper.json", scraped)
    envelope = json.loads(scraped["body"])
    rid = scraped["headers"].get("rid") or rid_from_storage_url(envelope.get("storage_url"))
    print("scraper+store headers:", scraped["headers"], "envelope storage_url:", envelope.get("storage_url"))
    md = call(NORMAL, url, format="md", md_readability="true", store="true")
    save("md_with_store.json", md)
    md_rid = md["headers"].get("rid") or rid_from_storage_url(md["headers"].get("storage_url"))
    print("md+store headers:", md["headers"], "body starts:", md["body"][:120].replace("\n", " "))
    time.sleep(3)
    for label, r in (("scraper", rid), ("md", md_rid)):
        if not r:
            print(label, "no rid returned")
            continue
        stored = httpx.get(STORAGE, params={"token": NORMAL, "rid": r}, timeout=60)
        keep = ("content-type", "rid", "url", "stored_at", "original_status", "pc_status")
        headers = {k: v for k, v in stored.headers.items() if k in keep}
        data = {"status_code": stored.status_code, "headers": headers, "body": stored.text}
        save(f"storage_get_{label}.json", data)
        print(label, "storage status", stored.status_code, "body starts:", stored.text[:150].replace("\n", " "))


def check_tokens(urls: list[str]) -> None:
    for url in urls:
        name = httpx.URL(url).host.replace("www.", "").replace(".", "_")
        for label, token in (("normal", NORMAL), ("js", JS)):
            result = call(token, url, scraper="generic-extractor")
            save(f"token_compare_{name}_{label}.json", result)
            try:
                envelope = json.loads(result["body"])
                page = envelope.get("body") or {}
                print(f"{url} [{label}] original_status={envelope.get('original_status')} "
                      f"links={len(page.get('links') or [])} content={len(page.get('content') or '')}")
            except json.JSONDecodeError:
                print(f"{url} [{label}] non-JSON {result['status_code']} {result['body'][:150]}")
            time.sleep(1)


if __name__ == "__main__":
    step = sys.argv[1]
    args = sys.argv[2:]
    {"hrefs": check_hrefs, "tokens": check_tokens}.get(step, lambda a: check_store(a[0]))(args)

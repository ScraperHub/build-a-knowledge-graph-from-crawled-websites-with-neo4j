"""Step 9: re-run extraction on stored pages from the Crawlbase Storage API. No new crawl requests."""

import importlib

import httpx
from openai import OpenAI

from _common import CRAWLBASE_TOKEN, load, save

step4 = importlib.import_module("04_extract_with_guard")
STORAGE = "https://api.crawlbase.com/storage"


def get_stored(rid: str) -> str:
    response = httpx.get(STORAGE, params={"token": CRAWLBASE_TOKEN, "rid": rid}, timeout=60)
    response.raise_for_status()
    print(f"  rid={rid} stored_at={response.headers.get('stored_at')} url={response.headers.get('url')}")
    return response.text


pages = [p for p in load("pages.json") if p["rid"]][:3]
client = OpenAI()
refreshed = []
for page in pages:
    markdown = get_stored(page["rid"])
    assert markdown == page["markdown"], "stored copy differs from the crawl"
    result, dropped = step4.extract(client, page["company"], markdown)
    print(f"  re-extracted {len(result.relationships)} relationships, dropped {len(dropped)}")
    refreshed.append({"company": page["company"], "url": page["url"], "rid": page["rid"],
                      "result": result.model_dump()})

print("Saved", save("refreshed.json", refreshed))

"""Step 2: fetch every discovered page as Markdown, store it in Crawlbase, and keep the rid."""

import time

import httpx

from _common import CRAWLBASE_JS_TOKEN, CRAWLBASE_TOKEN, load, save

API = "https://api.crawlbase.com/"


def fetch(url: str, token: str, readability: bool) -> httpx.Response:
    params = {"token": token, "url": url, "format": "md",
              "md_readability": str(readability).lower(), "store": "true"}
    for attempt in range(3):
        response = httpx.get(API, params=params, timeout=90)
        if response.status_code == 200 and response.headers.get("cb_status") != "0":
            return response
        time.sleep(2 ** attempt)
    response.raise_for_status()
    return response


def fetch_page(url: str) -> dict:
    """Readability first, plain Markdown if that drops the content, JS token if the page renders in the browser."""
    for token, readability, min_chars in ((CRAWLBASE_TOKEN, True, 1500),
                                          (CRAWLBASE_TOKEN, False, 300),
                                          (CRAWLBASE_JS_TOKEN, False, 0)):
        response = fetch(url, token, readability)
        if len(response.text) >= min_chars:
            break
    rid = httpx.URL(response.headers.get("storage_url", "")).params.get("rid", "")
    return {"url": url, "markdown": response.text, "rid": rid, "readability": readability,
            "js": token == CRAWLBASE_JS_TOKEN}


pages = []
for company in load("discovered.json"):
    for target in company["pages"]:
        page = fetch_page(target["url"])
        pages.append({"company": company["name"], **page})
        mode = "readability" if page["readability"] else "plain"
        print(f"{company['name']:<10} {len(page['markdown']):>6} chars  {mode:<11}  rid={page['rid']}  {page['url']}")
        time.sleep(1)

print("Saved", save("pages.json", pages))

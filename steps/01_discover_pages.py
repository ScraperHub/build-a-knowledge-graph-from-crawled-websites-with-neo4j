"""Step 1: find the about, team, partners, integrations, and careers pages of each company."""

import re
from urllib.parse import urljoin, urlsplit

from crawlbase import CrawlingAPI

from _common import CRAWLBASE_TOKEN, SEEDS, save

PAGE_TYPES = {
    "about": r"^(about|company|our-story)",
    "team": r"^(team|our-team|leadership|people)",
    "partners": r"^partner",
    "integrations": r"^(integration|marketplace)",
    "careers": r"^(career|jobs)",
}
MAX_PAGES = 8


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def page_type(url: str) -> str | None:
    segments = [s for s in urlsplit(url).path.lower().split("/") if s]
    for name, pattern in PAGE_TYPES.items():
        if segments and re.match(pattern, segments[-1]):
            return name
    return None


def discover(homepage: str, final_url: str, links: list) -> list[dict]:
    """Links on the seed host whose last path segment looks like a company page."""
    found, seen = [], set()
    for link in links:
        href = link.get("href") if isinstance(link, dict) else link
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(final_url, href).split("#")[0].split("?")[0].rstrip("/")
        key = (host(url), urlsplit(url).path)
        kind = page_type(url)
        if kind and key[0] == host(homepage) and key not in seen:
            seen.add(key)
            found.append({"url": url, "page_type": kind})
    return found[:MAX_PAGES]


api = CrawlingAPI({"token": CRAWLBASE_TOKEN, "timeout": 90})
discovered = []
for seed in SEEDS:
    response = api.get(seed["homepage"], {"scraper": "generic-extractor"})
    page = response["json"]
    final_url = response["headers"]["url"]
    pages = discover(seed["homepage"], final_url, page["links"])
    print(f"{seed['name']}: {len(page['links'])} links, {len(pages)} company pages (landed on {final_url})")
    for p in pages:
        print(f"  {p['page_type']:<13} {p['url']}")
    discovered.append({**seed, "pages": [{"url": seed["homepage"], "page_type": "home"}] + pages})

print("Saved", save("discovered.json", discovered))

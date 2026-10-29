"""Pick the about, team, partners, integrations, and careers pages from generic-extractor links."""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

PAGE_PATTERNS: dict[str, re.Pattern[str]] = {
    "about": re.compile(r"^(about|company|our-story|who-we-are)"),
    "team": re.compile(r"^(team|our-team|leadership|people)"),
    "partners": re.compile(r"^partner"),
    "integrations": re.compile(r"^(integration|marketplace)"),
    "careers": re.compile(r"^(career|jobs)"),
}
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")
MAX_PAGES = 8


def host_key(url: str) -> str:
    """Lowercase host without a leading www., so www.example.com equals example.com."""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def clean_url(url: str) -> str:
    """Drop query strings and fragments and trailing slashes so duplicates collapse."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def resolve_links(page_url: str, links: Iterable[Any]) -> list[str]:
    """Turn generic-extractor links (strings or {"href": ...} dicts, absolute or relative) into absolute URLs."""
    resolved: list[str] = []
    for link in links:
        href = link.get("href") if isinstance(link, dict) else link
        if not isinstance(href, str):
            continue
        href = href.strip()
        if not href or href.startswith("#") or href.lower().startswith(SKIP_SCHEMES):
            continue
        absolute = urljoin(page_url, href)
        if urlsplit(absolute).scheme in ("http", "https"):
            resolved.append(clean_url(absolute))
    return resolved


def match_page_type(url: str) -> str | None:
    """Return the page type that matches the last path segment, or None."""
    segments = [s.lower() for s in urlsplit(url).path.split("/") if s]
    if not segments:
        return None
    for page_type, pattern in PAGE_PATTERNS.items():
        if pattern.match(segments[-1]):
            return page_type
    return None


def discover_pages(homepage: str, links: Iterable[Any], max_pages: int = MAX_PAGES,
                   final_url: str | None = None) -> list[dict[str, str]]:
    """Keep links on the seed homepage's host that look like company pages, shallow paths first.

    Relative links resolve against final_url (the page Crawlbase ended on), but the host filter always
    uses the seed homepage, so a geo redirect such as example.com -> example.de does not empty the result.
    """
    site = host_key(homepage)
    home = clean_url(homepage)
    buckets: dict[str, list[str]] = {page_type: [] for page_type in PAGE_PATTERNS}
    seen: set[tuple[str, str]] = {(site, urlsplit(home).path)}
    for url in resolve_links(final_url or homepage, links):
        key = (host_key(url), urlsplit(url).path)
        if key in seen or key[0] != site:
            continue
        seen.add(key)
        page_type = match_page_type(url)
        if page_type:
            buckets[page_type].append(url)

    for urls in buckets.values():
        urls.sort(key=lambda u: (urlsplit(u).path.count("/"), len(u)))

    picked: list[dict[str, str]] = []
    while len(picked) < max_pages and any(buckets.values()):
        for page_type, urls in buckets.items():
            if urls and len(picked) < max_pages:
                picked.append({"url": urls.pop(0), "page_type": page_type})
    return picked

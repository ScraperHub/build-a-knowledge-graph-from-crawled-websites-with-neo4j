"""Crawlbase calls: generic-extractor discovery, Markdown fetch with store=true, and Storage API reads."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

import httpx
from crawlbase import CrawlingAPI

from .cache import JsonCache

API_URL = "https://api.crawlbase.com/"
STORAGE_URL = "https://api.crawlbase.com/storage"
MIN_READABLE_CHARS = 1500
MIN_RENDERED_CHARS = 300
RETRYABLE_STATUS = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525}

T = TypeVar("T")


class CrawlError(RuntimeError):
    """Raised when Crawlbase keeps failing after all retries."""


@dataclass
class FetchedPage:
    url: str
    final_url: str
    markdown: str
    rid: str
    token: str
    readability: bool
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_retryable_status(status_code: int | None, cb_status: str | None) -> bool:
    """Crawlbase marks failed, uncharged requests with HTTP 520 and cb_status 0."""
    if status_code in RETRYABLE_STATUS:
        return True
    return cb_status is not None and str(cb_status).strip() in {"0", *map(str, RETRYABLE_STATUS)}


def is_retryable_response(resp: httpx.Response) -> bool:
    return is_retryable_status(resp.status_code, resp.headers.get("cb_status"))


def rid_from_storage_url(storage_url: str | None) -> str:
    """Crawlbase returns the rid inside storage_url, not as its own field."""
    if not storage_url:
        return ""
    return httpx.URL(storage_url).params.get("rid", "")


class CrawlbaseClient:
    """Wraps Crawlbase with retries, timeouts, polite rate limiting, and a local cache."""

    def __init__(
        self,
        token: str,
        js_token: str,
        cache: JsonCache,
        timeout: float = 90.0,
        max_retries: int = 3,
        min_interval: float = 1.0,
        http: httpx.Client | None = None,
        sdk_factory: Callable[[dict[str, Any]], Any] = CrawlingAPI,
    ) -> None:
        if not token:
            raise ValueError("CRAWLBASE_TOKEN is missing")
        self.tokens = {"normal": token, "js": js_token or token}
        self.cache = cache
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.http = http or httpx.Client(timeout=timeout)
        self.sdk = {name: sdk_factory({"token": t, "timeout": int(timeout)}) for name, t in self.tokens.items()}
        self._last_call = 0.0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _with_retries(self, call: Callable[[], T], is_retryable: Callable[[T], bool]) -> T:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                result = call()
                if not is_retryable(result):
                    return result
                last_error = CrawlError(f"retryable response: {result!r}"[:300])
            except (httpx.TransportError, OSError) as error:
                last_error = error
            time.sleep(2**attempt)
        raise CrawlError(f"Crawlbase failed after {self.max_retries} attempts: {last_error}")

    def scrape_generic(self, url: str, use_js: bool = False) -> dict[str, Any]:
        """Run scraper=generic-extractor through the official SDK and return the parsed page."""
        token = "js" if use_js else "normal"
        key = f"{token}|{url}"
        cached = self.cache.get("generic", key)
        if cached is not None:
            return cached

        def call() -> dict[str, Any]:
            return self.sdk[token].get(url, {"scraper": "generic-extractor"})

        def retryable(resp: dict[str, Any]) -> bool:
            return is_retryable_status(resp.get("status_code"), resp.get("headers", {}).get("cb_status"))

        resp = self._with_retries(call, retryable)
        page = resp.get("json") or {}
        if not isinstance(page, dict):
            raise CrawlError(f"generic-extractor returned no JSON for {url}")
        page["final_url"] = resp.get("headers", {}).get("url") or url
        self.cache.set("generic", key, page)
        return page

    def _get_markdown(self, url: str, token: str, readability: bool) -> httpx.Response:
        params = {
            "token": self.tokens[token],
            "url": url,
            "format": "md",
            "md_readability": "true" if readability else "false",
            "store": "true",
        }

        return self._with_retries(lambda: self.http.get(API_URL, params=params), is_retryable_response)

    def fetch_markdown(self, url: str, use_js: bool = False) -> FetchedPage:
        """Fetch a page as Markdown with store=true.

        Tries md_readability=true first, falls back to plain Markdown when readability
        drops structured content, and falls back to the JS token when the page
        renders in the browser.
        """
        cached = self.cache.get("markdown", url)
        if cached is not None:
            return FetchedPage(**cached)

        attempts = [("js" if use_js else "normal", True), ("js" if use_js else "normal", False)]
        if not use_js:
            attempts.append(("js", False))

        page: FetchedPage | None = None
        for token, readability in attempts:
            resp = self._get_markdown(url, token, readability)
            candidate = FetchedPage(
                url=url,
                final_url=resp.headers.get("url") or url,
                markdown=resp.text,
                rid=rid_from_storage_url(resp.headers.get("storage_url")),
                token=token,
                readability=readability,
                fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            if page is None or len(candidate.markdown) > len(page.markdown):
                page = candidate
            threshold = MIN_READABLE_CHARS if readability else MIN_RENDERED_CHARS
            if len(candidate.markdown) >= threshold:
                page = candidate
                break

        assert page is not None
        self.cache.set("markdown", url, page.to_dict())
        return page

    def get_stored(self, rid: str) -> dict[str, str]:
        """Read a stored page back from the Storage API by rid."""

        resp = self._with_retries(
            lambda: self.http.get(STORAGE_URL, params={"token": self.tokens["normal"], "rid": rid}),
            lambda r: r.status_code in RETRYABLE_STATUS,
        )
        if resp.status_code != 200:
            raise CrawlError(f"Storage API returned {resp.status_code} for rid {rid}")
        return {
            "rid": resp.headers.get("rid", rid),
            "url": resp.headers.get("url", ""),
            "stored_at": resp.headers.get("stored_at", ""),
            "body": resp.text,
        }

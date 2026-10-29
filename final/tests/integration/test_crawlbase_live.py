"""Real Crawlbase calls with both tokens on three companies from the small seed list."""

from __future__ import annotations

import pytest

from kg_pipeline.discover import discover_pages, host_key

pytestmark = pytest.mark.integration


def test_generic_extractor_with_normal_token_on_three_companies(live_crawler, seeds):
    discovered = {}
    for seed in seeds[:3]:
        page = live_crawler.scrape_generic(seed["homepage"])
        assert page.get("title"), seed["name"]
        assert page.get("links"), seed["name"]
        pages = discover_pages(page["final_url"], page["links"])
        assert all(host_key(p["url"]) == host_key(seed["homepage"]) for p in pages)
        discovered[seed["name"]] = [p["url"] for p in pages]
    assert "https://basecamp.com/about" in discovered["Basecamp"]
    assert any(url.endswith("/about") for url in discovered["Pipedrive"])


def test_generic_extractor_with_js_token(live_crawler, seeds):
    page = live_crawler.scrape_generic(seeds[0]["homepage"], use_js=True)
    assert page.get("links")
    assert len(page.get("content") or "") > 500


def test_markdown_with_store_returns_rid_and_falls_back_from_readability(live_crawler):
    page = live_crawler.fetch_markdown("https://www.pipedrive.com/en/about")
    assert page.rid
    assert page.token == "normal"
    assert page.readability is False
    assert "Tallinn" in page.markdown


def test_markdown_with_js_token_returns_rid(live_crawler):
    page = live_crawler.fetch_markdown("https://basecamp.com/about", use_js=True)
    assert page.rid
    assert page.token == "js"
    assert "Jason Fried" in page.markdown


def test_browser_rendered_page_needs_the_js_token(live_crawler):
    page = live_crawler.fetch_markdown("https://quotes.toscrape.com/js/")
    assert page.token == "js"
    assert "Albert Einstein" in page.markdown

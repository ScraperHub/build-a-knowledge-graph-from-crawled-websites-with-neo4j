from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from helpers import load_fixture
from kg_pipeline import crawl as crawl_module
from kg_pipeline.cache import JsonCache
from kg_pipeline.crawl import CrawlbaseClient, CrawlError, rid_from_storage_url
from kg_pipeline.extract import extract_page
from kg_pipeline.schema import ExtractionResult


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(crawl_module.time, "sleep", lambda _: None)


def recorded(name: str) -> httpx.Response:
    data = load_fixture(name)
    return httpx.Response(data["status_code"], headers=data["headers"], text=data["body"])


class FakeSdk:
    def __init__(self, options):
        self.calls = 0

    def get(self, url, options):
        self.calls += 1
        return {"status_code": 200, "headers": {"cb_status": "200", "url": url},
                "json": {"title": "t", "links": ["https://example.com/about"]}}


def make_client(tmp_path, handler, **kwargs) -> CrawlbaseClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return CrawlbaseClient("normal-token", "js-token", JsonCache(tmp_path), min_interval=0, http=http,
                           sdk_factory=FakeSdk, **kwargs)


def test_rid_comes_from_storage_url_in_the_real_md_store_response():
    headers = load_fixture("md_with_store.json")["headers"]
    assert "rid" not in headers
    assert rid_from_storage_url(headers["storage_url"]) == "e3f47e85254ef95d7ff82dd6"


def test_markdown_fetch_uses_store_and_caches(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(
            200, headers={"cb_status": "200", "storage_url": "https://api.crawlbase.com/storage?token=t&rid=abc123"},
            text="# Team\n" + "Real content. " * 200)

    client = make_client(tmp_path, handler)
    first = client.fetch_markdown("https://example.com/team")
    second = client.fetch_markdown("https://example.com/team")
    assert first == second
    assert first.rid == "abc123"
    assert len(calls) == 1
    assert calls[0]["format"] == "md"
    assert calls[0]["md_readability"] == "true"
    assert calls[0]["store"] == "true"
    assert calls[0]["token"] == "normal-token"


def test_thin_readability_output_falls_back_to_plain_markdown(tmp_path):
    readability = recorded("md_with_store.json")
    plain = load_fixture("md_plain_close_com_about.json")["body"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["md_readability"] == "true":
            return readability
        return httpx.Response(200, headers={"storage_url": "https://x/storage?rid=plainrid"}, text=plain)

    page = make_client(tmp_path, handler).fetch_markdown("https://www.close.com/about")
    assert page.readability is False
    assert page.rid == "plainrid"
    assert "Steli Efti" in page.markdown


def test_browser_rendered_page_falls_back_to_js_token(tmp_path):
    normal = recorded("md_token_quotes_toscrape_com_js_normal.json")
    js = recorded("md_token_quotes_toscrape_com_js_js.json")
    tokens = []

    def handler(request: httpx.Request) -> httpx.Response:
        tokens.append(request.url.params["token"])
        return js if request.url.params["token"] == "js-token" else normal

    page = make_client(tmp_path, handler).fetch_markdown("https://quotes.toscrape.com/js/")
    assert tokens == ["normal-token", "normal-token", "js-token"]
    assert page.token == "js"
    assert len(page.markdown) > 300


def test_retries_the_real_520_failure_then_succeeds(tmp_path):
    responses = [recorded("crawl_failure_520.json"),
                 httpx.Response(200, headers={"cb_status": "200"}, text="ok " * 1000)]

    page = make_client(tmp_path, lambda request: responses.pop(0)).fetch_markdown("https://www.close.com/integrations")
    assert page.markdown.startswith("ok")
    assert responses == []


def test_gives_up_after_max_retries(tmp_path):
    client = make_client(tmp_path, lambda request: recorded("crawl_failure_520.json"), max_retries=2)
    with pytest.raises(CrawlError):
        client.fetch_markdown("https://www.close.com/integrations")


def test_network_errors_are_retried(tmp_path):
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectTimeout("timeout")
        return httpx.Response(200, text="x" * 2000)

    assert make_client(tmp_path, handler).fetch_markdown("https://example.com/").markdown == "x" * 2000
    assert attempts["n"] == 2


def test_generic_extractor_is_cached(tmp_path):
    client = make_client(tmp_path, lambda request: httpx.Response(500))
    client.scrape_generic("https://example.com/")
    client.scrape_generic("https://example.com/")
    assert client.sdk["normal"].calls == 1


def test_storage_round_trip_parses_the_real_response(tmp_path):
    stored = load_fixture("storage_get_md.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/storage"
        return httpx.Response(200, headers=stored["headers"], text=stored["body"])

    page = make_client(tmp_path, handler).get_stored(stored["headers"]["rid"])
    assert page["url"] == "https://close.com/about"
    assert page["body"].startswith("Before Close was a CRM")


def test_llm_results_are_cached_by_page_content(tmp_path):
    raw = load_fixture("llm_pipedrive_marketplace.json")
    page = load_fixture("page_pipedrive_marketplace.json")
    calls = {"n": 0}

    def parse(**kwargs):
        calls["n"] += 1
        message = SimpleNamespace(parsed=ExtractionResult.model_validate(raw))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    llm = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    cache = JsonCache(tmp_path)
    args = (llm, "gpt-4o-mini", cache, "Pipedrive", page["url"], page["rid"], page["markdown"])
    first = extract_page(*args)
    second = extract_page(*args)
    assert calls["n"] == 1
    assert first == second
    assert first["rid"] == page["rid"]
    assert any(r["type"] == "INTEGRATES_WITH" for r in first["result"]["relationships"])

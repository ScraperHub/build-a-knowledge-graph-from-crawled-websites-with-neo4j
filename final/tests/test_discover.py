from __future__ import annotations

import pytest

from helpers import generic_extractor_page
from kg_pipeline.discover import MAX_PAGES, discover_pages, host_key, match_page_type, resolve_links


def urls(pages: list[dict[str, str]]) -> list[str]:
    return [p["url"] for p in pages]


def test_real_fixture_links_are_plain_absolute_strings(close_homepage):
    links = close_homepage["links"]
    assert all(isinstance(link, str) for link in links)
    assert sum(link.startswith("https://") for link in links) == len(links) - 1


def test_real_fixture_discovers_company_pages(close_homepage):
    assert close_homepage["url"] == "https://www.close.com/"
    pages = discover_pages(close_homepage["url"], close_homepage["links"])
    assert urls(pages) == [
        "https://close.com/about",
        "https://close.com/partners",
        "https://close.com/integrations",
        "https://close.com/careers",
    ]
    assert [p["page_type"] for p in pages] == ["about", "partners", "integrations", "careers"]


@pytest.mark.parametrize("name", ["pipedrive_com", "zendesk_com", "basecamp_com", "hey_com"])
def test_real_fixtures_only_keep_same_host_pages(name):
    page = generic_extractor_page(name)
    for found in discover_pages(page["url"], page["links"]):
        assert host_key(found["url"]) == host_key(page["url"])


def test_relative_hrefs_are_resolved_against_the_page_url():
    links = ["/about", "team", "../partners", "./integrations/", "https://example.com/careers"]
    resolved = resolve_links("https://example.com/company/", links)
    assert resolved == [
        "https://example.com/about",
        "https://example.com/company/team",
        "https://example.com/partners",
        "https://example.com/company/integrations",
        "https://example.com/careers",
    ]


def test_documented_dict_links_also_work():
    links = [{"href": "/about-us", "text": "About"}, {"href": "https://example.com/team", "text": "Team"}]
    assert urls(discover_pages("https://example.com/", links)) == [
        "https://example.com/about-us",
        "https://example.com/team",
    ]


def test_same_host_filter_drops_subdomains_and_other_sites():
    links = [
        "https://app.close.com/signup/",
        "https://help.close.com/about",
        "https://chatgpt.com/?q=evaluate%20the%20close%20team",
        "https://close.com/about",
        "https://www.close.com/careers",
    ]
    assert urls(discover_pages("https://www.close.com/", links)) == [
        "https://close.com/about",
        "https://www.close.com/careers",
    ]


def test_skips_mailto_tel_javascript_and_fragments():
    links = ["mailto:jason@basecamp.com", "tel:+18334625673", "javascript:void(0)", "#team", ""]
    assert resolve_links("https://basecamp.com/", links) == []


def test_query_strings_fragments_and_trailing_slashes_collapse():
    links = ["https://example.com/about/", "https://example.com/about?utm_source=x", "https://example.com/about#top"]
    assert urls(discover_pages("https://example.com/", links)) == ["https://example.com/about"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/en/about", "about"),
        ("https://example.com/our-team", "team"),
        ("https://example.com/partner/", "partners"),
        ("https://example.com/integrations", "integrations"),
        ("https://example.com/en/marketplace", "integrations"),
        ("https://example.com/company/careers/", "careers"),
        ("https://example.com/en/jobs", "careers"),
        ("https://example.com/blog/playbook-to-scaling-sales-teams", None),
        ("https://example.com/company/legal", None),
        ("https://example.com/apps", None),
        ("https://example.com/", None),
    ],
)
def test_pattern_match_uses_the_last_path_segment(url, expected):
    assert match_page_type(url) == expected


def test_deep_pages_under_a_matching_folder_are_skipped():
    links = [f"https://example.com/integrations/tool-{i}" for i in range(20)]
    assert discover_pages("https://example.com/", links) == []


def test_page_cap_and_round_robin_across_types():
    langs = ["en", "de", "fr", "es", "pt", "it", "nl", "ja", "ko", "pl"]
    links = [f"https://example.com/{lang}/integrations" for lang in langs]
    links += ["https://example.com/about", "https://example.com/careers"]
    pages = discover_pages("https://example.com/", links)
    assert len(pages) == MAX_PAGES
    assert [p["page_type"] for p in pages[:3]] == ["about", "integrations", "careers"]
    assert urls(pages)[:3] == [
        "https://example.com/about",
        "https://example.com/en/integrations",
        "https://example.com/careers",
    ]


def test_custom_cap():
    links = [f"https://example.com/{lang}/team" for lang in ("en", "de", "fr", "es", "pt")]
    assert len(discover_pages("https://example.com/", links, max_pages=2)) == 2


def test_www_and_bare_host_duplicates_collapse():
    links = ["https://close.com/about", "https://www.close.com/about/"]
    assert urls(discover_pages("https://www.close.com/", links)) == ["https://close.com/about"]


def test_homepage_itself_is_not_returned():
    assert discover_pages("https://example.com/", ["https://example.com/", "https://www.example.com"]) == []


def test_real_geo_redirect_still_finds_pages_on_the_seed_host():
    page = generic_extractor_page("zendesk_georedirect")
    assert host_key(page["url"]) == "zendesk.de"
    pages = discover_pages("https://www.zendesk.com/", page["links"], final_url=page["url"])
    assert {p["page_type"] for p in pages} == {"about", "partners", "integrations", "careers"}
    assert all(host_key(p["url"]) == "zendesk.com" for p in pages)


def test_relative_links_resolve_against_the_final_url():
    pages = discover_pages("https://example.com/", ["/about", "https://example.com/team"],
                           final_url="https://www.example.com/en/")
    assert urls(pages) == ["https://www.example.com/about", "https://example.com/team"]

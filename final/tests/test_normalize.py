from __future__ import annotations

import pytest

from kg_pipeline.normalize import build_name_map, canonical_key, normalize_records


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Stripe, Inc.", "stripe"),
        ("Salesforce.com", "salesforce"),
        ("HubSpot", "hubspot"),
        ("Apollo.io", "apollo"),
        ("Zendesk GmbH", "zendesk"),
        ("  Google   Calendar ", "google calendar"),
    ],
)
def test_canonical_key(name, key):
    assert canonical_key(name) == key


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Stripe", "Stripe, Inc."),
        ("Salesforce", "Salesforce.com"),
        ("HubSpot", "Hubspot"),
        ("Google Calendar", "Google Calender"),
        ("Microsoft Teams", "Microsoft Teams."),
    ],
)
def test_near_duplicates_merge(a, b):
    mapping = build_name_map([a, a, b])
    assert mapping[b] == a


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Notion", "Motion"),
        ("Zoom", "Zoho"),
        ("Asana", "Basecamp"),
        ("GitHub", "GitLab"),
        ("Close", "Clay"),
    ],
)
def test_different_names_stay_separate(a, b):
    mapping = build_name_map([a, b])
    assert mapping[a] == a
    assert mapping[b] == b


def test_preferred_seed_name_wins():
    mapping = build_name_map(["Pipedrive Inc.", "Pipedrive Inc.", "Pipedrive"], preferred=["Pipedrive"])
    assert mapping["Pipedrive Inc."] == "Pipedrive"


def page(url: str, **lists) -> dict:
    base = {"companies": [], "people": [], "products": [], "integrations": [], "locations": [], "relationships": []}
    return {"company": "X", "url": url, "rid": "r", "extracted_at": "t", "result": {**base, **lists}}


def test_records_are_rewritten_across_pages_and_types_stay_separate():
    records = [
        page("https://a.com/integrations",
             companies=[{"name": "Acme", "source_quote": "q"}],
             integrations=[{"name": "Zapier", "source_quote": "q"}, {"name": "Zapier Inc.", "source_quote": "q"}],
             relationships=[
                 {"source": "Acme", "type": "INTEGRATES_WITH", "target": "Zapier", "source_quote": "q"},
                 {"source": "Acme", "type": "INTEGRATES_WITH", "target": "Zapier Inc.", "source_quote": "q"},
             ]),
        page("https://b.com/about",
             companies=[{"name": "Zapier", "source_quote": "q"}],
             locations=[{"name": "Austin", "country": "USA", "source_quote": "q"}]),
    ]
    normalized, merges = normalize_records(records, seed_companies=["Acme"])
    first = normalized[0]["result"]
    assert [i["name"] for i in first["integrations"]] == ["Zapier"]
    assert len(first["relationships"]) == 1
    assert ("Integration", "Zapier Inc.", "Zapier") in merges
    assert normalized[1]["result"]["companies"][0]["name"] == "Zapier"
    assert normalized[1]["result"]["locations"][0]["country"] == "United States"
    assert records[0]["result"]["integrations"][1]["name"] == "Zapier Inc."


def test_self_partnership_after_merge_is_dropped():
    records = [page("https://a.com/partners",
                    companies=[{"name": "Acme", "source_quote": "q"}, {"name": "Acme Inc.", "source_quote": "q"}],
                    relationships=[{"source": "Acme", "type": "PARTNERS_WITH", "target": "Acme Inc.",
                                    "source_quote": "q"}])]
    normalized, _ = normalize_records(records, seed_companies=["Acme"])
    assert normalized[0]["result"]["relationships"] == []

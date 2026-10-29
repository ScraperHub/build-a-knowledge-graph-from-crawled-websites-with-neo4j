from __future__ import annotations

from helpers import load_fixture
from kg_pipeline.extract import (
    add_implied_relationships,
    apply_guard,
    clean_for_company,
    normalize_text,
    quote_in_page,
)
from kg_pipeline.schema import ExtractionResult


def result(**lists) -> ExtractionResult:
    base = {"companies": [], "people": [], "products": [], "integrations": [], "locations": [], "relationships": []}
    return ExtractionResult.model_validate({**base, **lists})


def test_keeps_real_quotes_from_a_real_page(close_about_markdown):
    extracted = result(
        companies=[{"name": "Close", "source_quote": "Close is a fully remote team working around the world."}],
        people=[{"name": "Steli Efti", "title": "CEO & Co-Founder", "employer": "Close",
                 "source_quote": "Steli Efti CEO & Co-Founder"}],
        relationships=[{"source": "Steli Efti", "type": "WORKS_AT", "target": "Close",
                        "source_quote": "Steli Efti CEO & Co-Founder"}],
    )
    report = apply_guard(extracted, close_about_markdown)
    assert report.dropped == []
    assert report.kept == 3


def test_drops_invented_quotes_and_their_relationships(close_about_markdown):
    extracted = result(
        companies=[{"name": "Close", "source_quote": "Close is a fully remote team working around the world."}],
        people=[{"name": "Elon Musk", "title": "Advisor", "employer": "Close",
                 "source_quote": "Elon Musk joined Close as an advisor"}],
        relationships=[{"source": "Elon Musk", "type": "WORKS_AT", "target": "Close",
                        "source_quote": "Elon Musk joined Close as an advisor"}],
    )
    report = apply_guard(extracted, close_about_markdown)
    assert [p.name for p in report.result.people] == []
    assert report.result.relationships == []
    assert {d["kind"] for d in report.dropped} == {"people", "relationship"}


def test_drops_relationship_with_a_fake_quote_even_when_entities_are_real(close_about_markdown):
    extracted = result(
        companies=[{"name": "Close", "source_quote": "Close is a fully remote team working around the world."}],
        locations=[{"name": "Paris", "country": "France", "source_quote": "fully remote team"}],
        relationships=[{"source": "Close", "type": "LOCATED_IN", "target": "Paris",
                        "source_quote": "Our headquarters are in Paris"}],
    )
    report = apply_guard(extracted, close_about_markdown)
    assert report.result.relationships == []
    assert report.dropped[0]["kind"] == "relationship"


def test_real_llm_output_drops_relationships_to_unlisted_companies():
    page = load_fixture("page_pipedrive_home.json")
    raw = ExtractionResult.model_validate(load_fixture("llm_pipedrive_home.json"))
    report = apply_guard(raw, page["markdown"])
    missing = [d for d in report.dropped if d.get("reason") == "missing endpoint"]
    assert len(missing) == 3
    assert all(d["kind"] == "relationship" for d in missing)


def test_real_llm_output_quotes_are_found_on_the_real_page():
    page = load_fixture("page_pipedrive_marketplace.json")
    raw = ExtractionResult.model_validate(load_fixture("llm_pipedrive_marketplace.json"))
    report = apply_guard(raw, page["markdown"])
    assert len(report.result.integrations) == len(raw.integrations) > 10
    assert report.dropped == []


def test_markdown_links_and_formatting_are_flattened():
    page = "**Nirmal Gyanwali** Managing Director\n\n[See open roles](https://close.com/careers)"
    normalized = normalize_text(page)
    assert quote_in_page("Nirmal Gyanwali Managing Director", normalized)
    assert quote_in_page("See open roles", normalized)
    assert not quote_in_page("close.com/careers", normalized)


def test_curly_quotes_dashes_whitespace_and_trailing_punctuation():
    normalized = normalize_text("Tallinn, Estonia \u2013 the city where Pipedrive was born \u2013 for a party.\n\nWe\u2019re hiring")
    assert quote_in_page("Tallinn, Estonia - the city where Pipedrive was born.", normalized)
    assert quote_in_page("We're   hiring", normalized)
    assert quote_in_page("jason@basecamp.com Co-founder", normalize_text("[jason@basecamp.com](mailto:x)Co-founder"))


def test_paraphrases_and_short_quotes_are_rejected():
    normalized = normalize_text("Pipedrive was founded in 2010 in Tallinn.")
    assert not quote_in_page("Pipedrive was started in 2010 in Tallinn", normalized)
    assert not quote_in_page("a", normalized)


def test_clean_for_company_drops_testimonial_people_and_strips_suffixes():
    extracted = result(
        companies=[{"name": "Pipedrive", "source_quote": "x" * 5}],
        people=[
            {"name": "Paulo Cunha", "title": "CEO", "employer": "Pipedrive", "source_quote": "Paulo Cunha, CEO"},
            {"name": "Suds Singh", "title": "Founder and MD", "employer": "Interesting Content",
             "source_quote": "Suds Singh Founder and MD"},
        ],
        integrations=[{"name": "Stripe for Pipedrive", "source_quote": "Stripe for Pipedrive"}],
        relationships=[{"source": "Pipedrive", "type": "INTEGRATES_WITH", "target": "Stripe for Pipedrive",
                        "source_quote": "Stripe for Pipedrive"}],
    )
    cleaned = clean_for_company(extracted, "Pipedrive")
    assert [p.name for p in cleaned.people] == ["Paulo Cunha"]
    assert cleaned.integrations[0].name == "Stripe"
    assert cleaned.relationships[0].target == "Stripe"


def test_implied_relationships_are_added_once():
    extracted = result(
        people=[{"name": "Jason Fried", "title": "CEO", "employer": None, "source_quote": "Jason Fried, CEO"}],
        integrations=[{"name": "Slack", "source_quote": "Basecamp works with Slack"}],
        locations=[{"name": "Chicago", "country": "United States", "source_quote": "based in Chicago"}],
        relationships=[{"source": "Basecamp", "type": "INTEGRATES_WITH", "target": "Slack",
                        "source_quote": "Basecamp works with Slack"}],
    )
    out = add_implied_relationships(extracted, "Basecamp")
    triples = sorted((r.source, r.type, r.target) for r in out.relationships)
    assert triples == [
        ("Basecamp", "INTEGRATES_WITH", "Slack"),
        ("Basecamp", "LOCATED_IN", "Chicago"),
        ("Jason Fried", "WORKS_AT", "Basecamp"),
    ]

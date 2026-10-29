from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from helpers import load_fixture
from kg_pipeline.schema import ExtractionResult

GOOD = {
    "companies": [{"name": "Close", "source_quote": "In 2013, that internal tool became Close."}],
    "people": [{"name": "Steli Efti", "title": "CEO & Co-Founder", "employer": "Close",
                "source_quote": "Steli Efti CEO & Co-Founder"}],
    "products": [],
    "integrations": [{"name": "Zapier", "source_quote": "Connect Close to Zapier"}],
    "locations": [{"name": "Tallinn", "country": "Estonia", "source_quote": "Tallinn, Estonia"}],
    "relationships": [{"source": "Steli Efti", "type": "WORKS_AT", "target": "Close",
                       "source_quote": "Steli Efti CEO & Co-Founder"}],
}


def test_good_payload_parses():
    result = ExtractionResult.model_validate(GOOD)
    assert result.people[0].title == "CEO & Co-Founder"
    assert result.names_by_label()["Integration"] == {"Zapier"}


@pytest.mark.parametrize("fixture", ["llm_pipedrive_home.json", "llm_pipedrive_marketplace.json"])
def test_real_llm_output_parses(fixture):
    result = ExtractionResult.model_validate(load_fixture(fixture))
    assert result.companies[0].name == "Pipedrive"


def broken(path: list, value) -> dict:
    payload = copy.deepcopy(GOOD)
    target = payload
    for key in path[:-1]:
        target = target[key]
    if value is KeyError:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return payload


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["people", 0, "source_quote"], KeyError),
        (["companies", 0, "source_quote"], ""),
        (["companies", 0, "name"], ""),
        (["relationships", 0, "type"], "ACQUIRED"),
        (["relationships", 0, "source_quote"], KeyError),
        (["people", 0, "title"], KeyError),
        (["people", 0, "salary"], "100k"),
        (["integrations"], "Zapier"),
        (["locations"], KeyError),
    ],
)
def test_bad_payloads_are_rejected(path, value):
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(broken(path, value))


def test_unknown_top_level_key_is_rejected():
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({**GOOD, "investors": []})


def test_json_schema_is_strict_enough_for_structured_outputs():
    schema = ExtractionResult.model_json_schema()
    assert schema["additionalProperties"] is False
    relationship = schema["$defs"]["Relationship"]
    assert set(relationship["properties"]["type"]["enum"]) == {
        "WORKS_AT", "OFFERS", "INTEGRATES_WITH", "PARTNERS_WITH", "LOCATED_IN",
    }

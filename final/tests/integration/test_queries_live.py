"""The three cross-company queries return real rows on the small seed graph."""

from __future__ import annotations

import pytest

from kg_pipeline.queries import company_communities, run_all_queries

pytestmark = pytest.mark.integration


def test_all_three_queries_return_rows(driver, loaded_graph):
    results = run_all_queries(driver)
    assert set(results) == {"shared_integrations", "shared_people", "geo_clusters"}
    for name, rows in results.items():
        assert rows, f"{name} returned no rows"


def test_shared_integrations_between_basecamp_and_pipedrive(driver, loaded_graph):
    rows = run_all_queries(driver)["shared_integrations"]
    pair = next(r for r in rows if {r["company_a"], r["company_b"]} == {"Basecamp", "Pipedrive"})
    assert {"Zapier", "Trello"} <= set(pair["shared_integrations"])


def test_jason_fried_appears_on_two_companies(driver, loaded_graph):
    rows = run_all_queries(driver)["shared_people"]
    jason = next(r for r in rows if r["person"] == "Jason Fried")
    assert set(jason["companies"]) == {"Basecamp", "HEY"}


def test_geo_clusters_group_companies_by_country(driver, loaded_graph):
    rows = run_all_queries(driver)["geo_clusters"]
    assert all(r["company_count"] >= 2 for r in rows)
    assert any(set(r["companies"]) == {"Pipedrive", "Zendesk"} for r in rows)


def test_networkx_communities(driver, loaded_graph):
    assert ["Basecamp", "Pipedrive"] in company_communities(driver)

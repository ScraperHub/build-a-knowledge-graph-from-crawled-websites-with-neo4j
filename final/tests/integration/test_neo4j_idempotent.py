"""Loading the same data twice must not change node or relationship counts."""

from __future__ import annotations

import pytest

from kg_pipeline.load import graph_counts, load_records

pytestmark = pytest.mark.integration


def test_second_load_creates_no_duplicates(driver, loaded_graph, recorded_records, seeds):
    first = loaded_graph
    assert first["nodes"] > 50
    assert first["relationships"] > 50
    second = load_records(driver, recorded_records, seeds)
    assert second == first
    assert graph_counts(driver) == first


def test_relationships_carry_provenance(driver, loaded_graph):
    with driver.session() as session:
        missing = session.run(
            "MATCH ()-[r]->() WHERE r.source_url IS NULL OR r.rid IS NULL OR r.extracted_at IS NULL "
            "RETURN count(r) AS c"
        ).single()["c"]
        nodes_without_rid = session.run(
            "MATCH (n) WHERE NOT n:Company AND size(coalesce(n.rids, [])) = 0 RETURN count(n) AS c"
        ).single()["c"]
    assert missing == 0
    assert nodes_without_rid == 0


def test_each_name_is_unique_per_label(driver, loaded_graph):
    with driver.session() as session:
        duplicates = session.run(
            "MATCH (n) WITH labels(n)[0] AS label, n.name AS name, count(*) AS c WHERE c > 1 RETURN count(*) AS d"
        ).single()["d"]
    assert duplicates == 0

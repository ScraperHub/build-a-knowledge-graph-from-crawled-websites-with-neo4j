"""One GraphRAG question end to end, plus proof that the database rejects writes in read mode."""

from __future__ import annotations

import pytest
from neo4j.exceptions import Neo4jError

from kg_pipeline.graphrag import ask, run_read_only
from kg_pipeline.load import graph_counts

pytestmark = pytest.mark.integration


def test_graphrag_answer_cites_provenance(llm, settings, driver, loaded_graph):
    result = ask(llm, settings.openai_model, driver, "Which integrations do Basecamp and Pipedrive have in common?")
    assert result.rows
    assert result.sources
    known_rids = {s["rid"] for s in result.sources}
    assert any(rid in result.answer for rid in known_rids)
    assert any(name in result.answer for name in ("Zapier", "Trello", "Asana", "Stripe"))


def test_read_transaction_rejects_writes_even_without_the_keyword_check(driver, loaded_graph):
    before = graph_counts(driver)
    with pytest.raises(Neo4jError):
        run_read_only(driver, "CREATE (n:Company {name: 'Injected'}) RETURN n")
    assert graph_counts(driver) == before

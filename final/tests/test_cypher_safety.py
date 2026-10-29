from __future__ import annotations

import pytest

from kg_pipeline.graphrag import UnsafeCypherError, check_read_only, collect_sources

BLOCKED = [
    "CREATE (n:Company {name: 'Evil'})",
    "MATCH (n) DETACH DELETE n",
    "MATCH (n) DELETE n",
    "MERGE (c:Company {name: 'Acme'}) RETURN c",
    "MATCH (c:Company) SET c.name = 'x' RETURN c",
    "MATCH (c:Company) REMOVE c.website RETURN c",
    "DROP CONSTRAINT company_name",
    "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
    "CALL apoc.periodic.iterate('MATCH (n) RETURN n', 'DELETE n', {})",
    "CALL dbms.security.createUser('x', 'y')",
    "MATCH (n) CALL { WITH n DELETE n } RETURN 1",
    "MATCH (n) FOREACH (x IN [1] | SET n.flag = true)",
    "MATCH (n) RETURN n; MATCH (m) DELETE m",
    "match (n) detach delete n",
    "MaTcH (n) SeT n.x = 1",
    "MATCH (n)\nWITH n\nCREATE (m)",
    "USE system SHOW USERS",
    "SHOW DATABASES",
    "  // comment\n  CREATE (n)",
]

ALLOWED = [
    "MATCH (c:Company) RETURN c.name LIMIT 5",
    "MATCH (c:Company) RETURN c.name;",
    "OPTIONAL MATCH (p:Person)-[r:WORKS_AT]->(c) RETURN p.name, r.source_url, r.rid",
    "MATCH (c:Company) WHERE c.name = 'CREATE DELETE SET' RETURN c",
    "MATCH (c:Company) WHERE c.name CONTAINS \"merge\" RETURN c",
    "MATCH (c:`Company`) RETURN c // DELETE everything",
    "WITH ['a', 'b'] AS xs UNWIND xs AS x RETURN x",
    "MATCH (c:Company)-[:INTEGRATES_WITH]->(i) WITH i, count(c) AS n WHERE n > 1 RETURN i.name, n",
]


@pytest.mark.parametrize("cypher", BLOCKED)
def test_write_and_admin_queries_are_blocked(cypher):
    with pytest.raises(UnsafeCypherError):
        check_read_only(cypher)


@pytest.mark.parametrize("cypher", ALLOWED)
def test_read_queries_pass(cypher):
    assert check_read_only(cypher).rstrip(";") == cypher.strip().rstrip(";")


def test_collect_sources_flat_rows():
    rows = [{"integration": "Zapier", "source_url": "https://a.com/i", "rid": "r1"},
            {"integration": "Slack", "source_url": "https://a.com/i", "rid": "r1"}]
    assert collect_sources(rows) == [{"source_url": "https://a.com/i", "rid": "r1"}]


def test_collect_sources_nested_and_list_columns():
    rows = [{"person": "Jason Fried", "provenance": [{"source_url": "https://hey.com/", "rid": "r2"}]},
            {"source_urls": ["https://b.com/1", "https://b.com/2"], "rids": ["r3", "r4"]}]
    assert collect_sources(rows) == [
        {"source_url": "https://hey.com/", "rid": "r2"},
        {"source_url": "https://b.com/1", "rid": "r3"},
        {"source_url": "https://b.com/2", "rid": "r4"},
    ]


def test_collect_sources_empty_when_no_provenance():
    assert collect_sources([{"name": "Basecamp"}]) == []

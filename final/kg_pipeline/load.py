"""Idempotent Neo4j loader. MERGE on names for nodes and on (endpoints, type, source_url) for relationships."""

from __future__ import annotations

from typing import Any, Iterable

from neo4j import Driver

from .normalize import ENTITY_LISTS
from .schema import RELATIONSHIP_ENDPOINTS

LABELS = tuple(ENTITY_LISTS.values())

NODE_QUERY = """
UNWIND $rows AS row
MERGE (n:{label} {{name: row.name}})
ON CREATE SET n.created_at = row.extracted_at
SET n += row.props,
    n.source_urls = CASE WHEN row.source_url IN coalesce(n.source_urls, [])
                    THEN n.source_urls ELSE coalesce(n.source_urls, []) + row.source_url END,
    n.rids = CASE WHEN row.rid IN coalesce(n.rids, [])
             THEN n.rids ELSE coalesce(n.rids, []) + row.rid END
"""

RELATIONSHIP_QUERY = """
UNWIND $rows AS row
MATCH (a:{source_label} {{name: row.source}})
MATCH (b:{target_label} {{name: row.target}})
MERGE (a)-[r:{rel_type} {{source_url: row.source_url}}]->(b)
SET r.rid = row.rid, r.extracted_at = row.extracted_at, r.source_quote = row.source_quote
"""

SEED_QUERY = """
UNWIND $rows AS row
MERGE (c:Company {name: row.name})
SET c.website = row.homepage, c.seed = true
"""


def ensure_constraints(driver: Driver) -> None:
    """One uniqueness constraint per label. This also creates the index MERGE uses."""
    with driver.session() as session:
        for label in LABELS:
            session.run(f"CREATE CONSTRAINT {label.lower()}_name IF NOT EXISTS FOR (n:{label}) REQUIRE n.name IS UNIQUE")


def build_rows(records: Iterable[dict[str, Any]]) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Flatten page records into node rows per label and relationship rows per type."""
    nodes: dict[str, list[dict]] = {label: [] for label in LABELS}
    rels: dict[str, list[dict]] = {rel_type: [] for rel_type in RELATIONSHIP_ENDPOINTS}
    for record in records:
        provenance = {"source_url": record["url"], "rid": record["rid"], "extracted_at": record["extracted_at"]}
        for list_name, label in ENTITY_LISTS.items():
            for entity in record["result"][list_name]:
                props = {k: v for k, v in entity.items() if k in ("title", "country") and v}
                nodes[label].append({"name": entity["name"], "props": props, **provenance})
        for rel in record["result"]["relationships"]:
            rels[rel["type"]].append({"source": rel["source"], "target": rel["target"],
                                      "source_quote": rel["source_quote"], **provenance})
    return nodes, rels


def load_records(driver: Driver, records: list[dict[str, Any]], seeds: list[dict[str, str]] = ()) -> dict[str, int]:
    """Write seeds, nodes, and relationships. Safe to run any number of times."""
    ensure_constraints(driver)
    nodes, rels = build_rows(records)
    with driver.session() as session:
        if seeds:
            session.run(SEED_QUERY, rows=[{"name": s["name"], "homepage": s["homepage"]} for s in seeds]).consume()
        for label, rows in nodes.items():
            if rows:
                session.run(NODE_QUERY.format(label=label), rows=rows).consume()
        for rel_type, rows in rels.items():
            if rows:
                source_label, target_label = RELATIONSHIP_ENDPOINTS[rel_type]
                query = RELATIONSHIP_QUERY.format(source_label=source_label, target_label=target_label, rel_type=rel_type)
                session.run(query, rows=rows).consume()
    return graph_counts(driver)


def graph_counts(driver: Driver) -> dict[str, int]:
    with driver.session() as session:
        nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        relationships = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    return {"nodes": nodes, "relationships": relationships}


def clear_graph(driver: Driver) -> None:
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n").consume()

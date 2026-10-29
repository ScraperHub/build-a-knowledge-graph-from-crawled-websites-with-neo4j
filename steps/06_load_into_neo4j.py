"""Step 6: load the graph with MERGE, twice, and show that the counts do not change."""

from datetime import datetime, timezone

from neo4j import GraphDatabase

from _common import NEO4J_AUTH, NEO4J_URI, SEEDS, load

LISTS = {"companies": "Company", "people": "Person", "products": "Product",
         "integrations": "Integration", "locations": "Location"}
ENDPOINTS = {"WORKS_AT": ("Person", "Company"), "OFFERS": ("Company", "Product"),
             "INTEGRATES_WITH": ("Company", "Integration"), "PARTNERS_WITH": ("Company", "Company"),
             "LOCATED_IN": ("Company", "Location")}

NODE = """
UNWIND $rows AS row
MERGE (n:{label} {{name: row.name}})
SET n += row.props,
    n.source_urls = CASE WHEN row.url IN coalesce(n.source_urls, []) THEN n.source_urls
                    ELSE coalesce(n.source_urls, []) + row.url END,
    n.rids = CASE WHEN row.rid IN coalesce(n.rids, []) THEN n.rids ELSE coalesce(n.rids, []) + row.rid END
"""

REL = """
UNWIND $rows AS row
MATCH (a:{source} {{name: row.source}}), (b:{target} {{name: row.target}})
MERGE (a)-[r:{type} {{source_url: row.url}}]->(b)
SET r.rid = row.rid, r.extracted_at = row.extracted_at, r.source_quote = row.source_quote
"""


def load_graph(session, records: list[dict], extracted_at: str) -> None:
    session.run("UNWIND $seeds AS s MERGE (c:Company {name: s.name}) SET c.website = s.homepage", seeds=SEEDS)
    for field, label in LISTS.items():
        rows = [{"name": e["name"], "url": r["url"], "rid": r["rid"],
                 "props": {k: e[k] for k in ("title", "country") if e.get(k)}}
                for r in records for e in r["result"][field]]
        session.run(NODE.format(label=label), rows=rows)
    for rel_type, (source, target) in ENDPOINTS.items():
        rows = [{**rel, "url": r["url"], "rid": r["rid"], "extracted_at": extracted_at}
                for r in records for rel in r["result"]["relationships"] if rel["type"] == rel_type]
        session.run(REL.format(source=source, target=target, type=rel_type), rows=rows)


def counts(session) -> tuple[int, int]:
    nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    return nodes, rels


records = load("normalized.json")
extracted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
with GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH) as driver, driver.session() as session:
    session.run("MATCH (n) DETACH DELETE n")
    for label in LISTS.values():
        session.run(f"CREATE CONSTRAINT {label.lower()}_name IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.name IS UNIQUE")
    for run in (1, 2):
        load_graph(session, records, extracted_at)
        nodes, rels = counts(session)
        print(f"After load {run}: {nodes} nodes, {rels} relationships")

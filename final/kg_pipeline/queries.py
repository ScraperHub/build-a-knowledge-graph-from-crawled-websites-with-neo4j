"""Cross-company Cypher queries, plus an optional networkx community example."""

from __future__ import annotations

from typing import Any

from neo4j import Driver

SHARED_INTEGRATIONS = """
MATCH (a:Company)-[:INTEGRATES_WITH]->(i:Integration)<-[:INTEGRATES_WITH]-(b:Company)
WHERE a.name < b.name
RETURN a.name AS company_a, b.name AS company_b,
       count(DISTINCT i) AS shared_count, collect(DISTINCT i.name)[..8] AS shared_integrations
ORDER BY shared_count DESC
LIMIT 10
"""

SHARED_PEOPLE = """
MATCH (p:Person)-[r:WORKS_AT]->(c:Company)
WITH p, collect(DISTINCT c.name) AS companies, collect(DISTINCT r.source_url) AS pages
WHERE size(companies) >= 2
RETURN p.name AS person, p.title AS title, companies, pages
ORDER BY size(companies) DESC, person
"""

GEO_CLUSTERS = """
MATCH (c:Company)-[:LOCATED_IN]->(l:Location)
WHERE l.country IS NOT NULL
WITH l.country AS country, collect(DISTINCT c.name) AS companies, collect(DISTINCT l.name) AS cities
WHERE size(companies) >= 2
RETURN country, size(companies) AS company_count, companies, cities
ORDER BY company_count DESC, country
"""

QUERIES = {
    "shared_integrations": SHARED_INTEGRATIONS,
    "shared_people": SHARED_PEOPLE,
    "geo_clusters": GEO_CLUSTERS,
}


def run_query(driver: Driver, cypher: str, **params: Any) -> list[dict[str, Any]]:
    with driver.session() as session:
        return session.execute_read(lambda tx: [r.data() for r in tx.run(cypher, **params)])


def run_all_queries(driver: Driver) -> dict[str, list[dict[str, Any]]]:
    return {name: run_query(driver, cypher) for name, cypher in QUERIES.items()}


def company_communities(driver: Driver) -> list[list[str]]:
    """Group companies that share integrations, using greedy modularity from networkx."""
    import networkx as nx
    from networkx.algorithms.community import greedy_modularity_communities

    graph = nx.Graph()
    for row in run_query(driver, SHARED_INTEGRATIONS.replace("LIMIT 10", "")):
        graph.add_edge(row["company_a"], row["company_b"], weight=row["shared_count"])
    if graph.number_of_edges() == 0:
        return []
    return [sorted(group) for group in greedy_modularity_communities(graph, weight="weight")]

"""Step 7: three cross-company questions that a flat table cannot answer easily."""

import json

from neo4j import GraphDatabase

from _common import NEO4J_AUTH, NEO4J_URI

QUERIES = {
    "Shared integrations": """
        MATCH (a:Company)-[:INTEGRATES_WITH]->(i:Integration)<-[:INTEGRATES_WITH]-(b:Company)
        WHERE a.name < b.name
        RETURN a.name AS company_a, b.name AS company_b,
               count(DISTINCT i) AS shared, collect(DISTINCT i.name)[..6] AS integrations
        ORDER BY shared DESC LIMIT 5""",
    "People on two companies' sites": """
        MATCH (p:Person)-[r:WORKS_AT]->(c:Company)
        WITH p, collect(DISTINCT c.name) AS companies, collect(DISTINCT r.source_url) AS pages
        WHERE size(companies) >= 2
        RETURN p.name AS person, companies, pages""",
    "Geographic clusters": """
        MATCH (c:Company)-[:LOCATED_IN]->(l:Location)
        WITH l.country AS country, collect(DISTINCT c.name) AS companies, collect(DISTINCT l.name) AS cities
        WHERE size(companies) >= 2
        RETURN country, companies, cities ORDER BY size(companies) DESC""",
}

with GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH) as driver:
    for title, cypher in QUERIES.items():
        records, _, _ = driver.execute_query(cypher)
        print(f"\n{title}:")
        for record in records:
            print("  ", json.dumps(record.data(), ensure_ascii=False))

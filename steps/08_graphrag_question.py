"""Step 8: GraphRAG. The model writes read-only Cypher, the graph answers, and the reply cites rids."""

import json
import re
import sys

from neo4j import GraphDatabase
from openai import OpenAI
from pydantic import BaseModel

from _common import NEO4J_AUTH, NEO4J_URI, OPENAI_MODEL

SCHEMA = """Nodes (all have name, source_urls, rids): Company {website}, Person {title}, Product,
Integration, Location {country}.
Relationships (all have source_url, rid, extracted_at, source_quote):
(:Person)-[:WORKS_AT]->(:Company), (:Company)-[:OFFERS]->(:Product),
(:Company)-[:INTEGRATES_WITH]->(:Integration), (:Company)-[:PARTNERS_WITH]->(:Company),
(:Company)-[:LOCATED_IN]->(:Location)"""

CYPHER_PROMPT = f"""Write one read-only Cypher query for this Neo4j graph.
{SCHEMA}
Rules: never write data or use CALL. Give every relationship a variable and return
r.source_url AS source_url, r.rid AS rid for each one, one row per relationship.
Compare names with toLower(n.name) = toLower('Name'). Add LIMIT 25.
Example for two companies: MATCH (a:Company)-[r1:INTEGRATES_WITH]->(i)<-[r2:INTEGRATES_WITH]-(b:Company)
WHERE toLower(a.name) = toLower('A') AND toLower(b.name) = toLower('B')
UNWIND [r1, r2] AS r RETURN i.name AS integration, startNode(r).name AS company,
r.source_url AS source_url, r.rid AS rid LIMIT 25"""

WRITE_WORDS = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|FOREACH|CALL)\b", re.I)


class Query(BaseModel):
    cypher: str


def check_read_only(cypher: str) -> str:
    """Reject write clauses. String literals are blanked first so names like 'Merge Labs' pass."""
    code = re.sub(r"'[^']*'|\"[^\"]*\"", "''", cypher).strip().rstrip(";")
    if ";" in code or WRITE_WORDS.search(code) or not re.match(r"(?i)\s*(MATCH|OPTIONAL|WITH|UNWIND)", code):
        raise ValueError(f"Blocked query: {cypher}")
    return cypher.strip().rstrip(";")


def ask(question: str) -> None:
    client = OpenAI()
    completion = client.chat.completions.parse(
        model=OPENAI_MODEL, temperature=0, response_format=Query,
        messages=[{"role": "system", "content": CYPHER_PROMPT}, {"role": "user", "content": question}])
    cypher = check_read_only(completion.choices[0].message.parsed.cypher)
    print("Cypher:\n" + cypher)

    with GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH) as driver, driver.session() as session:
        rows = session.execute_read(lambda tx: [r.data() for r in tx.run(cypher)])
    print(f"\nRows: {len(rows)}")

    answer = client.chat.completions.create(
        model=OPENAI_MODEL, temperature=0,
        messages=[{"role": "system", "content": "Answer from these graph rows only. The query already applied "
                                                "the question's filters. Cite each fact as [source_url, rid: RID]."},
                  {"role": "user", "content": f"Question: {question}\nRows: {json.dumps(rows)}"}])
    print("\nAnswer:\n" + answer.choices[0].message.content)


if __name__ == "__main__":
    try:
        check_read_only("MATCH (n) DETACH DELETE n")
    except ValueError as error:
        print("Safety check works:", error, "\n")
    ask(" ".join(sys.argv[1:]) or "Which integrations do Basecamp and Pipedrive have in common?")

"""GraphRAG: the LLM writes read-only Cypher from a schema description, and answers with provenance."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from neo4j import Driver
from neo4j.exceptions import Neo4jError
from pydantic import BaseModel

GRAPH_SCHEMA = """Node labels. Every node has: name, source_urls (list), rids (list).
- (:Company {name, website, seed})
- (:Person {name, title})
- (:Product {name})
- (:Integration {name})
- (:Location {name, country})

Relationships. Every relationship has: source_url, rid, extracted_at, source_quote.
- (:Person)-[:WORKS_AT]->(:Company)
- (:Company)-[:OFFERS]->(:Product)
- (:Company)-[:INTEGRATES_WITH]->(:Integration)
- (:Company)-[:PARTNERS_WITH]->(:Company)
- (:Company)-[:LOCATED_IN]->(:Location)"""

CYPHER_PROMPT = f"""You write one read-only Cypher query for Neo4j 5 that answers the user's question.

Graph schema:
{GRAPH_SCHEMA}

Rules:
- Use only MATCH, OPTIONAL MATCH, WHERE, WITH, UNWIND, RETURN, ORDER BY, LIMIT.
- Never write data and never use CALL.
- Return one row per matched relationship with its provenance as flat columns:
  r.source_url AS source_url, r.rid AS rid. Do not collect() provenance.
- Give every relationship a variable (r, r1, r2) and only RETURN variables bound in MATCH.
- Compare names case-insensitively on the property: WHERE toLower(c.name) = toLower('Acme').
- For "more than one" or "shared" questions, filter with an aggregate first, then MATCH
  again to return one provenance row per relationship.
- Add LIMIT 25 unless the question needs a count.

Example question: Which companies integrate with Slack?
Example query:
MATCH (c:Company)-[r:INTEGRATES_WITH]->(i:Integration)
WHERE toLower(i.name) = toLower('Slack')
RETURN c.name AS company, i.name AS integration, r.source_url AS source_url, r.rid AS rid
LIMIT 25

Example question: Which partners do Acme and Globex have in common?
Example query:
MATCH (a:Company)-[r1:PARTNERS_WITH]->(p:Company)<-[r2:PARTNERS_WITH]-(b:Company)
WHERE toLower(a.name) = toLower('Acme') AND toLower(b.name) = toLower('Globex')
UNWIND [r1, r2] AS r
RETURN p.name AS partner, startNode(r).name AS company, r.source_url AS source_url, r.rid AS rid
LIMIT 25

Example question: Which products are offered by more than one company?
Example query:
MATCH (c:Company)-[:OFFERS]->(p:Product)
WITH p, count(DISTINCT c) AS companies
WHERE companies > 1
MATCH (c:Company)-[r:OFFERS]->(p)
RETURN p.name AS product, c.name AS company, r.source_url AS source_url, r.rid AS rid
LIMIT 25"""

ANSWER_PROMPT = """You answer questions about a knowledge graph of companies.
You get the question, the Cypher query that was run to answer it, and the result rows.
The query already applied the question's filters, so every row is part of the answer.
Answer in a few sentences using only the rows. After each fact, cite [source_url, rid: RID].
If there are no rows, say the graph has no answer."""

FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|FOREACH|CALL|ALTER|GRANT|DENY|REVOKE|RENAME|"
    r"START|STOP|TERMINATE|USE|IMPORT)\b",
    re.IGNORECASE,
)
ALLOWED_START = re.compile(r"^\s*(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN)\b", re.IGNORECASE)


class UnsafeCypherError(ValueError):
    """Raised when generated Cypher is not a single read-only query."""


class CypherQuery(BaseModel):
    cypher: str


def strip_literals(cypher: str) -> str:
    """Remove comments, string literals, and backtick names so keywords inside them do not count."""
    cypher = re.sub(r"//[^\n]*|/\*.*?\*/", " ", cypher, flags=re.DOTALL)
    return re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`", "''", cypher)


def check_read_only(cypher: str) -> str:
    """Return the query without a trailing semicolon, or raise UnsafeCypherError."""
    query = cypher.strip().rstrip(";").strip()
    code = strip_literals(query)
    if ";" in code:
        raise UnsafeCypherError("multiple statements are not allowed")
    match = FORBIDDEN.search(code)
    if match:
        raise UnsafeCypherError(f"write or admin keyword not allowed: {match.group(1).upper()}")
    if not ALLOWED_START.match(code):
        raise UnsafeCypherError("query must start with MATCH, OPTIONAL MATCH, WITH, UNWIND, or RETURN")
    return query


@dataclass
class GraphAnswer:
    question: str
    cypher: str
    rows: list[dict[str, Any]]
    answer: str
    sources: list[dict[str, str]] = field(default_factory=list)


def collect_sources(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Find (source_url, rid) pairs in result rows, including inside nested maps and lists."""
    pairs: list[dict[str, str]] = []

    def add(url: Any, rid: Any) -> None:
        pair = {"source_url": str(url), "rid": str(rid or "")}
        if url and pair not in pairs:
            pairs.append(pair)

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            url_keys = [k for k in value if "source_url" in k.lower()]
            rid_keys = [k for k in value if k.lower() == "rid" or k.lower().endswith("rid") or k.lower().endswith("rids")]
            for url_key in url_keys:
                urls, rids = value[url_key], value[rid_keys[0]] if rid_keys else ""
                if isinstance(urls, list):
                    rid_list = rids if isinstance(rids, list) else [rids] * len(urls)
                    for url, rid in zip(urls, rid_list):
                        add(url, rid)
                else:
                    add(urls, rids)
            for key, item in value.items():
                if key not in url_keys and isinstance(item, (dict, list)):
                    walk(item)

    walk(rows)
    return pairs


def generate_cypher(client: Any, model: str, question: str, feedback: str = "") -> str:
    messages = [{"role": "system", "content": CYPHER_PROMPT}, {"role": "user", "content": question}]
    if feedback:
        messages.append({"role": "user", "content": feedback})
    completion = client.chat.completions.parse(model=model, temperature=0, response_format=CypherQuery,
                                               messages=messages)
    return completion.choices[0].message.parsed.cypher


def run_read_only(driver: Driver, cypher: str, limit: int = 50) -> list[dict[str, Any]]:
    """Run inside a read transaction, so the database also rejects writes."""
    with driver.session() as session:
        return session.execute_read(lambda tx: [r.data() for r in tx.run(cypher)][:limit])


def ask(client: Any, model: str, driver: Driver, question: str, max_attempts: int = 3) -> GraphAnswer:
    """Question to Cypher, Cypher to rows, rows to a cited answer.

    Bad Cypher, empty results, and missing provenance are fed back to the model for another try.
    Write queries raise UnsafeCypherError and never reach the database.
    """
    feedback, cypher, rows, sources = "", "", [], []
    for _ in range(max_attempts):
        cypher = check_read_only(generate_cypher(client, model, question, feedback))
        try:
            rows = run_read_only(driver, cypher)
        except Neo4jError as error:
            feedback = f"Your query was:\n{cypher}\nNeo4j rejected it: {error.message}\nFix the query."
            continue
        sources = collect_sources(rows)
        if rows and sources:
            break
        feedback = (f"Your query was:\n{cypher}\nIt returned {len(rows)} rows and {len(sources)} sources. "
                    "Rewrite it so it returns rows with r.source_url AS source_url and r.rid AS rid.")

    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": ANSWER_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nCypher:\n{cypher}\n\n"
                                        f"Rows:\n{json.dumps(rows, default=str)[:12000]}"},
        ],
    )
    return GraphAnswer(question, cypher, rows, completion.choices[0].message.content or "", sources)

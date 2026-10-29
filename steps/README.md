# Step-by-step scripts

One short script per blog section. Each script does one thing, prints what it did, and saves its output to `.cache/` so the next script can pick it up. Run them in order.

## Setup

You need Python 3.11+, Docker, a Crawlbase account (Normal and JavaScript tokens), and an OpenAI API key.

```bash
cd code
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r steps/requirements.txt

cd steps
cp .env.example .env    # then fill in your tokens and keys
```

Start Neo4j with the Compose file from the final project (it reads `NEO4J_PASSWORD` from your shell or from `final/.env`):

```bash
cd ../final
docker compose up -d
cd ../steps
```

The scripts load `.env` with `override=True`. Values in `.env` win over environment variables with the same name.

## The steps

| Script | What it does | Writes |
| --- | --- | --- |
| `01_discover_pages.py` | Calls the Crawling API with `scraper=generic-extractor` on each homepage and keeps same-host links that look like about, team, partners, integrations, or careers pages (8 per company at most). | `.cache/discovered.json` |
| `02_fetch_markdown_with_store.py` | Fetches each page as Markdown with `store=true`. Tries `md_readability=true` first, then plain Markdown, then the JS token. Saves the `rid` from `storage_url`. | `.cache/pages.json` |
| `03_extraction_schema.py` | Defines the Pydantic schema and validates one good and one bad sample. No API calls. | nothing |
| `04_extract_with_guard.py` | Sends each page to the LLM with structured outputs and drops any entity whose `source_quote` is not in the page. | `.cache/extracted.json` |
| `05_normalize_entities.py` | Merges near-duplicate names with `rapidfuzz`. | `.cache/normalized.json` |
| `06_load_into_neo4j.py` | Clears the database, loads the graph with `MERGE`, loads it again, and prints both counts. | Neo4j |
| `07_cypher_queries.py` | Runs the shared-integrations, shared-people, and geographic-cluster queries. | nothing |
| `08_graphrag_question.py` | Has the LLM write Cypher, checks that it is read-only, runs it in a read transaction, and answers with citations. | nothing |
| `09_refresh_from_storage.py` | Reads stored pages back from the Storage API by `rid` and re-extracts them without crawling again. | `.cache/refreshed.json` |

```bash
python 01_discover_pages.py
python 02_fetch_markdown_with_store.py
python 03_extraction_schema.py
python 04_extract_with_guard.py
python 05_normalize_entities.py
python 06_load_into_neo4j.py
python 07_cypher_queries.py
python 08_graphrag_question.py
python 09_refresh_from_storage.py
```

## Notes

- Steps 01, 02, and 09 spend Crawlbase credits. Steps 04, 08, and 09 call the OpenAI API.
- Step 06 deletes everything in the Neo4j database before it loads. Do not point it at a database you care about.
- Websites change. Your counts, rids, and extracted entities will differ from the blog output.
- Some sites serve a different homepage variant now and then. If step 01 finds no pages for a company that has them, run it again.
- The seed list in `_common.py` has four companies: Basecamp, HEY, Pipedrive, and Zendesk. This is the smallest set where all three Cypher queries in step 07 return results.

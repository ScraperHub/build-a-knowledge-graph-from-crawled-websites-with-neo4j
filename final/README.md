# kg_pipeline: company knowledge graph from crawled websites

This package crawls company websites with Crawlbase, extracts companies, people, products, integrations, and locations with an LLM, and loads them into Neo4j. You can then query the graph with Cypher or ask questions in plain English (GraphRAG).

Pipeline: crawl, discover, extract, normalize, load, query, ask, refresh.

## Requirements

- Python 3.11+
- Docker (for Neo4j 5 Community)
- A [Crawlbase](https://crawlbase.com) account with a Normal token and a JavaScript token
- An OpenAI API key (the default model is `gpt-4o-mini`)

## Setup

```bash
cd code
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
cd final
pip install -r requirements.txt
pip install -e .

cp .env.example .env      # fill in your tokens, key, and a Neo4j password
docker compose up -d --wait
```

`.env` holds every secret. It is loaded with `override=True`, so its values win over environment variables with the same name. Docker Compose reads `NEO4J_PASSWORD` from the same file. Neo4j Browser runs at http://localhost:7474.

| Variable | Purpose |
| --- | --- |
| `CRAWLBASE_TOKEN` | Normal token for server-rendered pages |
| `CRAWLBASE_JS_TOKEN` | JavaScript token for pages that render in the browser |
| `OPENAI_API_KEY` | Extraction and GraphRAG |
| `OPENAI_MODEL` | Optional, defaults to `gpt-4o-mini` |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | Neo4j connection |
| `KG_CACHE_DIR` | Optional, defaults to `final/.cache` |

## Run

```bash
python -m kg_pipeline run-all --seeds data/seed_small.csv
```

`run-all` runs `crawl`, `extract`, `load`, and `query` in that order. You can also run each stage on its own. Installing the package also adds a `kg` command that does the same thing as `python -m kg_pipeline`.

| Command | What it does |
| --- | --- |
| `crawl --seeds FILE --max-pages 8` | Runs `scraper=generic-extractor` on each homepage, picks up to 8 about, team, partners, integrations, and careers pages, and fetches each one as Markdown with `store=true`. Writes `output/pages.json`. |
| `extract` | Sends each page to the LLM with a Pydantic schema and drops entities whose `source_quote` is not in the page. Writes `output/extractions.json`. |
| `load --seeds FILE [--reset]` | Merges near-duplicate names with `rapidfuzz` and loads the graph with `MERGE`. Re-running it does not create duplicates. `--reset` deletes all graph data first. |
| `query --limit 5` | Shared integrations, people on two companies' sites, geographic clusters, and a `networkx` community example. |
| `ask "QUESTION"` | The LLM writes read-only Cypher, the code checks and runs it in a read transaction, and the answer cites `source_url` and `rid`. |
| `refresh` | Reads every stored page back from the Crawlbase Storage API by `rid` and re-extracts it. No new crawl requests. |

Add `-v` before the command for progress logs, for example `python -m kg_pipeline -v crawl`.

### Seed lists

- `data/seed_small.csv` has four companies: Basecamp, HEY, Pipedrive, and Zendesk. This is the smallest set where all three Cypher queries return results (Basecamp and Pipedrive share integrations, Jason Fried appears on both HEY and Basecamp, and Pipedrive and Zendesk share office countries).
- `data/seed_companies.csv` has 50 SaaS homepages. Each company costs one discovery request plus one to three Markdown requests per page (readability, plain, then JS fallback), and one LLM call per page. With 8 pages per company, plan for several hundred Crawlbase requests on a first run.

Set `use_js` to `true` in the CSV to force the JavaScript token for a company.

### Caching and cost

Every Crawlbase response and every LLM answer is cached in `.cache/` (keyed by URL, or by model, prompt version, and page hash). Re-running a stage reads from the cache and spends no credits. Delete `.cache/` to force fresh calls. `refresh` always calls the LLM again because its goal is to re-run extraction.

Crawlbase calls have a 90 second timeout, up to 3 retries with exponential backoff on 429, 5xx, 520 to 525, and `cb_status: 0`, and at least 1 second between requests.

## Tests

```bash
python -m pytest -m "not integration"   # unit tests, offline, use saved fixtures
python -m pytest -m integration         # live tests
```

The unit tests cover link discovery, schema validation, the hallucination guard, name normalization, the Cypher safety check, and the crawl client with mocked HTTP. They use real Crawlbase responses saved in `tests/fixtures/`. `tests/fixtures/FINDINGS.md` records what those live calls showed.

The integration tests need `.env`, Docker, and network access. They:

- call Crawlbase with both tokens on 3 companies (spends credits),
- round-trip a page through the Storage API,
- **delete all data in the Neo4j database** and load the same extractions twice to check the counts do not change,
- run the three Cypher queries,
- ask one GraphRAG question and check the answer cites a `rid`.

## Layout

```
final/
  kg_pipeline/
    config.py      settings from .env
    cache.py       JSON file cache
    crawl.py       Crawlbase client: generic-extractor, Markdown with store=true, Storage API
    discover.py    pick company pages from generic-extractor links
    schema.py      Pydantic entity and relationship models
    extract.py     LLM extraction and the source_quote guard
    normalize.py   rapidfuzz name merging
    load.py        idempotent MERGE into Neo4j
    queries.py     cross-company Cypher queries
    graphrag.py    question to read-only Cypher to cited answer
    pipeline.py    stage functions
    cli.py         command line
  data/            seed lists
  scripts/         the scripts used to verify Crawlbase behavior
  tests/           unit tests, integration tests, fixtures
  docker-compose.yml
```

## Notes

- Websites change, so your entity counts and rids will differ from the blog.
- Crawlbase picks the exit country automatically. Some sites geo-redirect (for example zendesk.com to zendesk.de). Discovery filters links on the seed homepage's host, so a redirect does not lose pages.
- The `storage_url` Crawlbase returns contains your token. The code keeps only the `rid` and silences `httpx` request logs.

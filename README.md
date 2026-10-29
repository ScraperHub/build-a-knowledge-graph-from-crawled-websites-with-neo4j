# Build a knowledge graph from crawled websites with Neo4j

Code for the blog post "Build a Knowledge Graph from Web Data: Crawled Company Sites to Neo4j". It crawls company websites with [Crawlbase](https://crawlbase.com), extracts entities and relationships with an LLM, loads them into Neo4j, and answers questions over the graph with GraphRAG.

## Folders

- [`steps/`](steps/README.md): one short script per blog section, run in order from `01_discover_pages.py` to `09_refresh_from_storage.py`. Start here if you are following the blog.
- [`final/`](final/README.md): the complete pipeline as a Python package with a CLI (`crawl`, `extract`, `load`, `query`, `ask`, `refresh`, `run-all`), Docker Compose for Neo4j, seed lists, and tests.

## Quick start

```bash
cd code
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
cd final
pip install -r requirements.txt
pip install -e .
cp .env.example .env          # add your Crawlbase tokens, OpenAI key, and a Neo4j password
docker compose up -d --wait
python -m kg_pipeline run-all --seeds data/seed_small.csv
python -m kg_pipeline ask "Which integrations do Basecamp and Pipedrive have in common?"
```

## Requirements

- Python 3.11+
- Docker
- A Crawlbase account (Normal and JavaScript tokens)
- An OpenAI API key

Never commit `.env`. It is listed in `.gitignore`.

## License

See [LICENSE](LICENSE).

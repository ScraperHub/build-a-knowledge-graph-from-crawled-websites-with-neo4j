"""Step 4: extract entities with OpenAI structured outputs, then drop anything the page does not say."""

import importlib
import re
import unicodedata

from openai import OpenAI
from rapidfuzz import fuzz

from _common import OPENAI_MODEL, load, save

schema = importlib.import_module("03_extraction_schema")

PROMPT = """You extract a knowledge graph from one page of the "{company}" website.
Always call that company exactly "{company}".
- Company: {company} and partner companies named on the page.
- Person: people who work at {company}, with title and employer. Skip customers and testimonials.
- Product: named products {company} sells.
- Integration: named third-party tools {company} connects with. Skip phrases like "500+ integrations".
- Location: cities where {company} has an office, with the country.
- Relationships: WORKS_AT (Person->Company), OFFERS (Company->Product),
  INTEGRATES_WITH (Company->Integration), PARTNERS_WITH (Company->Company), LOCATED_IN (Company->Location).
For every item, copy source_quote word for word from the page (5 to 25 words). Only use facts on the page."""


def normalize(text: str) -> str:
    """Lowercase, keep Markdown link text, drop formatting characters and all whitespace."""
    text = unicodedata.normalize("NFKC", text).replace("\u2019", "'").replace("\u2013", "-")
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`#>|\[\]\\\s]", "", text)
    return text.lower()


def guard(result, page: str, company: str):
    """Keep entities whose quote is on the page and relationships whose endpoints survived."""
    page_text = normalize(page)
    found = lambda quote: len(quote) > 2 and normalize(quote).rstrip(".,;:!?") in page_text  # noqa: E731
    dropped = []
    for field in ("companies", "people", "products", "integrations", "locations"):
        items = getattr(result, field)
        dropped += [f"{field}: {e.name}" for e in items if not found(e.source_quote)]
        setattr(result, field, [e for e in items if found(e.source_quote)])
    result.people = [p for p in result.people
                     if not p.employer or fuzz.token_set_ratio(p.employer.lower(), company.lower()) >= 90]
    names = {e.name for f in ("companies", "people", "products", "integrations", "locations")
             for e in getattr(result, f)} | {company}
    kept = [r for r in result.relationships
            if r.source in names and r.target in names and found(r.source_quote)]
    dropped += [f"relationship: {r.source} {r.type} {r.target}" for r in result.relationships if r not in kept]
    result.relationships = kept
    return result, dropped


def add_implied(result, company: str):
    """Staff, products, integrations, and offices on a company's own site belong to that company."""
    linked = {(r.type, r.target if r.type != "WORKS_AT" else r.source) for r in result.relationships}
    for field, rel in (("people", "WORKS_AT"), ("products", "OFFERS"),
                       ("integrations", "INTEGRATES_WITH"), ("locations", "LOCATED_IN")):
        for e in getattr(result, field):
            if (rel, e.name) not in linked:
                source, target = (e.name, company) if rel == "WORKS_AT" else (company, e.name)
                result.relationships.append(schema.Relationship(
                    source=source, type=rel, target=target, source_quote=e.source_quote))
    return result


def extract(client: OpenAI, company: str, markdown: str):
    completion = client.chat.completions.parse(
        model=OPENAI_MODEL, temperature=0, response_format=schema.ExtractionResult,
        messages=[{"role": "system", "content": PROMPT.format(company=company)},
                  {"role": "user", "content": markdown[:40_000]}])
    result, dropped = guard(completion.choices[0].message.parsed, markdown, company)
    return add_implied(result, company), dropped


if __name__ == "__main__":
    client = OpenAI()
    records = []
    for page in load("pages.json"):
        result, dropped = extract(client, page["company"], page["markdown"])
        print(f"{page['url']}: {len(result.relationships)} relationships, {len(dropped)} dropped")
        for item in dropped:
            print("   dropped", item)
        records.append({"company": page["company"], "url": page["url"], "rid": page["rid"],
                        "result": result.model_dump()})
    print("Saved", save("extracted.json", records))

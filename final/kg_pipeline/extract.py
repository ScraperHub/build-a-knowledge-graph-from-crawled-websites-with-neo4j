"""LLM extraction with structured outputs, plus a guard that drops anything the page does not say."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from rapidfuzz import fuzz

from .cache import JsonCache
from .schema import RELATIONSHIP_ENDPOINTS, ExtractionResult, Relationship

PROMPT_VERSION = "v3"
MAX_PAGE_CHARS = 40_000

SYSTEM_PROMPT = """You extract a knowledge graph from one page of a company website.
The page belongs to the company "{company}". Always use exactly "{company}" as that company's name.

Entity types:
- Company: {company} itself, plus partner companies named on the page.
- Person: people who work at {company} (founders, leaders, team members), with their title
  and employer as the page states them. Skip customers, testimonial authors, and investors.
- Product: named products that {company} sells.
- Integration: named third-party tools {company} connects with. Use the tool's own name
  ("Stripe", not "Stripe for {company}"). Skip counts and generic phrases like "500+ integrations".
- Location: cities where {company} has a headquarters or office, with the country.

Relationship types:
- WORKS_AT: Person -> Company
- OFFERS: Company -> Product
- INTEGRATES_WITH: Company -> Integration
- PARTNERS_WITH: Company -> Company
- LOCATED_IN: Company -> Location

Rules:
- Only include facts the page states. Do not use outside knowledge.
- For every entity and relationship, copy source_quote word for word from the page (5 to 25 words). Do not paraphrase or fix typos.
- Relationship source and target must match entity names you listed.
- Return empty lists when the page has nothing for a type."""


def normalize_text(text: str) -> str:
    """Lowercase, flatten Markdown links and formatting, unify quotes and dashes, collapse whitespace."""
    text = html.unescape(unicodedata.normalize("NFKC", text))
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.translate(str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                                         "\u2013": "-", "\u2014": "-", "\u00a0": " "}))
    text = re.sub(r"[*_`#>|\[\]\\]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in_page(quote: str, normalized_page: str) -> bool:
    """True when the quote appears in the page, ignoring whitespace, case, and trailing punctuation."""
    needle = normalize_text(quote).rstrip(" .,;:!?").replace(" ", "")
    return len(needle) >= 3 and needle in normalized_page.replace(" ", "")


@dataclass
class GuardReport:
    result: ExtractionResult
    kept: int = 0
    dropped: list[dict[str, str]] = field(default_factory=list)


def apply_guard(result: ExtractionResult, page_text: str) -> GuardReport:
    """Drop entities whose quote is not in the page, then drop relationships that lost an endpoint."""
    page = normalize_text(page_text)
    report = GuardReport(result=result)
    kept_lists: dict[str, list[Any]] = {}
    for list_name in ("companies", "people", "products", "integrations", "locations"):
        kept_lists[list_name] = []
        for entity in getattr(result, list_name):
            if quote_in_page(entity.source_quote, page):
                kept_lists[list_name].append(entity)
            else:
                report.dropped.append({"kind": list_name, "name": entity.name, "quote": entity.source_quote})

    filtered = ExtractionResult(**kept_lists, relationships=[])
    names = filtered.names_by_label()
    for rel in result.relationships:
        source_label, target_label = RELATIONSHIP_ENDPOINTS[rel.type]
        if rel.source not in names[source_label] or rel.target not in names[target_label]:
            report.dropped.append({"kind": "relationship", "name": f"{rel.source} {rel.type} {rel.target}",
                                   "quote": rel.source_quote, "reason": "missing endpoint"})
        elif not quote_in_page(rel.source_quote, page):
            report.dropped.append({"kind": "relationship", "name": f"{rel.source} {rel.type} {rel.target}",
                                   "quote": rel.source_quote})
        else:
            filtered.relationships.append(rel)

    report.result = filtered
    report.kept = sum(len(getattr(filtered, n)) for n in kept_lists) + len(filtered.relationships)
    return report


IMPLIED = {"integrations": "INTEGRATES_WITH", "products": "OFFERS", "locations": "LOCATED_IN", "people": "WORKS_AT"}


def works_elsewhere(employer: str | None, company: str) -> bool:
    """True when the page names a different employer, such as a customer in a testimonial."""
    return bool(employer) and fuzz.token_set_ratio(employer.lower(), company.lower()) < 90


def clean_for_company(result: ExtractionResult, company: str) -> ExtractionResult:
    """Drop people who work elsewhere and strip "for <company>" from integration names."""
    outsiders = {p.name for p in result.people if works_elsewhere(p.employer, company)}
    result.people = [p for p in result.people if p.name not in outsiders]
    result.relationships = [r for r in result.relationships if r.source not in outsiders]
    suffix = re.compile(rf"\s+(for|\+)\s+{re.escape(company)}$", re.IGNORECASE)
    renames = {i.name: suffix.sub("", i.name) for i in result.integrations}
    for integration in result.integrations:
        integration.name = renames[integration.name]
    for rel in result.relationships:
        if rel.type == "INTEGRATES_WITH":
            rel.target = renames.get(rel.target, rel.target)
    return result


def add_implied_relationships(result: ExtractionResult, company: str) -> ExtractionResult:
    """Integrations, products, offices, and staff listed on a company's own site belong to that company."""
    linked = {(r.type, r.source if r.type == "WORKS_AT" else r.target) for r in result.relationships}
    for list_name, rel_type in IMPLIED.items():
        for entity in getattr(result, list_name):
            if (rel_type, entity.name) in linked:
                continue
            source, target = (entity.name, company) if rel_type == "WORKS_AT" else (company, entity.name)
            result.relationships.append(
                Relationship(source=source, type=rel_type, target=target, source_quote=entity.source_quote)
            )
    return result


def call_llm(client: Any, model: str, company: str, page_text: str) -> ExtractionResult:
    """Ask the model for an ExtractionResult using OpenAI structured outputs."""
    completion = client.chat.completions.parse(
        model=model,
        temperature=0,
        response_format=ExtractionResult,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(company=company)},
            {"role": "user", "content": page_text[:MAX_PAGE_CHARS]},
        ],
    )
    parsed = completion.choices[0].message.parsed
    return parsed or ExtractionResult(companies=[], people=[], products=[], integrations=[], locations=[],
                                      relationships=[])


def extract_page(
    client: Any,
    model: str,
    cache: JsonCache,
    company: str,
    url: str,
    rid: str,
    page_text: str,
) -> dict[str, Any]:
    """Extract, guard, and return a provenance-tagged record. LLM output is cached by page content."""
    digest = hashlib.sha256(page_text.encode("utf-8")).hexdigest()
    key = f"{model}|{PROMPT_VERSION}|{company}|{digest}"
    cached = cache.get("llm", key)
    if cached is None:
        raw = call_llm(client, model, company, page_text)
        cached = {"raw": raw.model_dump(), "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        cache.set("llm", key, cached)

    report = apply_guard(ExtractionResult.model_validate(cached["raw"]), page_text)
    clean_for_company(report.result, company)
    add_implied_relationships(report.result, company)
    return {
        "company": company,
        "url": url,
        "rid": rid,
        "extracted_at": cached["extracted_at"],
        "result": report.result.model_dump(),
        "kept": report.kept,
        "dropped": report.dropped,
    }

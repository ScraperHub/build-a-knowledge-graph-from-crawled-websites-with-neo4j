"""Canonical entity names: strip legal suffixes and domains, then merge near duplicates with rapidfuzz."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from copy import deepcopy
from typing import Any, Iterable

from rapidfuzz import fuzz

from .schema import RELATIONSHIP_ENDPOINTS

LEGAL_SUFFIXES = {"inc", "llc", "ltd", "limited", "gmbh", "corp", "corporation", "co", "plc", "sa", "ag", "bv", "oy"}
DOMAIN_SUFFIX = re.compile(r"\.(com|io|ai|co|app|so|net|org|dev)$")
MATCH_THRESHOLD = 90
COUNTRY_ALIASES = {"usa": "United States", "us": "United States", "u.s.": "United States",
                   "united states of america": "United States", "uk": "United Kingdom",
                   "great britain": "United Kingdom", "czechia": "Czech Republic"}
ENTITY_LISTS = {"companies": "Company", "people": "Person", "products": "Product",
                "integrations": "Integration", "locations": "Location"}


def canonical_key(name: str) -> str:
    """Comparison key: lowercase, no domain suffix, no punctuation, no legal suffix."""
    text = unicodedata.normalize("NFKC", name).lower().strip()
    text = DOMAIN_SUFFIX.sub("", text)
    text = re.sub(r"[^\w\s&+]", " ", text)
    tokens = [t for t in text.split() if t not in LEGAL_SUFFIXES]
    return " ".join(tokens)


def build_name_map(names: Iterable[str], preferred: Iterable[str] = (), threshold: int = MATCH_THRESHOLD) -> dict[str, str]:
    """Map every name to a representative. Preferred names win, then the most frequent, then the shortest."""
    names = list(names)
    counts = Counter(names)
    preferred = list(dict.fromkeys(preferred))
    ordered = preferred + sorted(set(names) - set(preferred), key=lambda n: (-counts[n], len(n), n))
    clusters: list[tuple[str, str]] = []
    mapping: dict[str, str] = {}
    for name in ordered:
        key = canonical_key(name)
        for cluster_key, representative in clusters:
            if key and fuzz.ratio(key, cluster_key) >= threshold:
                mapping[name] = representative
                break
        else:
            clusters.append((key, name))
            mapping[name] = name
    return mapping


def normalize_records(records: list[dict[str, Any]], seed_companies: Iterable[str] = ()) -> tuple[list[dict[str, Any]], list[tuple[str, str, str]]]:
    """Rewrite names across all page records so near duplicates share one name. Returns records and merges."""
    names: dict[str, list[str]] = {label: [] for label in ENTITY_LISTS.values()}
    for record in records:
        for list_name, label in ENTITY_LISTS.items():
            names[label].extend(e["name"] for e in record["result"][list_name])

    maps = {label: build_name_map(values, seed_companies if label == "Company" else ())
            for label, values in names.items()}
    merges = sorted({(label, old, new) for label, m in maps.items() for old, new in m.items() if old != new})

    normalized: list[dict[str, Any]] = []
    for record in records:
        record = deepcopy(record)
        result = record["result"]
        for list_name, label in ENTITY_LISTS.items():
            unique: dict[str, dict[str, Any]] = {}
            for entity in result[list_name]:
                entity["name"] = maps[label].get(entity["name"], entity["name"])
                if entity.get("country"):
                    entity["country"] = COUNTRY_ALIASES.get(entity["country"].strip().lower(), entity["country"].strip())
                unique.setdefault(entity["name"], entity)
            result[list_name] = list(unique.values())
        seen: set[tuple[str, str, str]] = set()
        relationships = []
        for rel in result["relationships"]:
            source_label, target_label = RELATIONSHIP_ENDPOINTS[rel["type"]]
            rel["source"] = maps[source_label].get(rel["source"], rel["source"])
            rel["target"] = maps[target_label].get(rel["target"], rel["target"])
            triple = (rel["source"], rel["type"], rel["target"])
            if rel["source"] == rel["target"] and source_label == target_label:
                continue
            if triple not in seen:
                seen.add(triple)
                relationships.append(rel)
        result["relationships"] = relationships
        normalized.append(record)
    return normalized, merges

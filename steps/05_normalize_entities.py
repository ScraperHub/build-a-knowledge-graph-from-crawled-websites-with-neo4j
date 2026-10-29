"""Step 5: merge near-duplicate names across pages with rapidfuzz before loading."""

import re

from rapidfuzz import fuzz

from _common import SEEDS, load, save

SUFFIXES = {"inc", "llc", "ltd", "gmbh", "corp", "co", "plc"}
LISTS = {"companies": "Company", "people": "Person", "products": "Product",
         "integrations": "Integration", "locations": "Location"}
ENDPOINTS = {"WORKS_AT": ("Person", "Company"), "OFFERS": ("Company", "Product"),
             "INTEGRATES_WITH": ("Company", "Integration"), "PARTNERS_WITH": ("Company", "Company"),
             "LOCATED_IN": ("Company", "Location")}


def key(name: str) -> str:
    """"Stripe, Inc." and "stripe.com" both become "stripe"."""
    name = re.sub(r"\.(com|io|ai|co|app)$", "", name.lower().strip())
    return " ".join(t for t in re.sub(r"[^\w\s&+]", " ", name).split() if t not in SUFFIXES)


def name_map(names: list[str], preferred: list[str] = ()) -> dict[str, str]:
    """Map each name to the first name it scores 90 or more against."""
    ordered = list(dict.fromkeys(list(preferred) + sorted(names, key=lambda n: (-names.count(n), len(n)))))
    keepers, mapping = [], {}
    for name in ordered:
        match = next((k for k in keepers if fuzz.ratio(key(name), key(k)) >= 90), None)
        mapping[name] = match or name
        if not match:
            keepers.append(name)
    return mapping


if __name__ == "__main__":
    for a, b in (("Stripe", "Stripe, Inc."), ("Salesforce", "Salesforce.com"), ("Notion", "Motion")):
        print(f"{a!r} vs {b!r}: score {fuzz.ratio(key(a), key(b)):.0f}, merged={name_map([a, b])[b] == a}")

    records = load("extracted.json")
    maps = {}
    for field, label in LISTS.items():
        names = [e["name"] for r in records for e in r["result"][field]]
        maps[label] = name_map(names, [s["name"] for s in SEEDS] if label == "Company" else ())
        for old, new in maps[label].items():
            if old != new:
                print(f"merge {label}: {old!r} -> {new!r}")

    for record in records:
        result = record["result"]
        for field, label in LISTS.items():
            for entity in result[field]:
                entity["name"] = maps[label].get(entity["name"], entity["name"])
        for rel in result["relationships"]:
            source_label, target_label = ENDPOINTS[rel["type"]]
            rel["source"] = maps[source_label].get(rel["source"], rel["source"])
            rel["target"] = maps[target_label].get(rel["target"], rel["target"])
    print("Saved", save("normalized.json", records))

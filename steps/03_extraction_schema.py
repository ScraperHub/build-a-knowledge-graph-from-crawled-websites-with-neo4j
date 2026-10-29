"""Step 3: the entity and relationship schema the LLM must fill. Every item carries a source_quote."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    source_quote: str = Field(min_length=3, description="Exact words copied from the page.")


class Company(Evidence): pass
class Product(Evidence): pass
class Integration(Evidence): pass


class Person(Evidence):
    title: str | None
    employer: str | None


class Location(Evidence):
    country: str | None


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    type: Literal["WORKS_AT", "OFFERS", "INTEGRATES_WITH", "PARTNERS_WITH", "LOCATED_IN"]
    target: str
    source_quote: str = Field(min_length=3)


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    companies: list[Company]
    people: list[Person]
    products: list[Product]
    integrations: list[Integration]
    locations: list[Location]
    relationships: list[Relationship]


if __name__ == "__main__":
    good = {"companies": [{"name": "Pipedrive", "source_quote": "Pipedrive is a sales CRM"}],
            "people": [{"name": "Paulo Cunha", "title": "CEO", "employer": "Pipedrive",
                        "source_quote": "Paulo Cunha, CEO"}],
            "products": [], "integrations": [], "locations": [],
            "relationships": [{"source": "Paulo Cunha", "type": "WORKS_AT", "target": "Pipedrive",
                               "source_quote": "Paulo Cunha, CEO"}]}
    print("Good output parses:", ExtractionResult.model_validate(good).people[0].name)

    bad = json.loads(json.dumps(good))
    del bad["people"][0]["source_quote"]
    bad["relationships"][0]["type"] = "ACQUIRED"
    try:
        ExtractionResult.model_validate(bad)
    except ValidationError as error:
        print(f"Bad output rejected with {error.error_count()} errors:")
        for item in error.errors():
            print("  ", ".".join(map(str, item["loc"])), "->", item["msg"])

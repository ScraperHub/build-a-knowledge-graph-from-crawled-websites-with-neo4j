"""Pydantic models the LLM must fill. Every entity and relationship carries a source_quote."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntityLabel = Literal["Company", "Person", "Product", "Integration", "Location"]
RelationshipType = Literal["WORKS_AT", "OFFERS", "INTEGRATES_WITH", "PARTNERS_WITH", "LOCATED_IN"]

RELATIONSHIP_ENDPOINTS: dict[str, tuple[str, str]] = {
    "WORKS_AT": ("Person", "Company"),
    "OFFERS": ("Company", "Product"),
    "INTEGRATES_WITH": ("Company", "Integration"),
    "PARTNERS_WITH": ("Company", "Company"),
    "LOCATED_IN": ("Company", "Location"),
}


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Name exactly as written on the page.")
    source_quote: str = Field(min_length=3, description="A short verbatim quote from the page that proves this entity.")


class Company(Evidence):
    pass


class Person(Evidence):
    title: str | None = Field(description="Job title if the page states one, otherwise null.")
    employer: str | None = Field(description="Company the page says this person works at, otherwise null.")


class Product(Evidence):
    pass


class Integration(Evidence):
    pass


class Location(Evidence):
    country: str | None = Field(description="Country if the page states or clearly implies it, otherwise null.")


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, description="Name of the source entity.")
    type: RelationshipType
    target: str = Field(min_length=1, description="Name of the target entity.")
    source_quote: str = Field(min_length=3, description="A short verbatim quote from the page that proves this relationship.")


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    companies: list[Company]
    people: list[Person]
    products: list[Product]
    integrations: list[Integration]
    locations: list[Location]
    relationships: list[Relationship]

    def names_by_label(self) -> dict[str, set[str]]:
        return {
            "Company": {e.name for e in self.companies},
            "Person": {e.name for e in self.people},
            "Product": {e.name for e in self.products},
            "Integration": {e.name for e in self.integrations},
            "Location": {e.name for e in self.locations},
        }

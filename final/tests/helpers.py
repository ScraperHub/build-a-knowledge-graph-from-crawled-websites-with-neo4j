from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def generic_extractor_page(name: str) -> dict[str, Any]:
    """The parsed page inside a saved generic-extractor envelope."""
    envelope = json.loads(load_fixture(f"generic_extractor_{name}.json")["body"])
    return {"url": envelope["url"], **envelope["body"]}

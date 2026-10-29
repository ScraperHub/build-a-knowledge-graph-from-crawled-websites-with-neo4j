from __future__ import annotations

from typing import Any

import pytest

from helpers import generic_extractor_page, load_fixture


@pytest.fixture
def close_homepage() -> dict[str, Any]:
    return generic_extractor_page("close_com")


@pytest.fixture
def close_about_markdown() -> str:
    return load_fixture("md_plain_close_com_about.json")["body"]

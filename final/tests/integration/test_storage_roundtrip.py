"""Store a page with store=true, then read it back from the Storage API by rid."""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.integration


def test_storage_round_trip_with_a_real_rid(live_crawler):
    fetched = live_crawler.fetch_markdown("https://basecamp.com/about")
    assert fetched.rid

    stored = None
    for _ in range(5):
        try:
            stored = live_crawler.get_stored(fetched.rid)
            break
        except Exception:
            time.sleep(3)
    assert stored is not None
    assert stored["rid"] == fetched.rid
    assert stored["url"].rstrip("/") == "https://basecamp.com/about"
    assert stored["body"].strip() == fetched.markdown.strip()

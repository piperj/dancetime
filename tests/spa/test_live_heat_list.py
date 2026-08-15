"""
Live trust check: the published SPA's rendered heat list for Johan Piper
must match a *fresh* pull of his own record straight from NDCA -- every
heat he's in, and no others.

Deliberately targeted, not a full competition scrape: this fetches only
Johan's own heatlist record (2 lightweight API calls -- a name->ID roster
lookup, then his one competitor record), not every competitor in the
competition. It walks data/index.json (already sorted most-recent-first)
for the most recent competition he's registered in, so it stays runnable
without needing him to be in whatever comp happens to be "active" today.

Renders against the already-published site (root index.html + data/), so
this test never scrapes a whole competition or rebuilds the pipeline --
it only makes live calls to fetch the ground truth to compare against.
"""
import json

import pytest

from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

REQUESTS_NAME = ["Johan", "Piper"]
SEARCH_NAME = "Johan Piper"


def _find_comp_and_id(client, index_json):
    """Most recent tracked competition Johan is registered in, plus his
    NDCA competitor ID there (from the lightweight name->ID roster call --
    not a full-field fetch)."""
    for comp in index_json["competitions"]:
        if SEARCH_NAME not in comp.get("competitors", []):
            continue
        cyi = comp["cyi"]
        roster = client.fetch_competitor_list(cyi, "heatlists")
        match = next((r for r in roster if r.get("Name") == REQUESTS_NAME), None)
        if match:
            return cyi, match["ID"]
    pytest.skip(f"{SEARCH_NAME!r} not found (via live roster lookup) in any tracked competition")


def _ground_truth_heats(client, cyi, competitor_id):
    record = client.fetch_competitor_heatlists(cyi, str(competitor_id), "")
    assert record is not None, f"live heatlists fetch returned nothing for cyi={cyi} id={competitor_id}"
    numbers = set()
    for entry in record.get("Entries", []):
        for ev in entry.get("Events", []):
            if ev.get("Heat"):
                numbers.add(str(ev["Heat"]))
    return numbers


class TestLiveHeatListMatchesFreshScrape:
    def test_rendered_heats_match_live_ndca_record(self, page, spa_server):
        from scrape.client import NDCAClient
        from .conftest import REPO_ROOT

        client = NDCAClient()
        index_json = json.loads((REPO_ROOT / "data" / "index.json").read_text())
        cyi, competitor_id = _find_comp_and_id(client, index_json)
        expected = _ground_truth_heats(client, cyi, competitor_id)
        assert expected, f"{SEARCH_NAME!r} (cyi={cyi}) has no heats in the live record -- nothing to compare"

        wait_for_spa(page, spa_server)
        page.evaluate(f"selectComp(compList.findIndex(c => c.cyi === {cyi}))")
        page.wait_for_function(
            """() => {
                const s = document.getElementById('status');
                return s.classList.contains('hidden') || !s.textContent.includes('Loading');
            }""",
            timeout=15_000,
        )
        page.evaluate(f"setHeatsSearch({SEARCH_NAME!r})")
        page.wait_for_function(
            "() => document.querySelectorAll('#scheduleContent .heat-box').length > 0",
            timeout=10_000,
        )
        # Scoped to the card header's own <strong> (the heat number) -- a bare
        # '.heat-box strong' also matches each dance name inside the (hidden
        # until expanded) couples list, e.g. "G-B1 Cl. Pre-Bronze Int'l Jive:".
        actual = set(page.evaluate(
            "() => Array.from(document.querySelectorAll('#scheduleContent .heat-box > div.text-base > strong'))"
            ".map(e => e.textContent.trim())"
        ))

        missing = expected - actual   # heats he has but the SPA didn't show
        extra = actual - expected     # heats the SPA showed that aren't his
        assert not missing, f"cyi={cyi}: SPA is missing heats from the live record: {sorted(missing, key=int)}"
        assert not extra, f"cyi={cyi}: SPA shows heats not in the live record: {sorted(extra, key=int)}"

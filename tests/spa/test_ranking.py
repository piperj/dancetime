"""
Suite B — locks Ranking-tab ELO chart behaviour at the known-good baseline (dd48d2a).

Run AFTER restoring static/index.html to dd48d2a.  Both suite A and suite B
must stay green through all subsequent UI-improvement commits.

Test data uses competitors known to appear across multiple competitions so
cross-comp series assertions are meaningful.
"""
import pytest
from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# Known multi-competition competitors (from elo_history.json, 4-5 comps each)
COMPETITOR_A = "Kristina Kuvshynov"
COMPETITOR_B = "Sarah McClammy"
COMPETITOR_C = "Yuriy Kuvshynov"
# A real couple pair
COUPLE_A = "Kristina Kuvshynov"
COUPLE_B = "Yuriy Kuvshynov"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _click_tab(page, tab):
    page.click(f"nav button[data-tab='{tab}']")
    page.wait_for_timeout(400)


def _add_competitor(page, name):
    inp = page.locator("#elo-search-a")
    inp.fill(name)
    inp.dispatch_event("input")
    page.wait_for_timeout(300)
    # "Add contestant" button — onclick="eloAddContestant()"
    page.locator("button[onclick*='eloAddContestant'], button:text('Add contestant')").first.click()
    page.wait_for_timeout(600)


def _add_couple(page, name_a, name_b):
    page.locator("#elo-search-a").fill(name_a)
    page.locator("#elo-search-a").dispatch_event("input")
    page.wait_for_timeout(200)
    page.locator("#elo-search-b").fill(name_b)
    page.locator("#elo-search-b").dispatch_event("input")
    page.wait_for_timeout(200)
    # "Add couple" button — onclick="eloAddCouple()"
    page.locator("button[onclick*='eloAddCouple'], button:text('Add couple')").first.click()
    page.wait_for_timeout(600)


def _dataset_count(page):
    return page.evaluate("() => window.__eloChart?.data?.datasets?.length ?? 0")


def _datasets(page):
    return page.evaluate("""() => (window.__eloChart?.data?.datasets ?? []).map(d => ({
        label:      d.label,
        points:     d.data?.length ?? 0,
        borderDash: d.borderDash ?? [],
    }))""")


def _remove_chip(page, label):
    """Click the × on the series chip matching label."""
    chips = page.locator("#elo-series-list span")
    for i in range(chips.count()):
        chip = chips.nth(i)
        if label.split()[0] in chip.inner_text():
            chip.locator("button, .chip-x, [aria-label='Remove']").first.click()
            page.wait_for_timeout(400)
            return
    # Fallback: click first × button in the chip list
    page.locator("#elo-series-list").locator("button").first.click()
    page.wait_for_timeout(400)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRankingTab:
    def test_single_competitor_series(self, page, spa_server):
        """Adding one competitor renders a single solid step-line dataset with >1 points."""
        wait_for_spa(page, spa_server)
        _click_tab(page, "elo")
        _add_competitor(page, COMPETITOR_A)

        datasets = _datasets(page)
        assert len(datasets) == 1, f"expected 1 dataset, got {len(datasets)}: {datasets}"
        d = datasets[0]
        assert d["points"] > 1, f"expected >1 data points, got {d['points']}"
        assert d["borderDash"] == [], f"individual series should be solid (no dash), got {d['borderDash']}"

    def test_couple_series_is_dashed(self, page, spa_server):
        """Adding a couple renders a dotted/dashed curve dataset."""
        wait_for_spa(page, spa_server)
        _click_tab(page, "elo")
        _add_couple(page, COUPLE_A, COUPLE_B)

        datasets = _datasets(page)
        assert len(datasets) == 1, f"expected 1 couple dataset, got {len(datasets)}"
        d = datasets[0]
        assert d["points"] > 1, f"couple series needs >1 points"
        assert d["borderDash"] != [], f"couple series should be dashed, got borderDash={d['borderDash']}"

    def test_multiple_series(self, page, spa_server):
        """Adding 2 competitors + 1 couple gives 3 datasets with distinct labels."""
        wait_for_spa(page, spa_server)
        _click_tab(page, "elo")
        _add_competitor(page, COMPETITOR_A)
        _add_competitor(page, COMPETITOR_B)
        # Use a couple that doesn't overlap with already-added solo series
        _add_couple(page, "Sarah McClammy", "Yuriy Kuvshynov")

        datasets = _datasets(page)
        assert len(datasets) == 3, f"expected 3 datasets, got {len(datasets)}: {[d['label'] for d in datasets]}"
        labels = [d["label"] for d in datasets]
        assert len(set(labels)) == 3, f"labels should be distinct: {labels}"

    def test_series_removal(self, page, spa_server):
        """Clicking × on a chip removes that dataset."""
        wait_for_spa(page, spa_server)
        _click_tab(page, "elo")
        _add_competitor(page, COMPETITOR_A)
        _add_competitor(page, COMPETITOR_B)
        assert _dataset_count(page) == 2, "expected 2 datasets before removal"

        # Click the × button on the first chip (.elo-series-chip button)
        page.locator("#elo-series-list .elo-series-chip button").first.click()
        page.wait_for_timeout(500)
        assert _dataset_count(page) == 1, "expected 1 dataset after removing one chip"

    def test_cross_competition_spans(self, page, spa_server):
        """A multi-comp competitor's series spans data from ≥2 competitions."""
        wait_for_spa(page, spa_server)
        _click_tab(page, "elo")
        _add_competitor(page, COMPETITOR_A)  # 5 competitions in history

        datasets = _datasets(page)
        assert datasets, "no datasets rendered"
        # The chart x-axis uses dance # (cumulative). Each comp has many heats,
        # so a 5-comp competitor should have substantially more than 20 points.
        assert datasets[0]["points"] > 20, (
            f"expected many points across multiple comps, got {datasets[0]['points']}"
        )

    def test_comp_header_hidden_on_ranking_tab(self, page, spa_server):
        """The per-competition dropdown (comp-header) is hidden on the Ranking tab."""
        wait_for_spa(page, spa_server)
        _click_tab(page, "elo")
        is_hidden = page.evaluate(
            "() => document.getElementById('comp-header').classList.contains('hidden')"
        )
        assert is_hidden, "comp-header should be hidden on the Ranking/ELO tab"

    def test_canvas_visible_after_add(self, page, spa_server):
        """The chart canvas is visible after adding a competitor."""
        wait_for_spa(page, spa_server)
        _click_tab(page, "elo")
        _add_competitor(page, COMPETITOR_A)

        wrap = page.locator("#elo-chart-wrap")
        assert not wrap.evaluate("el => el.classList.contains('hidden')"), (
            "elo-chart-wrap should not be hidden after adding a series"
        )
        canvas = page.locator("#elo-canvas")
        assert canvas.is_visible(), "elo-canvas should be visible"

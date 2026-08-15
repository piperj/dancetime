"""
Contested-pill scoping by search context (HeatCard.context / HeatCard.isRelevant).

A physical heat can host multiple simultaneous events, each independently
contested. Before this, a Contested pill was shown for *every* contested
event on the heat regardless of who you searched for -- so searching a
single competitor could surface a pill for a completely unrelated couple's
event sharing the same floor. Real-data regression found this session:

data/heats/422.json (International Grand Ball 2026) heat "583" has exactly
this shape -- two simultaneous events, each contested:
  event 2261: Sara Fan & Reimar Leike (studio "Leike/Fan", bib 744)
              vs Uditi Guha & Catherine Kuntoro (studio "DNA Dance - Kuntoro/Guha", bib 736)
  event 2262: Hyun Joo Kim & Rui Li (studio "Li/Kim", bib 745)
              vs Helen Piper & Johan Piper (studio "Arete Dance Center", bib 759)

Searching for Johan Piper (or his bib 759, or his studio "Arete Dance
Center") must show only the 2262 pill -- never the unrelated 2261 one.
The All-Heats view (no search scope) shows both.
"""
import pytest
from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CYI = 422
HEAT_NUMBER = "583"


def _select_comp(page, cyi):
    page.evaluate(f"selectComp(compList.findIndex(c => c.cyi === {cyi}))")
    page.wait_for_function(
        """() => {
            const s = document.getElementById('status');
            return s.classList.contains('hidden') || !s.textContent.includes('Loading');
        }""",
        timeout=15_000,
    )


def _setup(page, spa_server):
    wait_for_spa(page, spa_server)
    _select_comp(page, CYI)


def _heat_box(page):
    """The .heat-box for HEAT_NUMBER -- exact match on the <strong> heat number,
    since a substring match could hit e.g. heat '1583' too."""
    return page.locator(
        f"xpath=//div[contains(@class,'heat-box')]"
        f"[.//strong[normalize-space(text())='{HEAT_NUMBER}']]"
    )


def _pill_anchor_names(page):
    """Anchor names of every Contested pill currently shown on the heat 583
    card -- distinguishes the two events without depending on label text
    (both can render the same medal, e.g. both "🥈 Contested")."""
    return page.locator(
        f"xpath=//div[contains(@class,'heat-box')]"
        f"[.//strong[normalize-space(text())='{HEAT_NUMBER}']]"
        f"//span[@data-role='contested-pill']"
    ).evaluate_all("els => els.map(e => e.dataset.anchorName)")


class TestContestedPillScoping:
    def test_all_heats_view_shows_both_pills(self, page, spa_server):
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('')")
        assert _pill_anchor_names(page) == ["Uditi Guha", "Hyun Joo Kim"], "All-Heats view has no search scope, both events' pills should show"

    def test_competitor_search_shows_only_own_event(self, page, spa_server):
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('Johan Piper')")
        assert _pill_anchor_names(page) == ["Hyun Joo Kim"], "should show only event 2262's pill (Johan's own)"

    def test_bib_search_shows_only_own_event(self, page, spa_server):
        """Bib 759 is Helen & Johan Piper's couple -- same event 2262 as above."""
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('759')")
        assert _pill_anchor_names(page) == ["Hyun Joo Kim"], "should show only event 2262's pill (bib 759's own)"

    def test_studio_search_shows_only_own_event(self, page, spa_server):
        """Arete Dance Center is Helen & Johan Piper's studio -- neither of
        event 2261's studios (Leike/Fan, DNA Dance - Kuntoro/Guha)."""
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('Arete Dance Center')")
        assert _pill_anchor_names(page) == ["Hyun Joo Kim"], "should show only event 2262's pill (Arete's own)"

    def test_unrelated_competitor_search_shows_other_event(self, page, spa_server):
        """Sanity check on the fixture and the filter direction: searching a
        competitor in event 2261 shows only *that* event's pill, not 2262's."""
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('Sara Fan')")
        assert _pill_anchor_names(page) == ["Uditi Guha"], "should show only event 2261's pill (Sara's own)"

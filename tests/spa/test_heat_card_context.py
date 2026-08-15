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
Center") must show only the 2262 pill -- never the unrelated 2261 one, and
its anchor/label reflect *that couple's own* placement (Helen Piper's
entry), not the event's overall winner -- searching Sara Fan symmetrically
shows only 2261's pill, anchored on her own entry. The All-Heats view (no
search scope) shows both, each anchored on its event's overall winner.
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


def _heat_box(page, heat_number=HEAT_NUMBER):
    """The .heat-box for a given heat number -- exact match on the <strong>
    heat number, since a substring match could hit e.g. heat '1583' too."""
    return page.locator(
        f"xpath=//div[contains(@class,'heat-box')]"
        f"[.//strong[normalize-space(text())='{heat_number}']]"
    )


def _pill_anchor_names(page, heat_number=HEAT_NUMBER):
    """Anchor names of every Contested pill currently shown on the given
    heat's card -- distinguishes events without depending on label text
    (two pills can render the same medal, e.g. both "🥈 Contested")."""
    return page.locator(
        f"xpath=//div[contains(@class,'heat-box')]"
        f"[.//strong[normalize-space(text())='{heat_number}']]"
        f"//span[@data-role='contested-pill']"
    ).evaluate_all("els => els.map(e => e.dataset.anchorName)")


def _pills(page, heat_number=HEAT_NUMBER):
    """{label, anchor} for every Contested pill on the given heat's card."""
    return page.locator(
        f"xpath=//div[contains(@class,'heat-box')]"
        f"[.//strong[normalize-space(text())='{heat_number}']]"
        f"//span[@data-role='contested-pill']"
    ).evaluate_all("els => els.map(e => ({label: e.textContent.trim(), anchor: e.dataset.anchorName}))")


class TestContestedPillScoping:
    def test_all_heats_view_shows_both_pills(self, page, spa_server):
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('')")
        assert _pill_anchor_names(page) == ["Uditi Guha", "Hyun Joo Kim"], "All-Heats view has no search scope, both events' pills should show"

    def test_competitor_search_shows_only_own_event(self, page, spa_server):
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('Johan Piper')")
        assert _pill_anchor_names(page) == ["Helen Piper"], (
            "should show only event 2262's pill, anchored on Johan's own couple (not the event's overall winner)"
        )

    def test_bib_search_shows_only_own_event(self, page, spa_server):
        """Bib 759 is Helen & Johan Piper's couple -- same event 2262 as above."""
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('759')")
        assert _pill_anchor_names(page) == ["Helen Piper"], "should show only event 2262's pill (bib 759's own)"

    def test_studio_search_shows_only_own_event(self, page, spa_server):
        """Arete Dance Center is Helen & Johan Piper's studio -- neither of
        event 2261's studios (Leike/Fan, DNA Dance - Kuntoro/Guha)."""
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('Arete Dance Center')")
        assert _pill_anchor_names(page) == ["Helen Piper"], "should show only event 2262's pill (Arete's own)"

    def test_unrelated_competitor_search_shows_other_event(self, page, spa_server):
        """Sanity check on the fixture and the filter direction: searching a
        competitor in event 2261 shows only *that* event's pill, anchored on
        her own couple, not 2262's."""
        _setup(page, spa_server)
        page.evaluate("setHeatsSearch('Sara Fan')")
        assert _pill_anchor_names(page) == ["Sara Fan"], "should show only event 2261's pill (Sara's own)"


# ---------------------------------------------------------------------------
# Multi-round collapse: one pill per contested *event*, not per round
# ---------------------------------------------------------------------------
# data/heats/373.json (City Lights Open) heat "628" is a two-round heat
# (Semi-Final then Final) of the same event (1759). 11 couples danced the
# contested Semi-Final; 6 were recalled to a contested Final. Before this
# fix, each round produced its own independent contested group, so a couple
# recalled to the Final got *two* pills for what's really one ongoing
# contested field -- and JudgesScores.fetchJudgesData returns the whole
# heat's rounds together regardless of which pill anchors the fetch, so the
# second pill was pure redundant noise, not a second, different result.
ROUND_CYI = 373
ROUND_HEAT_NUMBER = "628"


class TestMultiRoundCollapse:
    def _setup(self, page, spa_server):
        wait_for_spa(page, spa_server)
        _select_comp(page, ROUND_CYI)

    def test_recalled_couple_gets_one_pill_with_own_final_placement(self, page, spa_server):
        """Jasher Kuehn & Brooke Johnson danced both rounds and placed 3rd in
        the Final -- exactly one pill, showing *their* Final result, not the
        Semi-Final's or the field's eventual winner's."""
        self._setup(page, spa_server)
        page.evaluate("setHeatsSearch('Jasher Kuehn')")
        pills = _pills(page, ROUND_HEAT_NUMBER)
        assert pills == [{"label": "🥉 Contested", "anchor": "Jasher Kuehn"}]

    def test_eliminated_couple_falls_back_to_semi_final_placement(self, page, spa_server):
        """Oscar Adrian Rodriguez danced only the Semi-Final (not recalled) --
        one pill, showing his Semi-Final placement since no Final result
        exists for him ('Final trumps Semi-Final, if available')."""
        self._setup(page, spa_server)
        page.evaluate("setHeatsSearch('Oscar Adrian Rodriguez')")
        pills = _pills(page, ROUND_HEAT_NUMBER)
        assert pills == [{"label": "7th Contested", "anchor": "Oscar Adrian Rodriguez"}]

    def test_all_heats_view_also_collapses_to_one_pill(self, page, spa_server):
        """With no search scope, every couple in both rounds is 'relevant',
        but it's still one contested event -- one pill, using the Final's
        overall winner since the Final has been scored."""
        self._setup(page, spa_server)
        page.evaluate("setHeatsSearch('')")
        pills = _pills(page, ROUND_HEAT_NUMBER)
        assert pills == [{"label": "🥇 Contested", "anchor": "Bumchin Tegshjargal"}]

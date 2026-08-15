"""
Judges-scores panel tests — clicking a Contested pill lazy-loads live judges'
marks from NDCA into a dropdown card. The live network call is mocked via
page.route() so this suite has no external dependency and can't be flaky on
NDCA's availability; the mocked shape mirrors a real captured response
(cyi 373 heat 628, Oscar Adrian Rodriguez — a Prelims semi-final the couple
was NOT recalled from, followed by a Skated final).

heats/373.json (committed fixture data) already has heat 628 with Oscar
Adrian Rodriguez as a genuinely Contested entry, so the pill exists without
any extra setup — only the live-fetch call itself is mocked.
"""
import pytest
from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CYI = 373
COMPETITOR_ID = "A155"
COMPETITOR_NAME = "Oscar Adrian Rodriguez"
HEAT_NUMBER = "628"


# ---------------------------------------------------------------------------
# Mock NDCA responses
# ---------------------------------------------------------------------------

def _judges(letters_names):
    return [{"Judge_Letter": letter, "Name": name.split(" ", 1)} for letter, name in letters_names]


def _mock_event():
    """One event with two rounds: a Prelims semi-final (Oscar not recalled),
    then a Skated final danced only by the couples who were recalled."""
    judges = _judges([("01", "Tomas Atkocevicius"), ("02", "Agita Baranovska")])
    oscar_couple = {
        "ID": "C51", "Bib": "334",
        "Participants": [
            {"ID": COMPETITOR_ID, "Name": ["Oscar", "Adrian Rodriguez"]},
            {"ID": "A156", "Name": ["Chrystal", "Chen"]},
        ],
    }
    recalled_couple = {
        "ID": "C7", "Bib": "303",
        "Participants": [
            {"ID": "A13", "Name": ["Jasher", "Kuehn"]},
            {"ID": "A14", "Name": ["Brooke", "Johnson"]},
        ],
    }
    return {
        "ID": 178,
        "Name": "Adult Amateur Open A Int'l Latin #NR (CC,S,R,PD,J)",
        "Heat": HEAT_NUMBER,
        "Rounds": [
            {
                "Name": "Semi-Final",
                "Scoring_Method": "Prelims",
                "Dances": [{
                    "Dance_Name": "Int'l Cha Cha",
                    "Judges": judges,
                    "Competitors": [
                        {**recalled_couple, "Marks": [1, 1], "Result": None},
                        {**oscar_couple, "Marks": [0, 1], "Result": None},
                    ],
                }],
                "Summary": {
                    "Competitors": [
                        {**recalled_couple, "Total": 2, "Recalled": 1},
                        {**oscar_couple, "Total": 1, "Recalled": 0},
                    ],
                },
            },
            {
                "Name": "Final",
                "Scoring_Method": "Skated",
                "Dances": [{
                    "Dance_Name": "Int'l Cha Cha",
                    "Judges": judges,
                    "Competitors": [
                        {**recalled_couple, "Marks": [1, 1], "Result": 1},
                    ],
                }],
            },
        ],
    }


def _other_cyi_event():
    """A different heat number, to prove the fetch filters to the one requested."""
    event = _mock_event()
    return {**event, "Heat": "999", "Rounds": [event["Rounds"][1]]}


def install_ndca_mocks(page, fetch_log=None):
    """Intercepts every ndcapremier.com call the SPA's live judges-scores
    lookup makes, returning a fixed name->ID list and a fixed per-competitor
    Events list — no real network access.
    """
    def handle(route):
        url = route.request.url
        if fetch_log is not None:
            fetch_log.append(url)
        if "id=" in url:
            route.fulfill(json={
                "Status": 1,
                "Result": {"Events": [_mock_event(), _other_cyi_event()]},
            })
        elif "date=" in url:
            # HeatCard picks an arbitrary entrant of the contested group as the
            # fetch anchor (any of them resolves in real NDCA data), not
            # necessarily Oscar -- register every heat-628 entrant name so
            # whichever one gets picked still resolves. The `id=` branch above
            # ignores which id was actually requested, so the id value here
            # doesn't need to be distinct per name.
            route.fulfill(json={
                "Status": 1,
                "Result": [
                    {"ID": COMPETITOR_ID, "Name": ["Oscar", "Adrian Rodriguez"]},
                    {"ID": COMPETITOR_ID, "Name": ["Anastasiya", "Barysevich"]},
                    {"ID": COMPETITOR_ID, "Name": ["Bumchin", "Tegshjargal"]},
                ],
            })
        else:
            route.continue_()

    page.route("https://ndcapremier.com/**", handle)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _select_comp(page, cyi):
    page.evaluate(f"selectComp(compList.findIndex(c => c.cyi === {cyi}))")
    # loadComp() re-shows #status while its fetch is in flight, same as the
    # initial page load — wait for the real signal instead of guessing.
    page.wait_for_function(
        """() => {
            const s = document.getElementById('status');
            return s.classList.contains('hidden') || !s.textContent.includes('Loading');
        }""",
        timeout=15_000,
    )


def _search_competitor(page, name):
    inp = page.locator("#competitorSearch")
    inp.fill(name)
    inp.dispatch_event("input")
    # #competitorSearch is a native <input list=datalist>; WebKit can leave its
    # autocomplete popup open over the schedule below, silently swallowing the
    # next click (observed as a ~4% flake: the "open panel" click landed on the
    # popup instead of the pill, and only the *second* click actually toggled
    # the panel). Blur before anything below the search box gets clicked.
    inp.press("Escape")


def _click_contested_pill(page):
    page.locator("span:text-is('7th Contested')").click()
    panel_key = _panel_key(page)
    # HeatCard.toggleJudges() paints the expanded/loading state synchronously;
    # the real fetch (mocked, but still an async round trip) resolves after.
    page.wait_for_function(
        """(key) => {
            const el = document.querySelector(`[data-role="judges-panel"][data-panel-key="${key}"]`);
            if (!el || !el.classList.contains('expanded')) return true;
            return !el.textContent.includes('Loading judges scores');
        }""",
        arg=panel_key,
    )


def _panel_key(page):
    return page.evaluate("""() => {
        const pill = Array.from(document.querySelectorAll('span'))
            .find(s => s.textContent.trim() === '7th Contested');
        return pill.dataset.panelKey;
    }""")


def _panel(page):
    """The judges-panel belonging to the '7th Contested' pill specifically —
    every contested heat on the page has its own (mostly collapsed) panel,
    so a bare '.judges-panel' selector matches many elements."""
    return page.locator(f'[data-role="judges-panel"][data-panel-key="{_panel_key(page)}"]')


def _assert_panel_expanded(page, expanded):
    """Locator.get_attribute() is a single unretried read; wrap it in a poll
    so a same-tick DOM update (e.g. WebKit finishing the click's synchronous
    handler a beat late) can't read a stale class list."""
    page.wait_for_function(
        """([key, expanded]) => {
            const el = document.querySelector(`[data-role="judges-panel"][data-panel-key="${key}"]`);
            return (el?.classList.contains('expanded') ?? false) === expanded;
        }""",
        arg=[_panel_key(page), expanded],
    )


def _setup(page, spa_server, fetch_log=None):
    install_ndca_mocks(page, fetch_log)
    wait_for_spa(page, spa_server)
    _select_comp(page, CYI)
    _search_competitor(page, COMPETITOR_NAME)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJudgesScoresPanel:
    def test_pill_renders_for_contested_heat(self, page, spa_server):
        """heats/373.json's genuinely-contested heat 628 shows a Contested pill."""
        _setup(page, spa_server)
        assert page.locator("span:text-is('7th Contested')").count() == 1

    def test_click_opens_panel_with_content(self, page, spa_server):
        """Clicking the pill lazy-fetches and renders the judges' marks."""
        fetch_log = []
        _setup(page, spa_server, fetch_log)
        _click_contested_pill(page)

        panel = _panel(page)
        assert "expanded" in panel.get_attribute("class")
        text = panel.inner_text()
        assert "Heat 628" in text
        assert "Int'l Cha Cha" in text
        assert fetch_log, "expected the panel click to trigger live NDCA fetches"

    def test_only_requested_heat_shown(self, page, spa_server):
        """The mocked competitor has events for heat 628 AND heat 999 — only
        628 (the one behind the clicked pill) should ever render."""
        _setup(page, spa_server)
        _click_contested_pill(page)

        text = _panel(page).inner_text()
        assert "Heat 628" in text
        assert "Heat 999" not in text

    def test_final_round_shown_before_semifinal(self, page, spa_server):
        """The conclusive round (Final) renders above the earlier Prelims round."""
        _setup(page, spa_server)
        _click_contested_pill(page)

        text = _panel(page).inner_text()
        final_idx = text.index("Final")
        semi_idx = text.index("Semi-Final")
        assert final_idx < semi_idx, "Final round should render before Semi-Final"

    def test_prelims_round_shows_recall_status(self, page, spa_server):
        """The Prelims round shows both couples' recall outcome, not a placement."""
        _setup(page, spa_server)
        _click_contested_pill(page)

        text = _panel(page).inner_text()
        assert "Recalled" in text
        assert "Not recalled" in text

    def test_second_click_collapses_panel(self, page, spa_server):
        """Clicking the pill again toggles the panel closed."""
        _setup(page, spa_server)
        _click_contested_pill(page)
        _assert_panel_expanded(page, True)

        _click_contested_pill(page)
        _assert_panel_expanded(page, False)

    def test_reopen_uses_cache_not_refetch(self, page, spa_server):
        """A second open of the same panel reuses judgesDataCache instead of
        re-fetching — the fetch log should only grow on the first open."""
        fetch_log = []
        _setup(page, spa_server, fetch_log)

        _click_contested_pill(page)  # open (fetches)
        count_after_first_open = len(fetch_log)
        _click_contested_pill(page)  # close
        _click_contested_pill(page)  # reopen (should be cached)

        assert len(fetch_log) == count_after_first_open, (
            "reopening should not trigger new NDCA requests"
        )
        assert "Heat 628" in _panel(page).inner_text()

    def test_panel_survives_forced_rerender(self, page, spa_server):
        """A full schedule re-render (as the 10s auto-refresh performs) must not
        collapse or blank out an open panel — regression for a real bug where
        toggleJudgesPanel's direct DOM update bypassed the render path that
        restores state from judgesDataCache/expandedJudgesPanels."""
        _setup(page, spa_server)
        _click_contested_pill(page)
        assert "Heat 628" in _panel(page).inner_text()

        page.evaluate("generateSchedule()")

        panel = _panel(page)
        assert "expanded" in panel.get_attribute("class")
        assert "Heat 628" in panel.inner_text()

    def test_forced_rerender_preserves_scroll_position(self, page, spa_server):
        """Regression for a real bug: the periodic full re-render reset window
        scroll position (and, on mobile, could interrupt an in-progress touch
        scroll entirely), so a click moments later would land on whatever heat
        card now happened to occupy the old scroll offset."""
        _setup(page, spa_server)
        _click_contested_pill(page)

        page.evaluate("window.scrollTo(0, 200)")
        scroll_before = page.evaluate("window.scrollY")
        page.evaluate("generateSchedule()")
        scroll_after = page.evaluate("window.scrollY")

        assert scroll_after == scroll_before, "scroll position must survive a full re-render"

"""
Program-feed markers (awards / top-award ceremonies / first heat) on a
competitor's personal Heats schedule, plus the taxonomy-driven
costume-change marker that replaced the old NDCA-keyword-based one (see
static/dance-taxonomy.js's styleFamilyChanged() and thor.md 2026-08-16).

The live network call to ndcapremier.com's /feed/program/ is mocked via
page.route(), so this suite has no external dependency and can't be flaky on
NDCA's availability or on a real competition's schedule changing over time.

Fixture: City Lights Open (cyi 373, committed heats/373.json). Helen Piper
dances only in session '02' (Friday Morning), first heat 313 at 12:10:42 pm,
last heat 330 at 12:32:48 pm — the session itself runs from 8:30 am (heat
211, someone else) to 3:12 pm. She has zero heats in session '04' (Saturday
Morning), used below for the always-shown "top" ceremony test.

These tests lock in three regressions found by hand while building the
feature (see thor.md 2026-07-26):
  1. A competitor's own first heat can start hours after the session's real
     first heat; award/top notices from that gap belong to other heats and
     must not leak onto this competitor's schedule.
  2. Once trimmed, "First heat" must fall back to the *session's* first heat
     (useful for "when do I need to be there") when nothing relevant
     preceded this competitor's own first heat — but to their *own* first
     heat when a break/award did intervene, since the session-wide time is
     then stale.
  3. After a competitor's last heat, only the next award (the one covering
     their result) is relevant — later ones belong to heats they have no
     part in.
"""
import urllib.parse

import pytest
from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CYI = 373
COMPETITOR = "Helen Piper"


def install_program_mock(page, activities_by_code, cyi=CYI, name_has_prefix=True):
    """Intercepts every ndcapremier.com /feed/program/ call. `activities_by_code`
    maps a session code ("02", "04", ...) to a list of {title, date_time,
    duration} dicts rendered as that session's Activity items. Session IDs are
    just the code string — program.js only cares about recovering the code
    from Session.Name's "NN-" prefix or, failing that, Session.Abbreviation.

    `name_has_prefix=False` mimics competitions (e.g. Manhattan Dance
    Championships) whose Session.Name has no numeric prefix at all — only
    Abbreviation carries the code, zero-padded the same way heats/*.json is.
    """
    def handle(route):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(route.request.url).query)
        if params.get("cyi", [None])[0] != str(cyi):
            route.fulfill(json={"Status": 0})
            return
        session_id = params.get("session", [None])[0]
        if session_id is None:
            name_fn = (lambda code: f"{code}-Session {code}") if name_has_prefix else (lambda code: f"Session {code}")
            sessions = [
                {"ID": code, "Name": name_fn(code), "Abbreviation": code, "Date_Time": "1/1/2026 12:00 AM"}
                for code in activities_by_code
            ]
            route.fulfill(json={"Status": 1, "Result": {"Ballrooms": [{"ID": 1, "Name": None, "Sessions": sessions}]}})
            return
        acts = activities_by_code.get(session_id, [])
        result = [
            {"Type": "Activity", "Title": a["title"], "Subtitle": "", "Duration": a.get("duration", 10),
             "Date_Time": a["date_time"], "Floors": None}
            for a in acts
        ]
        route.fulfill(json={"Status": 1, "Result": result})

    page.route("https://ndcapremier.com/**", handle)


def _select_city_lights(page):
    page.evaluate(f"selectComp(compList.findIndex(c => c.cyi === {CYI}))")
    page.wait_for_function(
        """() => {
            const s = document.getElementById('status');
            return s.classList.contains('hidden') || !s.textContent.includes('Loading');
        }"""
    )


def _search_and_wait_for_markers(page, spa_server):
    """Load the SPA, switch to City Lights Open, search Helen Piper, and wait
    for the async program-markers fetch to finish and re-render."""
    wait_for_spa(page, spa_server, query="?show_elo=1")
    _select_city_lights(page)
    page.evaluate(f"setHeatsSearch('{COMPETITOR}')")
    # programMarkers is a top-level `let` in index.html's classic script, so
    # (like compList/rankingData elsewhere in this suite) it's reachable by
    # bare name from page.evaluate even though it isn't attached to window.
    page.wait_for_function("() => typeof programMarkers !== 'undefined' && programMarkers !== null",
                            timeout=10_000)
    # The fetch resolving triggers a re-render on the next microtask/tick;
    # give it a beat to land before reading the DOM.
    page.wait_for_timeout(300)
    return page.locator("#scheduleContent").inner_text()


class TestProgramMarkers:
    def test_leading_backlog_of_awards_is_fully_trimmed(self, page, spa_server):
        # Every leading award belongs to a heat before this competitor's own
        # first heat -- none of them are relevant, so all get dropped (only
        # a 'top' ceremony, or -- previously -- a trailing break/costume
        # marker, would have survived; there's no such marker anymore).
        install_program_mock(page, {
            "02": [
                {"title": "Awards", "date_time": "1/23/2026 9:45 AM"},
                {"title": "Awards", "date_time": "1/23/2026 11:35 AM"},
            ],
        })
        text = _search_and_wait_for_markers(page, spa_server)
        assert "9:45" not in text
        assert "11:35" not in text
        assert "First heat" in text

    def test_costume_change_marker_fires_on_style_family_transition(self, page, spa_server):
        # Helen's real schedule in this fixture never actually changes style
        # family (313-330 are all Int'l Ballroom at varying levels) -- inject
        # one mid-session so the taxonomy-driven marker has something to fire
        # on, and confirm it lands in reading order between the two affected
        # heats rather than leaking to the very first heat (costume-change
        # never fires before a session's first block).
        wait_for_spa(page, spa_server, query="?show_elo=1")
        install_program_mock(page, {"02": []})
        _select_city_lights(page)
        page.evaluate("""() => {
            const heat = Object.values(heatsByKey).find(h => h.heat_number === '320' && h.session === '02');
            const entry = heat.entries.find(e => e.competitor1 === 'Helen Piper' || e.competitor2 === 'Helen Piper');
            heatsData.events[entry.event] = "AC-B2 Cl. Pre-Bronze Amer. Foxtrot";
        }""")
        page.evaluate(f"setHeatsSearch('{COMPETITOR}')")
        page.wait_for_function("() => typeof programMarkers !== 'undefined' && programMarkers !== null", timeout=10_000)
        page.wait_for_timeout(300)
        text = page.locator("#scheduleContent").inner_text()
        assert "Costume change" in text
        assert text.index("318") < text.index("Costume change") < text.index("320")
        assert text.index("Costume change") > text.index("First heat")

    def test_first_heat_falls_back_to_session_start_with_no_backlog(self, page, spa_server):
        install_program_mock(page, {"02": []})
        text = _search_and_wait_for_markers(page, spa_server)
        # Session 02's real first heat (heat 211, not Helen's) is 8:30 am —
        # with nothing relevant in between, that's what should be surfaced,
        # not Helen's own 12:10 pm.
        assert "First heat 8:30 am" in text

    def test_first_heat_uses_own_heat_when_backlog_present(self, page, spa_server):
        install_program_mock(page, {
            "02": [{"title": "Awards", "date_time": "1/23/2026 9:45 AM"}],
        })
        text = _search_and_wait_for_markers(page, spa_server)
        assert "First heat 12:10 pm" in text
        assert "8:30 am" not in text

    def test_trailing_awards_stop_at_first_relevant_one(self, page, spa_server):
        install_program_mock(page, {
            "02": [
                {"title": "Awards", "date_time": "1/23/2026 12:46 PM"},
                {"title": "Awards", "date_time": "1/23/2026 1:15 PM"},
                {"title": "Awards", "date_time": "1/23/2026 2:00 PM"},
            ],
        })
        text = _search_and_wait_for_markers(page, spa_server)
        assert "12:46" in text
        assert "1:15" not in text
        assert "2:00" not in text

    def test_trailing_top_ceremony_survives_after_the_stopping_award(self, page, spa_server):
        # Regression: California Star Ball's Sunday session ends with
        # "Awards and Best Of The Best Dance Off" immediately followed by
        # "Ca Star Ball Top Awards" — the top ceremony must not be swallowed
        # by the same truncation that (correctly) drops later unrelated
        # awards after a competitor's last heat.
        install_program_mock(page, {
            "02": [
                {"title": "Awards", "date_time": "1/23/2026 12:46 PM"},
                {"title": "Top Awards", "date_time": "1/23/2026 12:50 PM"},
                {"title": "Awards", "date_time": "1/23/2026 1:15 PM"},
            ],
        })
        text = _search_and_wait_for_markers(page, spa_server)
        assert "12:46" in text
        assert "12:50" in text
        assert "1:15" not in text

    def test_leading_top_ceremony_survives_the_backlog_trim(self, page, spa_server):
        # Same regression, mirrored on the leading side: a 'top' entry buried
        # in the backlog before this competitor's own first heat must not be
        # discarded along with the unrelated 'award' noise around it.
        install_program_mock(page, {
            "02": [
                {"title": "Top Awards", "date_time": "1/23/2026 9:00 AM"},
                {"title": "Awards", "date_time": "1/23/2026 9:45 AM"},
            ],
        })
        text = _search_and_wait_for_markers(page, spa_server)
        assert "Top Awards" in text
        assert "9:45" not in text

    def test_session_code_falls_back_to_abbreviation_without_name_prefix(self, page, spa_server):
        install_program_mock(page, {
            "02": [{"title": "Awards", "date_time": "1/23/2026 12:46 PM"}],
        }, name_has_prefix=False)
        text = _search_and_wait_for_markers(page, spa_server)
        assert "12:46" in text

    def test_top_ceremony_shown_for_session_competitor_does_not_dance(self, page, spa_server):
        install_program_mock(page, {
            "04": [{"title": "Top Teachers and Studios", "date_time": "1/24/2026 9:00 PM"}],
        })
        text = _search_and_wait_for_markers(page, spa_server)
        assert "Top Teachers and Studios" in text
        assert "Saturday Morning" in text

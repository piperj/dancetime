"""
Rounds tab (static/rounds.js) -- exercised directly against synthetic
heatsData injected via page.evaluate(), per rounds.js's explicit
Rounds.init({...}) design (no bare-global fallback to whatever competition
wait_for_spa()'s initial loadComp() happened to select).
"""
import re

import pytest
from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


def count_cells(html):
    # 'class="cell' alone also matches the *container* div's
    # 'class="cells"' -- require the word to end right after "cell".
    return len(re.findall(r'class="cell(?:"| )', html))

# Builds a small synthetic competition (one competitor, four heats: a solo
# heat, a contested heat, a style-family transition into a third heat, and
# a fourth heat with a large heat_number gap after it -- a full round's
# worth of missing heat_numbers, per rounds.js's heatNumberGap-based break
# detection, not the old floor-position heuristic) and calls
# Rounds.init()+Rounds.render() against it.
SETUP_JS = """
() => {
  const events = [
    "AC-A1 Full Bronze Amer. Waltz",   // 0 -- amSmooth
    "AC-A1 Full Bronze Amer. Tango",   // 1 -- amSmooth
    "AC-A1 Full Bronze Int'l Waltz",   // 2 -- intlBallroom
  ];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('h1', '100', '2026-01-01T10:00:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' },
    ]),
    heat('h2', '101', '2026-01-01T10:01:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 1, bib: '1', result: '' },
      { competitor1: 'Other X', competitor2: 'Other Y', event: 1, bib: '2', result: '' },
    ]),
    heat('h3', '102', '2026-01-01T10:05:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 2, bib: '1', result: '' },
    ]),
    heat('h4', '110', '2026-01-01T10:20:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 2, bib: '1', result: '' },
    ]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' },
    events,
    competitor_heats: { 'Test A': ['h1', 'h2', 'h3', 'h4'], 'Test B': ['h1', 'h2', 'h3', 'h4'] },
    competitor_studios: {},
    heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({
    cyi: 999999,
    heatsData: window.__testHeatsData,
    heatsByKey: window.__testHeatsByKey,
    floorPositionByKey: {},
    sessionFirstHeatTime: { '01': '2026-01-01T10:00:00' },
    programMarkers: null,
  });
  return Rounds.render('Test A');
}
"""


class TestRoundsRender:
    def test_render_without_matching_context_shows_placeholder(self, page, spa_server):
        # Rounds.init() has never been pointed at "Test A" -- whatever real
        # competition wait_for_spa()'s initial loadComp() selected has no
        # such competitor, so this must not silently render someone else's
        # schedule (the explicit-init design's whole point).
        wait_for_spa(page, spa_server)
        html = page.evaluate("() => Rounds.render('Test A')")
        assert "No heats found" in html

    def test_grid_renders_dance_letters_in_heat_number_order(self, page, spa_server):
        wait_for_spa(page, spa_server)
        html = page.evaluate(SETUP_JS)
        assert html.index(">100<") < html.index(">101<") < html.index(">102<")
        assert ">W<" in html
        assert ">T<" in html

    def test_contested_dot_on_shared_heat(self, page, spa_server):
        wait_for_spa(page, spa_server)
        html = page.evaluate(SETUP_JS)
        assert "dot contested" in html

    def test_solo_dot_on_lone_couple_heat(self, page, spa_server):
        wait_for_spa(page, spa_server)
        html = page.evaluate(SETUP_JS)
        assert "dot solo" in html

    def test_costume_change_marker_on_style_family_transition(self, page, spa_server):
        wait_for_spa(page, spa_server)
        html = page.evaluate(SETUP_JS)
        assert "costume change" in html
        assert html.index(">101<") < html.index("costume change") < html.index(">102<")

    def test_no_costume_change_marker_between_same_family_heats(self, page, spa_server):
        # heat 100 -> heat 101 is amSmooth Waltz -> amSmooth Tango: a
        # level-only/no-level change within the same family, never fires.
        wait_for_spa(page, spa_server)
        html = page.evaluate(SETUP_JS)
        first_marker = html.find("costume change")
        assert first_marker == -1 or html.index(">100<") < html.index(">101<") < first_marker

    def test_large_gap_closes_the_round_with_no_break_pill(self, page, spa_server):
        # h3 (102) -> h4 (110) is a gap of 7 heat_numbers, past
        # intlBallroom's 5-dance round length -- crosses the
        # heatNumberGap-based break threshold (not a floor-position
        # heuristic; rounds.js no longer uses one -- see thor.md 2026-08-16).
        # Rounds has no break-time treatment at all -- the round just closes
        # and a fresh one starts, with no visual marker in between.
        wait_for_spa(page, spa_server)
        html = page.evaluate(SETUP_JS)
        assert "break-row" not in html
        assert html.count('class="heat-row"') == 3  # 100, 101 in one row; 102 and 110 each start fresh

    def test_now_time_stops_present_for_now_line(self, page, spa_server):
        wait_for_spa(page, spa_server)
        html = page.evaluate(SETUP_JS)
        assert html.count("data-now-time=") >= 3


# A single-block fixture isolating the round-sequence gap logic: heat 200
# (W) and 202 (VW) are this couple's own; heat 201 (T) is a *real* heat for
# someone else in between (an "empty" cell, with its own number/letter
# shown); heat 203 (F) doesn't exist for anyone at all (a "removed"
# position -- no cell rendered whatsoever, not even a placeholder, per the
# user: a horizontal line there read as confusing). Q (204) never happens.
GAP_SETUP_JS = """
() => {
  const events = [
    "AC-A1 Full Bronze Int'l Waltz",          // 0
    "AC-A1 Full Bronze Int'l Tango",          // 1 -- danced only by Other couple
    "AC-A1 Full Bronze Int'l Viennese Waltz", // 2
  ];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('g1', '200', '2026-01-01T10:00:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' },
    ]),
    heat('g2', '201', '2026-01-01T10:01:00', [
      { competitor1: 'Other X', competitor2: 'Other Y', event: 1, bib: '2', result: '' },
    ]),
    heat('g3', '202', '2026-01-01T10:03:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 2, bib: '1', result: '' },
    ]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' },
    events,
    competitor_heats: { 'Test A': ['g1', 'g3'], 'Test B': ['g1', 'g3'], 'Other X': ['g2'], 'Other Y': ['g2'] },
    competitor_studios: {},
    heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({
    cyi: 999999,
    heatsData: window.__testHeatsData,
    heatsByKey: window.__testHeatsByKey,
    floorPositionByKey: {},
    sessionFirstHeatTime: { '01': '2026-01-01T10:00:00' },
    programMarkers: null,
  });
  return Rounds.render('Test A');
}
"""


class TestRoundsGapCells:
    def test_empty_cell_shows_the_real_gap_heats_own_number_and_letter(self, page, spa_server):
        wait_for_spa(page, spa_server)
        html = page.evaluate(GAP_SETUP_JS)
        assert 'class="cell empty"' in html
        assert ">201<" in html
        assert ">T<" in html

    def test_removed_position_renders_no_cell_at_all(self, page, spa_server):
        # F (heat 203) never existed for anyone -- no placeholder, no line,
        # nothing. Confirmed by counting rendered cells: just the two real
        # ones (W, VW) plus the one empty gap cell (T) -- three total, not
        # five padded out to the family's full round length.
        wait_for_spa(page, spa_server)
        html = page.evaluate(GAP_SETUP_JS)
        assert count_cells(html) == 3
        assert "removed" not in html


class TestRoundsBroadLevelGrouping:
    def test_pre_and_full_bronze_share_one_header(self, page, spa_server):
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = [
    "AC-A1 Pre-Bronze Int'l Waltz",
    "AC-A1 Full Bronze Int'l Waltz",
  ];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('b1', '300', '2026-01-01T10:00:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' }]),
    heat('b2', '305', '2026-01-01T10:10:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 1, bib: '1', result: '' }]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: { 'Test A': ['b1', 'b2'], 'Test B': ['b1', 'b2'] },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null });
  return Rounds.render('Test A');
}
""")
        assert html.count("style-block") == 1  # a single block instance, not one per sub-level
        assert html.count("Bronze International Ballroom") == 1
        assert "Pre-Bronze" not in html
        assert "Full Bronze" not in html

    def test_no_separator_prebronze_still_groups_as_bronze(self, page, spa_server):
        # Real event strings sometimes concatenate "Pre" and "Bronze" with
        # no separator ("PreBronze") -- a \b word-boundary check before
        # "Bronze" would miss this, since there's no non-word character
        # between "Pre" and "Bronze" to form a boundary.
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = ["AC-A1 PreBronze Int'l Waltz"];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('pb1', '310', '2026-01-01T10:00:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' }]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: { 'Test A': ['pb1'], 'Test B': ['pb1'] },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null });
  return Rounds.render('Test A');
}
""")
        assert "Bronze International Ballroom" in html
        assert "PreBronze" not in html

    def test_newcomer_novice_and_beginner_share_one_beginner_header(self, page, spa_server):
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = [
    "AC-A1 Newcomer Int'l Waltz",
    "AC-A1 Novice Int'l Waltz",
    "AC-A1 Beginner 1 Int'l Waltz",
    "AC-A1 Beginner 2 Int'l Waltz",
  ];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('bg0', '899', '2026-01-01T09:55:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' }]),
    heat('bg1', '900', '2026-01-01T10:00:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 1, bib: '1', result: '' }]),
    heat('bg2', '905', '2026-01-01T10:10:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 2, bib: '1', result: '' }]),
    heat('bg3', '910', '2026-01-01T10:20:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 3, bib: '1', result: '' }]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: { 'Test A': ['bg0', 'bg1', 'bg2', 'bg3'], 'Test B': ['bg0', 'bg1', 'bg2', 'bg3'] },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null });
  return Rounds.render('Test A');
}
""")
        assert html.count("style-block") == 1
        assert html.count("Beginner International Ballroom") == 1
        assert "Newcomer" not in html
        assert "Novice" not in html
        assert "Beginner 1" not in html
        assert "Beginner 2" not in html


class TestRoundsNightClubSingleLine:
    def test_night_club_round_has_no_padding_or_gap_cells(self, page, spa_server):
        # Night Club opts out of the fixed round-sequence grid entirely --
        # danced cells append flat, in one continuous sequence, with no
        # empty/removed placeholders between unrelated Night Club dances.
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = ["AC-A1 Full Bronze Merengue", "AC-A1 Full Bronze Hustle"];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('n1', '400', '2026-01-01T10:00:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' }]),
    heat('n2', '401', '2026-01-01T10:01:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 1, bib: '1', result: '' }]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: { 'Test A': ['n1', 'n2'], 'Test B': ['n1', 'n2'] },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null });
  return Rounds.render('Test A');
}
""")
        assert html.count('class="heat-row"') == 1  # both dances land in the same continuous row
        assert count_cells(html) == 2                # just the two real cells, no gap/empty filler
        assert ">MER<" in html
        assert ">H<" in html


class TestRoundsMultiDanceGrouping:
    def test_multi_dance_cells_wrapped_in_one_bounding_box(self, page, spa_server):
        # One heat_number grouping three dances (W,T,F) explodes into three
        # cells, all wrapped in one bounding box spanning three grid tracks
        # -- so the group still reads as one heat, not three unrelated ones.
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = ["AC-A1 Full Bronze Amer. Smooth (W,T,F)"];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('m1', '500', '2026-01-01T10:00:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' }]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: { 'Test A': ['m1'], 'Test B': ['m1'] },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null });
  return Rounds.render('Test A');
}
""")
        assert 'class="multi-dance-group" style="grid-column:span 3"' in html
        assert count_cells(html) == 3
        assert ">W<" in html and ">T<" in html and ">F<" in html


class TestRoundsTrailingActivities:
    def test_stops_after_first_award_past_last_heat(self, page, spa_server):
        # Past this competitor's last heat, only the award covering it is
        # relevant -- later awards belong to other levels/heats entirely.
        # Mirrors generateSchedule()'s identical trim in index.html.
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = ["AC-A1 Full Bronze Amer. Waltz"];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('w1', '800', '2026-01-01T08:32:00', [{ competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' }]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: { 'Test A': ['w1'], 'Test B': ['w1'] },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({
    cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
    floorPositionByKey: {}, sessionFirstHeatTime: {},
    programMarkers: { bySession: { '01': { activities: [
      { time: '2026-01-01T09:02:00', title: 'Awards', category: 'award' },
      { time: '2026-01-01T10:22:00', title: 'Awards', category: 'award' },
      { time: '2026-01-01T11:17:00', title: 'Awards', category: 'award' },
      { time: '2026-01-01T12:20:00', title: 'Top Awards', category: 'top' },
    ] } } },
  });
  return Rounds.render('Test A');
}
""")
        assert html.count("awards-row") == 2  # the one real award + the always-relevant top ceremony
        assert "9:02 am" in html
        assert "10:22 am" not in html
        assert "11:17 am" not in html
        assert "12:20 pm" in html


class TestRoundsNavWiring:
    def test_rounds_tab_hidden_without_heats_data(self, page, spa_server):
        wait_for_spa(page, spa_server, query="?show_elo=1")
        page.evaluate("() => { heatsData = null; updateTabVisibility(); }")
        assert "hidden" in (page.locator('nav button[data-tab="rounds"]').get_attribute("class") or "")

    def test_clicking_rounds_tab_activates_it(self, page, spa_server):
        wait_for_spa(page, spa_server)
        page.locator('nav button[data-tab="rounds"]').click()
        assert "active" in page.locator('nav button[data-tab="rounds"]').get_attribute("class")
        assert page.evaluate("activeTab") == "rounds"

    def test_now_line_picks_up_rounds_stops(self, page, spa_server):
        # Rounds renders into the same #scheduleContent element Heats uses
        # (no separate #roundsContent container -- see the plan at
        # /Users/thor/.claude/plans/silly-tickling-moler.md), so now-line.js
        # needs zero changes to see Rounds' data-now-time stops.
        wait_for_spa(page, spa_server)
        page.evaluate(SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        page.wait_for_timeout(50)
        stops = page.evaluate("NowLine._test.debugStops()")
        assert len(stops) >= 3

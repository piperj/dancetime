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

    def test_style_block_shows_first_dance_start_time(self, page, spa_server):
        # h1 (heat 100, amSmooth Waltz) starts the first style block at
        # 10:00am -- the style-label box shows that start time.
        wait_for_spa(page, spa_server)
        html = page.evaluate(SETUP_JS)
        assert "· 10:00 am" in html

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
    def test_night_club_round_has_no_padding_between_adjacent_heats(self, page, spa_server):
        # Night Club opts out of the fixed round-sequence grid entirely --
        # danced cells append flat, in one continuous sequence -- but two
        # genuinely adjacent heat_numbers (no real gap at all) still render
        # with nothing extra between them.
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

    def test_night_club_fills_a_real_gap_between_the_couples_own_heats(self, page, spa_server):
        # Manhattan real-data case (cyi 904, Johan Piper): heat 269
        # "Beginner1 Hustle" and heat 274 "Beginner 2 Hustle" -- two
        # DIFFERENT verbatim sub-levels, 5 heats apart, genuinely interleaved
        # with each other and a third sub-level on the real schedule, not
        # scheduled as separate blocks the way standard families' sub-levels
        # are. Night Club's *broad* key still collapses both sub-levels
        # under one shared "Beginner Night Club" header/RoundSequencer (no
        # fixed round width to reset against) -- but within that shared
        # sequencer, this couple's own Hustle code showing up a second time
        # is the signal that a new pass through the syllabus started, so it
        # still gets its own row rather than reading as one heat danced
        # twice in a row. The real West Coast Swing heat for someone else,
        # sitting between the couple's two Hustles, is captured as a
        # trailing empty cell on the first row before the split.
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = ["AC-A1 Beginner1 Hustle", "AC-A1 Beginner 2 West Coast Swing", "AC-A1 Beginner 2 Hustle"];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('nc1', '269', '2026-01-01T19:31:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' },
    ]),
    heat('nc2', '270', '2026-01-01T19:35:00', [
      { competitor1: 'Other X', competitor2: 'Other Y', event: 1, bib: '2', result: '' },
    ]),
    heat('nc3', '274', '2026-01-01T19:50:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 2, bib: '1', result: '' },
    ]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: {
      'Test A': ['nc1', 'nc3'], 'Test B': ['nc1', 'nc3'],
      'Other X': ['nc2'], 'Other Y': ['nc2'],
    },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null });
  return Rounds.render('Test A');
}
""")
        assert html.count("style-block") == 1  # one shared "Beginner Night Club" header
        assert html.count('class="heat-row"') == 2  # own-code repeat splits into two separate rows
        assert count_cells(html) == 3  # 269 H, 270 WCS (empty), 274 H
        assert 'class="cell empty"' in html
        assert ">270<" in html and ">WCS<" in html
        assert ">271<" not in html and ">272<" not in html and ">273<" not in html


class TestRoundsTrailingFill:
    def test_trailing_positions_show_as_empty_unless_removed_for_everyone(self, page, spa_server):
        # Johan Piper / Manhattan-style fixture: round 1 has no Paso Doble
        # heat at all (removed for everyone -- no box), but Jive still runs
        # for someone else (an empty box); rounds 2-4 have all five
        # canonical Int'l Latin positions, with Jive always empty since this
        # couple never dances it. Wanted output: "C S R [J]" then three
        # rounds of "C S R PD [J]" -- the box after the couple's own last
        # dance of a round is no longer silently dropped; it's only skipped
        # when the organizers truly never scheduled anyone there.
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = [
    "AC-A1 Full Bronze Int'l Cha Cha",     // 0
    "AC-A1 Full Bronze Int'l Samba",       // 1
    "AC-A1 Full Bronze Int'l Rumba",       // 2
    "AC-A1 Full Bronze Int'l Paso Doble",  // 3
    "AC-A1 Full Bronze Int'l Jive",        // 4
  ];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const mine = (num) => ({ competitor1: 'Test A', competitor2: 'Test B', event: num, bib: '1', result: '' });
  const other = (num) => ({ competitor1: 'Other X', competitor2: 'Other Y', event: num, bib: '2', result: '' });
  const heats = [
    // Round 1: C,S,R mine; PD (heat 700) truly removed for everyone -- no
    // entry at that number at all, its slot just goes unused; J (701) runs
    // for someone else only.
    heat('r1c', '697', '2026-01-01T10:00:00', [mine(0)]),
    heat('r1s', '698', '2026-01-01T10:01:00', [mine(1)]),
    heat('r1r', '699', '2026-01-01T10:02:00', [mine(2)]),
    heat('r1j', '701', '2026-01-01T10:03:00', [other(4)]),
    // Round 2: full C,S,R,PD mine; J other-only.
    heat('r2c', '702', '2026-01-01T10:10:00', [mine(0)]),
    heat('r2s', '703', '2026-01-01T10:11:00', [mine(1)]),
    heat('r2r', '704', '2026-01-01T10:12:00', [mine(2)]),
    heat('r2p', '705', '2026-01-01T10:13:00', [mine(3)]),
    heat('r2j', '706', '2026-01-01T10:14:00', [other(4)]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: {
      'Test A': ['r1c', 'r1s', 'r1r', 'r2c', 'r2s', 'r2r', 'r2p'],
      'Test B': ['r1c', 'r1s', 'r1r', 'r2c', 'r2s', 'r2r', 'r2p'],
      'Other X': ['r1j', 'r2j'], 'Other Y': ['r1j', 'r2j'],
    },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null });
  return Rounds.render('Test A');
}
""")
        # Round 1: C, S, R filled + one empty J cell (heat 701) -- no PD box at all.
        assert count_cells(html) == 3 + 1 + 4 + 1  # round1: 3 mine + 1 empty; round2: 4 mine + 1 empty
        assert html.count(">J<") == 2  # one empty J cell per round
        assert ">701<" in html  # the real heat number behind round 1's empty J cell
        assert html.count(">PD<") == 1  # round 1's Paso Doble never rendered at all

    def test_leading_positions_fill_when_couples_only_dance_is_last_in_round(self, page, spa_server):
        # Manhattan real-data bug: this couple's only Int'l Latin entry is
        # Jive (the round's last canonical position), so fillGap's old
        # lastPlacedNum-forward math had nothing to anchor from on a row's
        # very first placement -- none of the leading C/S/R/PD boxes ever
        # rendered. Anchoring from the current heatNumber backward instead
        # fixes it: C, S, R, PD should all show as empty boxes before the
        # filled J cell.
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = [
    "AC-A1 Full Bronze Int'l Cha Cha",     // 0
    "AC-A1 Full Bronze Int'l Samba",       // 1
    "AC-A1 Full Bronze Int'l Rumba",       // 2
    "AC-A1 Full Bronze Int'l Paso Doble",  // 3
    "AC-A1 Full Bronze Int'l Jive",        // 4
  ];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const other = (num) => ({ competitor1: 'Other X', competitor2: 'Other Y', event: num, bib: '2', result: '' });
  const mine = (num) => ({ competitor1: 'Test A', competitor2: 'Test B', event: num, bib: '1', result: '' });
  const heats = [
    heat('m1', '994', '2026-01-01T10:00:00', [other(0)]),
    heat('m2', '995', '2026-01-01T10:01:00', [other(1)]),
    heat('m3', '996', '2026-01-01T10:02:00', [other(2)]),
    heat('m4', '997', '2026-01-01T10:03:00', [other(3)]),
    heat('m5', '998', '2026-01-01T10:04:00', [mine(4)]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: {
      'Test A': ['m5'], 'Test B': ['m5'],
      'Other X': ['m1', 'm2', 'm3', 'm4'], 'Other Y': ['m1', 'm2', 'm3', 'm4'],
    },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null });
  return Rounds.render('Test A');
}
""")
        assert count_cells(html) == 5  # C, S, R, PD empty + J filled
        assert 'class="cell empty"' in html
        assert html.count('class="cell empty"') == 4
        assert ">994<" in html and ">C<" in html
        assert ">998<" in html and ">J<" in html

    def test_multi_dance_round_disables_trailing_fill(self, page, spa_server):
        # IGB 2026 real-data bug: a multi-dance grouped heat (W,T,Q sharing
        # one heat_number) advances `pos` by one per code without regard to
        # its real seq index, so trusting `pos` for trailing-fill math
        # wandered into the *next* physical round's real heats and
        # mislabeled them as this round's missing tail. No trailing cells
        # should render after a multi-dance round at all.
        wait_for_spa(page, spa_server)
        html = page.evaluate("""
() => {
  const events = [
    "AC-A1 Beginner Int'l Ballroom (W,T,Q)",  // 0 -- multi-dance, intlBallroom
    "AC-A1 Beginner Int'l Waltz",             // 1 -- next round, someone else
  ];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('i1', '464', '2026-01-01T10:00:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' },
    ]),
    heat('i2', '465', '2026-01-01T10:01:00', [
      { competitor1: 'Other X', competitor2: 'Other Y', event: 1, bib: '2', result: '' },
    ]),
    heat('i3', '466', '2026-01-01T10:02:00', [
      { competitor1: 'Other X', competitor2: 'Other Y', event: 1, bib: '2', result: '' },
    ]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: {
      'Test A': ['i1'], 'Test B': ['i1'],
      'Other X': ['i2', 'i3'], 'Other Y': ['i2', 'i3'],
    },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null });
  return Rounds.render('Test A');
}
""")
        assert count_cells(html) == 3  # just W, T, Q -- no bogus trailing "465 W" / "466 W" cells
        assert ">465<" not in html
        assert ">466<" not in html


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


# Two same-code Night Club heats for one couple, 15 minutes apart -- Night
# Club has no fixed round width (roundSequenceFor returns null), so the
# couple's own code repeating is what splits them into two rows (see
# RoundSequencer.place's null-seq branch); the 15-minute gap between the
# first row's last placed heat and the second row's start crosses
# BREAK_THRESHOLD_MINUTES (8), so the second row gets a ⏸️ gutter icon.
BREAK_SETUP_JS = """
() => {
  const events = ["AC-A1 Full Bronze Hustle"];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('br1', '500', '2026-01-01T10:00:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' },
    ]),
    heat('br2', '501', '2026-01-01T10:15:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' },
    ]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: { 'Test A': ['br1', 'br2'], 'Test B': ['br1', 'br2'] },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: { '01': '2026-01-01T10:00:00' }, programMarkers: null });
}
"""

# Two consecutive Int'l Ballroom heats (Waltz then Tango, adjacent seq
# positions -- no round flush between them) for the same couple, but with
# Test A's partner switching from 'Test B' to 'Carol Jones' between heats --
# the second cell gets a partner-swap badge.
SWAP_SETUP_JS = """
() => {
  const events = ["AC-A1 Full Bronze Int'l Waltz", "AC-A1 Full Bronze Int'l Tango"];
  function heat(key, heatNumber, time, entries) {
    return { key, heat_number: heatNumber, session: '01', time, round: 'Final', entries };
  }
  const heats = [
    heat('sw1', '600', '2026-01-01T10:00:00', [
      { competitor1: 'Test A', competitor2: 'Test B', event: 0, bib: '1', result: '' },
    ]),
    heat('sw2', '601', '2026-01-01T10:01:00', [
      { competitor1: 'Test A', competitor2: 'Carol Jones', event: 1, bib: '1', result: '' },
    ]),
  ];
  window.__testHeatsData = {
    sessions: { '01': 'Test Session' }, events,
    competitor_heats: { 'Test A': ['sw1', 'sw2'], 'Test B': ['sw1'], 'Carol Jones': ['sw2'] },
    competitor_studios: {}, heats,
  };
  window.__testHeatsByKey = Object.fromEntries(heats.map(h => [h.key, h]));
  Rounds.init({ cyi: 999999, heatsData: window.__testHeatsData, heatsByKey: window.__testHeatsByKey,
                floorPositionByKey: {}, sessionFirstHeatTime: { '01': '2026-01-01T10:00:00' }, programMarkers: null });
}
"""


class TestRoundsTapToReveal:
    # Title tooltips don't work on a phone -- both the break (⏸️) and
    # partner-swap (🔄) icons instead expose their label via a tap that
    # toggles `.revealed` on the `[data-reveal]` element (see rounds.js's
    # delegated click listener). Exercised against real DOM (setScheduleHTML),
    # not just the returned HTML string, since this is a live click handler.

    def test_tap_break_icon_reveals_minutes(self, page, spa_server):
        wait_for_spa(page, spa_server)
        page.evaluate(BREAK_SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        icon = page.locator('.icon[data-reveal]')
        assert icon.count() == 1
        assert "revealed" not in (icon.get_attribute("class") or "")
        icon.click()
        assert "revealed" in icon.get_attribute("class")
        assert "15 min" in icon.locator(".reveal-text").inner_text()

    def test_tap_break_icon_again_hides_it(self, page, spa_server):
        # classList.toggle -- a second tap on the same icon reverses the
        # first, hiding the label again.
        wait_for_spa(page, spa_server)
        page.evaluate(BREAK_SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        icon = page.locator('.icon[data-reveal]')
        icon.click()
        icon.click()
        assert "revealed" not in (icon.get_attribute("class") or "")

    def test_tap_swap_badge_reveals_partner_first_name(self, page, spa_server):
        wait_for_spa(page, spa_server)
        page.evaluate(SWAP_SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        badge = page.locator(".badge-swap[data-reveal]")
        assert badge.count() == 1
        badge.click()
        assert "revealed" in badge.get_attribute("class")
        assert badge.locator(".reveal-text").inner_text() == "Carol"

    def test_tapping_reveal_icon_does_not_open_the_heat_box(self, page, spa_server):
        # The reveal icons sit inside a `.cell[data-round-key]` -- without the
        # click handler's [data-reveal] guard, tapping either icon would also
        # pop open the Heats-tab heat-box underneath it.
        wait_for_spa(page, spa_server)
        page.evaluate(SWAP_SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        page.locator(".badge-swap[data-reveal]").click()
        assert page.locator(".round-heat-box").count() == 0


class TestRoundsHeatBoxTap:
    # Tapping a filled cell drops the same Heats-tab heat-box card right
    # under that cell's row; a second tap on the same cell closes it; tapping
    # a different cell swaps which one is open (single-expansion model,
    # mirroring HeatCard's own behavior).

    def test_tap_cell_opens_heat_box_below_its_row(self, page, spa_server):
        wait_for_spa(page, spa_server)
        page.evaluate(SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        assert page.locator(".round-heat-box").count() == 0
        page.locator(".cell[data-round-key]").first.click()
        boxes = page.locator(".round-heat-box")
        assert boxes.count() == 1
        assert boxes.locator(".heat-box").count() == 1

    def test_tap_same_cell_again_closes_the_box(self, page, spa_server):
        wait_for_spa(page, spa_server)
        page.evaluate(SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        cell = page.locator(".cell[data-round-key]").first
        cell.click()
        assert page.locator(".round-heat-box").count() == 1
        cell.click()
        assert page.locator(".round-heat-box").count() == 0

    def test_tap_different_cell_swaps_the_open_box(self, page, spa_server):
        wait_for_spa(page, spa_server)
        page.evaluate(SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        cells = page.locator(".cell[data-round-key]")
        assert cells.count() >= 2
        first_key = cells.nth(0).get_attribute("data-round-key")
        second_key = cells.nth(1).get_attribute("data-round-key")
        assert first_key != second_key

        cells.nth(0).click()
        assert page.locator(".round-heat-box").count() == 1
        assert page.locator(".round-heat-box").get_attribute("data-round-key") == first_key

        cells.nth(1).click()
        boxes = page.locator(".round-heat-box")
        assert boxes.count() == 1  # the old box is gone, not stacked
        assert boxes.get_attribute("data-round-key") == second_key

    def test_box_survives_rerender_via_open_round_key(self, page, spa_server):
        # openRoundKey is durable state, not one-off DOM bookkeeping -- a
        # fresh render() call (e.g. the app's 10s auto-refresh) must re-embed
        # the box in the same spot rather than silently closing it.
        wait_for_spa(page, spa_server)
        page.evaluate(SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        page.locator(".cell[data-round-key]").first.click()
        open_key = page.locator(".round-heat-box").get_attribute("data-round-key")

        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        boxes = page.locator(".round-heat-box")
        assert boxes.count() == 1
        assert boxes.get_attribute("data-round-key") == open_key

    def test_collapse_open_clears_the_box_on_next_render(self, page, spa_server):
        # Rounds.collapseOpen() is what index.html's selectHeatsCompetitor
        # calls alongside HeatCard.collapseAll() so an open box never leaks
        # across to a newly-selected competitor's grid.
        wait_for_spa(page, spa_server)
        page.evaluate(SETUP_JS)
        page.evaluate("() => { setScheduleHTML(Rounds.render('Test A')); }")
        page.locator(".cell[data-round-key]").first.click()
        assert page.locator(".round-heat-box").count() == 1

        page.evaluate("() => { Rounds.collapseOpen(); setScheduleHTML(Rounds.render('Test A')); }")
        assert page.locator(".round-heat-box").count() == 0


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

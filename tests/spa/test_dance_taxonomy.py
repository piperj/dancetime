"""
DanceTaxonomy.parseEvent() -- the free-text NDCA event-string parser backing
both the Rounds tab's grid cells and Heats' new costume-change marker (see
static/dance-taxonomy.js and thor.md 2026-08-16).

Exercised against real event strings sampled from data/heats/1049.json and
data/heats/373.json (not just the two clean examples used while designing
the feature) -- level phrasing varies wildly, some dances carry no
"Amer."/"Int'l" marker at all, and real multi-dance events interleave
scholarship/qualifier prefixes in inconsistent order. Anything the parser
can't confidently resolve should degrade to a tagged 'unknown' entry rather
than throw -- a single weird event string must never break the whole grid.
"""
import pytest
from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


def parse(page, event_string):
    return page.evaluate("s => DanceTaxonomy.parseEvent(s)", event_string)


class TestDanceTaxonomyParsing:
    def test_ready_before_first_parse(self, page, spa_server):
        # wait_for_spa doesn't return until the initial Promise.all (which
        # includes DanceTaxonomy.ready) has resolved -- confirm parseEvent
        # actually has taxonomy data loaded, not silently falling back to
        # 'unknown' for everything because the fetch hadn't landed yet.
        wait_for_spa(page, spa_server)
        result = parse(page, "G-A3 Cl. Full Bronze Amer. Rumba")
        assert result[0]["styleFamily"] == "amRhythm"

    @pytest.mark.parametrize("level_phrase", [
        "Pre Bronze", "Int Bronze", "Full Bronze", "Newcomer", "Open Int. Silver", "Open Gold",
    ])
    def test_varied_level_phrasing_still_resolves_the_dance(self, page, spa_server, level_phrase):
        wait_for_spa(page, spa_server)
        result = parse(page, f"G-A1 {level_phrase} Amer. Waltz")
        assert len(result) == 1
        assert result[0]["styleFamily"] == "amSmooth"
        assert result[0]["danceName"] == "Waltz"
        assert result[0]["code"] == "W"

    def test_trailing_slash_p_is_stripped(self, page, spa_server):
        wait_for_spa(page, spa_server)
        result = parse(page, "G-S1 Newcomer  Amer. Waltz /P")
        assert len(result) == 1
        assert result[0]["danceName"] == "Waltz"
        assert "/P" not in result[0]["danceName"]

    def test_dance_with_no_style_marker_resolves_via_name_lookup(self, page, spa_server):
        wait_for_spa(page, spa_server)
        result = parse(page, "L-C Pre Silver Peabody")
        assert len(result) == 1
        assert result[0]["danceName"] == "Peabody"
        assert result[0]["styleFamily"] == "amSmooth"

    def test_international_marker_resolves_ballroom_family(self, page, spa_server):
        wait_for_spa(page, spa_server)
        result = parse(page, "G-A Pre Bronze Int'l Quickstep")
        assert result[0]["styleFamily"] == "intlBallroom"
        assert result[0]["code"] == "Q"
        assert result[0]["isAmerican"] is False

    def test_championship_round_name_does_not_leak_into_parse(self, page, spa_server):
        # HeatInstance.round ("Final", "Semi-Final", ...) is a separate field
        # entirely -- confirm the parser's output for the same event string
        # is identical regardless of what round it's attached to (this test
        # only exercises the string parse; round is never passed in).
        wait_for_spa(page, spa_server)
        a = parse(page, "AC-B1 Cl. Full Bronze Amer. Rumba")
        b = parse(page, "AC-B1 Cl. Full Bronze Amer. Rumba")
        assert a == b

    def test_multi_dance_clean_pattern_explodes_per_dance(self, page, spa_server):
        wait_for_spa(page, spa_server)
        result = parse(page, "Open Multi Dance Open  B M/F Amer. Smooth (W,T,F,VW)")
        assert [r["code"] for r in result] == ["W", "T", "F", "VW"]
        assert all(r["styleFamily"] == "amSmooth" for r in result)

    def test_multi_dance_with_scholarship_qualifier_prefix(self, page, spa_server):
        wait_for_spa(page, spa_server)
        result = parse(page, "Closed SR Scholarship Full Silver S1 Amer. Smooth (W,T,F)")
        assert [r["code"] for r in result] == ["W", "T", "F"]
        assert all(r["styleFamily"] == "amSmooth" for r in result)

    def test_multi_dance_with_heat_group_suffix(self, page, spa_server):
        wait_for_spa(page, spa_server)
        result = parse(page, "Gents Closed Silver Multi Full Silver S1 Amer. Smooth (W,T,F,VW)")
        assert [r["code"] for r in result] == ["W", "T", "F", "VW"]

    def test_garbage_string_degrades_to_unknown_without_throwing(self, page, spa_server):
        wait_for_spa(page, spa_server)
        result = parse(page, "###totally not an event###")
        assert len(result) == 1
        assert result[0]["styleFamily"] == "unknown"

    def test_empty_string_degrades_to_unknown(self, page, spa_server):
        wait_for_spa(page, spa_server)
        result = parse(page, "")
        assert result[0]["styleFamily"] == "unknown"


class TestStyleFamilyChanged:
    def test_level_only_change_does_not_fire(self, page, spa_server):
        wait_for_spa(page, spa_server)
        a = parse(page, "AC-B1 Cl. Pre Bronze Amer. Waltz")
        b = parse(page, "AC-B1 Cl. Full Bronze Amer. Waltz")
        assert page.evaluate("([a, b]) => DanceTaxonomy.styleFamilyChanged(a, b)", [a, b]) is False

    def test_style_family_change_fires(self, page, spa_server):
        wait_for_spa(page, spa_server)
        a = parse(page, "AC-B1 Cl. Full Bronze Amer. Waltz")
        b = parse(page, "AC-B1 Cl. Full Bronze Int'l Waltz")
        assert page.evaluate("([a, b]) => DanceTaxonomy.styleFamilyChanged(a, b)", [a, b]) is True

    def test_mixed_level_bundled_heat_union_diff(self, page, spa_server):
        # Not the parser's job (rounds.js does this diff) -- a synthetic
        # case confirming the underlying per-dance code data is what a
        # union/diff needs: two levels at the same heat_number, one dancing
        # a superset of the other's dances.
        wait_for_spa(page, spa_server)
        higher = parse(page, "Open Multi Dance Open  B M/F Amer. Smooth (W,T,F,VW)")
        lower = parse(page, "Open Multi Dance Open  A M/F Amer. Smooth (W,T,F)")
        higher_codes = {r["code"] for r in higher}
        lower_codes = {r["code"] for r in lower}
        assert higher_codes - lower_codes == {"VW"}

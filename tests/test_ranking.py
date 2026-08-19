import json
import pytest

import ranking.elo as elo_module
from ranking.models import DanceResult
from ranking.parser import parse_results, _join_name, _extract_placement
from ranking.skill_rating import get_initial_ratings
from ranking.elo import EloCalculator
from ranking.elo_store import load_history, load_ratings, load_ratings_full, save_ratings, write_history_for_cyi
from ranking.writer import build_ranking_json, write_ranking_json


def _make_results_json(placements: list[tuple[str, str, int]]) -> dict:
    """Build minimal results JSON with one dance: [(competitor, partner, place)]."""
    competitors_data = []
    for comp, partner, place in placements:
        competitors_data.append({
            "Result": place,
            "Participants": [
                {"Name": comp.split()},
                {"Name": partner.split()},
            ],
        })
    return {
        "results": [
            {
                "_metadata": {"competitor_name": placements[0][0], "studio": "Fred Astaire"},
                "Events": [{
                    "ID": 10,
                    "Name": "Adult Full Silver Standard",
                    "Rounds": [{
                        "ID": 1,
                        "Name": "Final",
                        "Session_ID": 3,
                        "Dances": [{
                            "Dance_ID": 1,
                            "Dance_Name": "Waltz",
                            "Competitors": competitors_data,
                        }],
                    }],
                }],
            }
        ]
    }


class TestExtractPlacement:
    def test_plain_integer(self):
        assert _extract_placement({"Result": 3}) == 3

    def test_single_element_list(self):
        assert _extract_placement({"Result": ["7"]}) == 7

    def test_tie_result_list(self):
        # NDCA encodes ties as ["TIE", "TIE", "11"] — last element is the placement
        assert _extract_placement({"Result": ["TIE", "TIE", "11"]}) == 11

    def test_two_element_tie(self):
        assert _extract_placement({"Result": ["TIE", "4"]}) == 4

    def test_none_result_returns_none(self):
        assert _extract_placement({"Result": None}) is None

    def test_empty_list_returns_none(self):
        assert _extract_placement({"Result": []}) is None

    def test_circuit_place_fallback(self):
        assert _extract_placement({"Circuit": {"Place": "2"}}) == 2


class TestJoinName:
    def test_two_parts(self):
        assert _join_name(["Alice", "Smith"]) == "Alice Smith"

    def test_empty_list(self):
        assert _join_name([]) == "Unknown"

    def test_none(self):
        assert _join_name(None) == "Unknown"


class TestDanceResultParser:
    def test_parses_two_competitor_heat(self):
        data = _make_results_json([("Alice Smith", "Bob Jones", 1), ("Carol Doe", "Dan Roe", 2)])
        results = parse_results(data)
        assert len(results) == 1
        r = results[0]
        assert "Alice Smith" in r.competitors
        assert "Carol Doe" in r.competitors

    def test_deduplication_merges_competitors(self):
        data = {
            "results": [
                {
                    "_metadata": {"competitor_name": "Alice Smith", "studio": ""},
                    "Events": [{
                        "ID": 10, "Name": "Silver Standard",
                        "Rounds": [{"ID": 1, "Name": "Final", "Session_ID": 1,
                            "Dances": [{"Dance_ID": 1, "Dance_Name": "Waltz",
                                "Competitors": [{"Result": 1, "Participants": [{"Name": ["Alice", "Smith"]}, {"Name": ["Bob", "Jones"]}]}]}]}],
                    }],
                },
                {
                    "_metadata": {"competitor_name": "Carol Doe", "studio": ""},
                    "Events": [{
                        "ID": 10, "Name": "Silver Standard",
                        "Rounds": [{"ID": 1, "Name": "Final", "Session_ID": 1,
                            "Dances": [{"Dance_ID": 1, "Dance_Name": "Waltz",
                                "Competitors": [{"Result": 2, "Participants": [{"Name": ["Carol", "Doe"]}, {"Name": ["Dan", "Roe"]}]}]}]}],
                    }],
                },
            ]
        }
        results = parse_results(data)
        assert len(results) == 1
        assert len(results[0].competitors) == 4

    def test_placements_extracted(self):
        data = _make_results_json([("Alice Smith", "Bob Jones", 1), ("Carol Doe", "Dan Roe", 2)])
        results = parse_results(data)
        assert results[0].placements["Alice Smith"] == 1
        assert results[0].placements["Carol Doe"] == 2

    def test_only_contested_returned(self):
        data = {
            "results": [{
                "_metadata": {"competitor_name": "Alice Smith", "studio": ""},
                "Events": [{"ID": 1, "Name": "Silver", "Rounds": [{"ID": 1, "Name": "Final", "Session_ID": 1,
                    "Dances": [{"Dance_ID": 1, "Dance_Name": "Waltz",
                        "Competitors": [{"Result": 1, "Participants": [{"Name": ["Alice", "Smith"]}]}]}]}]}],
            }]
        }
        results = parse_results(data)
        assert len(results) == 0

    def test_each_dance_processed_once(self):
        # The NDCA API returns one result entry per registered competitor, so the
        # same heat appears multiple times in the raw JSON. parse_results must
        # deduplicate them into a single DanceResult — otherwise process_heat would
        # be called twice for the same matchup and shift ELO ratings twice.
        dance = {"Dance_ID": 1, "Dance_Name": "Waltz", "Competitors": [
            {"Result": 1, "Participants": [{"Name": ["Johan"]}, {"Name": ["Kristina"]}]},
            {"Result": 2, "Participants": [{"Name": ["Jennifer"]}, {"Name": ["Ivan"]}]},
        ]}
        round_ = {"ID": 1, "Name": "Final", "Session_ID": 1, "Dances": [dance]}
        event = {"ID": 10, "Name": "Adult Full Silver Standard", "Rounds": [round_]}

        def _entry(name):
            return {"_metadata": {"competitor_name": name, "studio": ""}, "Events": [event]}

        data = {"results": [_entry("Johan"), _entry("Kristina")]}
        results = parse_results(data)
        assert len(results) == 1
        assert len(results[0].competitors) == 4

    def test_results_sorted_by_sort_key(self):
        data = {
            "results": [{
                "_metadata": {"competitor_name": "Alice", "studio": ""},
                "Events": [
                    {"ID": 1, "Name": "Event A", "Rounds": [{"ID": 1, "Name": "Final", "Session_ID": 2,
                        "Dances": [{"Dance_ID": 1, "Dance_Name": "Waltz",
                            "Competitors": [{"Result": 1, "Participants": [{"Name": ["A"]}, {"Name": ["B"]}]},
                                            {"Result": 2, "Participants": [{"Name": ["C"]}, {"Name": ["D"]}]}]}]}]},
                    {"ID": 2, "Name": "Event B", "Rounds": [{"ID": 1, "Name": "Final", "Session_ID": 1,
                        "Dances": [{"Dance_ID": 1, "Dance_Name": "Waltz",
                            "Competitors": [{"Result": 1, "Participants": [{"Name": ["E"]}, {"Name": ["F"]}]},
                                            {"Result": 2, "Participants": [{"Name": ["G"]}, {"Name": ["H"]}]}]}]}]},
                ],
            }]
        }
        results = parse_results(data)
        assert results[0].session_id <= results[-1].session_id


class TestSkillRating:
    def test_initial_rating_uses_prior(self):
        data = _make_results_json([("Alice Smith", "Bob Jones", 1), ("Carol Doe", "Dan Roe", 2)])
        results = parse_results(data)
        prior = {"Alice Smith": 1650.0}
        ratings = get_initial_ratings(results, prior)
        assert ratings["Alice Smith"] == 1650.0

    def test_initial_rating_uses_skill_offset_for_new(self):
        # fixture event is "Adult Full Silver Standard" → silver bucket → offset 0
        data = _make_results_json([("Alice Smith", "Bob Jones", 1), ("Carol Doe", "Dan Roe", 2)])
        results = parse_results(data)
        ratings = get_initial_ratings(results, {})
        assert ratings["Alice Smith"] == 1500.0


class TestEloCalculator:
    def _make_result(self, competitors: list[tuple[str, str, int]]) -> DanceResult:
        comps = [c for c, p, _ in competitors]
        partners = {}
        placements = {}
        for c, p, place in competitors:
            partners[c] = p
            partners[p] = c
            placements[c] = place
            placements[p] = place
            comps.append(p)
        return DanceResult(
            event_id=1, event_name="Test", round_id=1, round_name="Final",
            dance_id=1, dance_name="Waltz", session_id=1, heat_number=1, time="",
            competitors=comps, partners=partners, placements=placements,
        )

    def test_winner_gains_rating(self):
        calc = EloCalculator()
        calc.initialize({"Alice": 1500.0, "Bob": 1500.0, "Carol": 1500.0, "Dan": 1500.0})
        result = self._make_result([("Alice", "Bob", 1), ("Carol", "Dan", 2)])
        calc.process_heat(result)
        assert calc.get_rating("Alice") > 1500.0
        assert calc.get_rating("Carol") < 1500.0

    def test_equal_ratings_zero_sum(self):
        calc = EloCalculator()
        calc.initialize({"Alice": 1500.0, "Bob": 1500.0, "Carol": 1500.0, "Dan": 1500.0})
        result = self._make_result([("Alice", "Bob", 1), ("Carol", "Dan", 2)])
        calc.process_heat(result)
        total_before = 1500.0 * 4
        total_after = sum(calc.ratings.values())
        assert abs(total_after - total_before) < 0.01

    def test_no_op_for_uncontested(self):
        calc = EloCalculator()
        calc.initialize({"Alice": 1600.0})
        r = DanceResult(
            event_id=1, event_name="T", round_id=1, round_name="F",
            dance_id=1, dance_name="W", session_id=1, heat_number=1, time="",
            competitors=["Alice"], partners={}, placements={"Alice": 1},
        )
        calc.process_heat(r)
        assert calc.get_rating("Alice") == 1600.0

    def test_ratings_copy_not_reference(self):
        calc = EloCalculator()
        calc.initialize({"A": 1500.0})
        r1 = calc.ratings
        r1["A"] = 9999.0
        assert calc.get_rating("A") == 1500.0

    def test_process_heat_returns_before_after(self):
        calc = EloCalculator()
        calc.initialize({"Alice": 1500.0, "Bob": 1500.0, "Carol": 1500.0, "Dan": 1500.0})
        result = self._make_result([("Alice", "Bob", 1), ("Carol", "Dan", 2)])
        changes = calc.process_heat(result)
        assert set(changes.keys()) == {"Alice", "Bob", "Carol", "Dan"}
        for competitor, (before, after) in changes.items():
            assert before == 1500.0
            assert after == calc.get_rating(competitor)
            assert before != after

    def test_process_heat_returns_empty_for_uncontested(self):
        calc = EloCalculator()
        calc.initialize({"Alice": 1600.0})
        r = DanceResult(
            event_id=1, event_name="T", round_id=1, round_name="F",
            dance_id=1, dance_name="W", session_id=1, heat_number=1, time="",
            competitors=["Alice"], partners={}, placements={"Alice": 1},
        )
        assert calc.process_heat(r) == {}

    def test_solo_couple_no_elo_change(self):
        # Single couple with no opponent — partners must not be compared against each other
        calc = EloCalculator()
        calc.initialize({"Johan": 1650.0, "Kristina": 1500.0})
        r = DanceResult(
            event_id=1, event_name="T", round_id=1, round_name="Final",
            dance_id=1, dance_name="Waltz", session_id=1, heat_number=1, time="",
            competitors=["Johan", "Kristina"],
            partners={"Johan": "Kristina", "Kristina": "Johan"},
            placements={"Johan": 1, "Kristina": 1},
        )
        assert calc.process_heat(r) == {}
        assert calc.get_rating("Johan") == 1650.0
        assert calc.get_rating("Kristina") == 1500.0

    def test_partners_not_compared_in_multi_couple_heat(self):
        # Three couples: partners within each couple must not affect each other's ELO
        calc = EloCalculator()
        calc.initialize({"A": 1500.0, "B": 1500.0, "C": 1500.0, "D": 1500.0, "E": 1500.0, "F": 1500.0})
        result = self._make_result([("A", "B", 1), ("C", "D", 2), ("E", "F", 3)])
        calc.process_heat(result)
        # A and B won — both gain; E and F lost — both lose
        assert calc.get_rating("A") > 1500.0
        assert calc.get_rating("B") > 1500.0
        assert calc.get_rating("E") < 1500.0
        assert calc.get_rating("F") < 1500.0

    def test_weaker_partner_gets_larger_share(self):
        # Alice (1600) is the stronger partner; Bob (1300) is weaker.
        # Both win. Bob should receive more of the couple's delta than Alice.
        calc = EloCalculator()
        calc.initialize({"Alice": 1600.0, "Bob": 1300.0, "Carol": 1500.0, "Dan": 1500.0})
        result = self._make_result([("Alice", "Bob", 1), ("Carol", "Dan", 2)])
        calc.process_heat(result)
        delta_alice = calc.get_rating("Alice") - 1600.0
        delta_bob = calc.get_rating("Bob") - 1300.0
        assert delta_alice > 0
        assert delta_bob > 0
        assert delta_bob > delta_alice

    def test_base_50_gives_equal_shares(self):
        # Setting PARTNER_WEIGHT_BASE=0.50 collapses the adaptive term to zero,
        # giving every couple a 50/50 split regardless of rating gap.
        original = elo_module.PARTNER_WEIGHT_BASE
        elo_module.PARTNER_WEIGHT_BASE = 0.50
        try:
            calc = EloCalculator()
            calc.initialize({"Alice": 1600.0, "Bob": 1300.0, "Carol": 1500.0, "Dan": 1500.0})
            result = self._make_result([("Alice", "Bob", 1), ("Carol", "Dan", 2)])
            calc.process_heat(result)
            delta_alice = calc.get_rating("Alice") - 1600.0
            delta_bob = calc.get_rating("Bob") - 1300.0
            assert abs(delta_alice - delta_bob) < 0.01
        finally:
            elo_module.PARTNER_WEIGHT_BASE = original


class TestEloStore:
    def test_load_returns_empty_when_no_file(self, tmp_path):
        assert load_ratings(tmp_path) == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        save_ratings({"Alice": 1620.5}, {"Alice": 1}, 373, tmp_path)
        loaded = load_ratings(tmp_path)
        assert loaded["Alice"] == 1620.5

    def test_save_stores_comp_counts(self, tmp_path):
        save_ratings({"Alice": 1620.5}, {"Alice": 3}, 373, tmp_path)
        raw = json.loads((tmp_path / "elo_ratings.json").read_text())
        assert raw["ratings"]["Alice"]["num_comps"] == 3
        assert raw["ratings"]["Alice"]["last_cyi"] == 373

    def test_load_history_returns_empty_when_no_file(self, tmp_path):
        assert load_history(tmp_path, 422) == []

    def test_write_and_load_history_roundtrip(self, tmp_path):
        entries = [{"event_name": "Test", "round_name": "Final", "dance_name": "Waltz",
                    "competitor": "Alice", "partner": "Bob",
                    "elo_before": 1500.0, "elo_after": 1512.5}]
        write_history_for_cyi(422, entries, tmp_path)
        loaded = load_history(tmp_path, 422)
        assert loaded[0]["competitor"] == "Alice"
        assert loaded[0]["elo_after"] == 1512.5

    def test_load_ratings_full_returns_empty_when_no_file(self, tmp_path):
        result = load_ratings_full(tmp_path)
        assert result == {"last_cyi": None, "ratings": {}}

    def test_save_ratings_refuses_truncate_to_empty(self, tmp_path):
        save_ratings({"Alice": 1620.5}, {"Alice": 3}, 373, tmp_path)
        with pytest.raises(RuntimeError, match="refused to truncate"):
            save_ratings({}, {}, 422, tmp_path)
        # original file untouched
        raw = json.loads((tmp_path / "elo_ratings.json").read_text())
        assert raw["ratings"]["Alice"]["elo"] == 1620.5

    def test_save_ratings_allows_empty_when_no_prior_file(self, tmp_path):
        # First-ever run with zero competitors is legitimate; no file to clobber.
        save_ratings({}, {}, 0, tmp_path)
        assert (tmp_path / "elo_ratings.json").exists()

    def test_write_history_overwrites_fully(self, tmp_path):
        write_history_for_cyi(422, [{"elo_after": 1510.0}], tmp_path)
        write_history_for_cyi(422, [{"elo_after": 1520.0}], tmp_path)
        loaded = load_history(tmp_path, 422)
        assert loaded[0]["elo_after"] == 1520.0

    def test_write_history_preserves_other_cyis(self, tmp_path):
        write_history_for_cyi(422, [{"competitor": "Alice"}], tmp_path)
        write_history_for_cyi(904, [{"competitor": "Bob"}], tmp_path)
        assert load_history(tmp_path, 422)[0]["competitor"] == "Alice"
        assert load_history(tmp_path, 904)[0]["competitor"] == "Bob"


class TestRankingWriter:
    def _minimal_data(self, cyi=373):
        return build_ranking_json(
            cyi=cyi,
            competition_info={"Name": "Test Ball", "StartDate": "2026-01-29", "EndDate": "2026-02-01", "Location": "Columbus"},
            dance_results=[],
            final_ratings={"Alice": 1550.0, "Bob": 1480.0},
            initial_ratings={"Alice": 1500.0, "Bob": 1500.0},
            competitor_studios={"Alice": "Fred Astaire"},
        )

    def test_top_level_keys(self):
        data = self._minimal_data()
        for key in ("meta", "couples", "competitors", "studios", "competitor_studios"):
            assert key in data

    def test_couples_sorted_by_elo(self):
        data = self._minimal_data()
        couples = data["couples"]
        assert couples[0]["competitor"] == "Alice"
        assert couples[0]["rank"] == 1

    def test_write_creates_file(self, tmp_path):
        data = self._minimal_data()
        path = write_ranking_json(data, tmp_path)
        assert path.exists()
        assert path == tmp_path / "ranking" / "373.json"

    def test_competitor_with_multiple_partners_gets_a_row_per_partnership(self):
        # Regression test: a competitor who dances with more than one partner in
        # the same competition (e.g. different divisions) used to collapse to a
        # single leaderboard row keyed by whichever partner was processed last,
        # silently dropping the other partnership (and its contested-opponent
        # stats) from the Ladder entirely.
        heat_with_yuriy = DanceResult(
            event_id=1, event_name="Silver Standard", round_id=1, round_name="Final",
            dance_id=1, dance_name="Waltz", session_id=1, heat_number=1, time="",
            competitors=["Helen", "Yuriy", "Ann", "Bob"],
            partners={"Helen": "Yuriy", "Yuriy": "Helen", "Ann": "Bob", "Bob": "Ann"},
            placements={"Helen": 1, "Yuriy": 1, "Ann": 2, "Bob": 2},
        )
        heat_with_johan = DanceResult(
            event_id=2, event_name="Bronze Standard", round_id=1, round_name="Final",
            dance_id=2, dance_name="Tango", session_id=1, heat_number=2, time="",
            competitors=["Helen", "Johan", "Cara", "Dan"],
            partners={"Helen": "Johan", "Johan": "Helen", "Cara": "Dan", "Dan": "Cara"},
            placements={"Helen": 2, "Johan": 2, "Cara": 1, "Dan": 1},
        )

        data = build_ranking_json(
            cyi=422,
            competition_info={"Name": "IGB", "StartDate": "2026-07-23", "EndDate": "2026-07-26", "Location": "NYC"},
            dance_results=[heat_with_yuriy, heat_with_johan],
            final_ratings={"Helen": 1300.0, "Yuriy": 1600.0, "Johan": 1290.0,
                            "Ann": 1400.0, "Bob": 1400.0, "Cara": 1500.0, "Dan": 1500.0},
            initial_ratings={},
            competitor_studios={},
        )

        # dedup_couples collapses the mirrored A&B/B&A rows down to one
        # representative per *partnership*, so "Helen" may show up as either
        # the "competitor" or the "partner" field depending on elo tie-break —
        # look up by unordered pair, the same way the frontend's coupleKey does.
        couples = data["couples"]
        helen_rows = {
            frozenset((c["competitor"], c["partner"])): c
            for c in couples if "Helen" in (c["competitor"], c["partner"])
        }

        assert set(helen_rows) == {frozenset({"Helen", "Yuriy"}), frozenset({"Helen", "Johan"})}
        for pair, row in helen_rows.items():
            assert row["heats_processed"] == 1, pair
            assert row["num_opponents"] == 2, pair

    def test_multiple_partners_get_distinct_couple_blended_elo(self):
        # Regression test: the Ladder used to stamp every partnership row with
        # the competitor's raw individual rating, so a person's different
        # couples all showed the identical ELO/delta (e.g. "Sarah & Rasheed"
        # and "Sarah & Yuriy" both showing 1914/+196). Each row should instead
        # show a couple-blended rating that reflects *that* partner's rating.
        data = build_ranking_json(
            cyi=1030,
            competition_info={"Name": "Cal Star Ball", "StartDate": "2026-08-01", "EndDate": "2026-08-03", "Location": "LA"},
            dance_results=[
                DanceResult(
                    event_id=1, event_name="Bronze Latin", round_id=1, round_name="Final",
                    dance_id=1, dance_name="Cha Cha", session_id=1, heat_number=1, time="",
                    competitors=["Sarah", "Rasheed", "Ann", "Bob"],
                    partners={"Sarah": "Rasheed", "Rasheed": "Sarah", "Ann": "Bob", "Bob": "Ann"},
                    placements={"Sarah": 1, "Rasheed": 1, "Ann": 2, "Bob": 2},
                ),
                DanceResult(
                    event_id=2, event_name="Bronze Rhythm", round_id=1, round_name="Final",
                    dance_id=2, dance_name="Rumba", session_id=1, heat_number=2, time="",
                    competitors=["Sarah", "Yuriy", "Cara", "Dan"],
                    partners={"Sarah": "Yuriy", "Yuriy": "Sarah", "Cara": "Dan", "Dan": "Cara"},
                    placements={"Sarah": 1, "Yuriy": 1, "Cara": 2, "Dan": 2},
                ),
            ],
            final_ratings={"Sarah": 1914.0, "Rasheed": 1200.0, "Yuriy": 1900.0,
                            "Ann": 1400.0, "Bob": 1400.0, "Cara": 1500.0, "Dan": 1500.0},
            initial_ratings={},
            competitor_studios={},
        )

        sarah_rows = {
            frozenset((c["competitor"], c["partner"])): c
            for c in data["couples"] if "Sarah" in (c["competitor"], c["partner"])
        }
        rasheed_row = sarah_rows[frozenset({"Sarah", "Rasheed"})]
        yuriy_row = sarah_rows[frozenset({"Sarah", "Yuriy"})]

        assert rasheed_row["elo"] != yuriy_row["elo"]
        # Both blended ratings should sit strictly between the two individual
        # ratings involved (never equal to Sarah's bare individual rating).
        assert 1200.0 < rasheed_row["elo"] < 1914.0
        assert 1900.0 < yuriy_row["elo"] < 1914.0

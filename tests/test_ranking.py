import json
import pytest

from ranking.models import DanceResult
from ranking.parser import parse_results, _join_name, _extract_placement
from ranking.skill_rating import get_initial_ratings
from ranking.elo import EloCalculator
from ranking.clusters import build_graph, assign_leaderboards
from ranking.elo_store import compute_deltas, load_history, load_ratings, save_ratings, write_history
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
        # A and B won — both gain; E and F lost — both lose; C and D are in the middle
        assert calc.get_rating("A") > 1500.0
        assert calc.get_rating("B") > 1500.0
        assert calc.get_rating("E") < 1500.0
        assert calc.get_rating("F") < 1500.0
        # Partners within a couple must move identically (same delta applied to both)
        assert abs(calc.get_rating("A") - calc.get_rating("B")) < 0.01
        assert abs(calc.get_rating("C") - calc.get_rating("D")) < 0.01
        assert abs(calc.get_rating("E") - calc.get_rating("F")) < 0.01


class TestClusters:
    def _make_results(self, groups: list[list[str]]) -> list[DanceResult]:
        results = []
        for i, group in enumerate(groups):
            results.append(DanceResult(
                event_id=i, event_name="T", round_id=1, round_name="F",
                dance_id=1, dance_name="W", session_id=1, heat_number=i, time="",
                competitors=group, partners={}, placements={c: j+1 for j, c in enumerate(group)},
            ))
        return results

    def test_fully_connected_group_gets_label_A(self):
        results = self._make_results([["A", "B", "C", "D", "E"]])
        graph = build_graph(results)
        assignments = assign_leaderboards(graph)
        assert all(v == "A" for v in assignments.values())

    def test_isolated_node_gets_not_rated(self):
        results = self._make_results([["A", "B"], ["C"]])
        graph = build_graph(results)
        assignments = assign_leaderboards(graph)
        assert assignments.get("C") == "Not Rated"

    def test_two_separate_clusters(self):
        results = self._make_results([["A", "B"], ["C", "D"]])
        graph = build_graph(results)
        assignments = assign_leaderboards(graph)
        assert assignments["A"] == assignments["B"]
        assert assignments["C"] == assignments["D"]
        assert assignments["A"] != assignments["C"]


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

    def test_compute_deltas_positive(self):
        deltas = compute_deltas({"Alice": 1550.0}, {"Alice": 1500.0})
        assert deltas["Alice"] == "+50.0"

    def test_compute_deltas_negative(self):
        deltas = compute_deltas({"Alice": 1450.0}, {"Alice": 1500.0})
        assert deltas["Alice"] == "-50.0"

    def test_compute_deltas_new_competitor(self):
        deltas = compute_deltas({"Alice": 1500.0}, {})
        assert deltas["Alice"] == "+0.0"

    def test_load_history_returns_empty_when_no_file(self, tmp_path):
        assert load_history(tmp_path) == {}

    def test_write_and_load_history_roundtrip(self, tmp_path):
        entries = [{"event_name": "Test", "round_name": "Final", "dance_name": "Waltz",
                    "competitor": "Alice", "partner": "Bob",
                    "elo_before": 1500.0, "elo_after": 1512.5}]
        write_history({"422": entries}, tmp_path)
        loaded = load_history(tmp_path)
        assert "422" in loaded
        assert loaded["422"][0]["competitor"] == "Alice"
        assert loaded["422"][0]["elo_after"] == 1512.5

    def test_write_history_overwrites_fully(self, tmp_path):
        write_history({"422": [{"elo_after": 1510.0}]}, tmp_path)
        write_history({"422": [{"elo_after": 1520.0}]}, tmp_path)
        loaded = load_history(tmp_path)
        assert loaded["422"][0]["elo_after"] == 1520.0

    def test_write_history_preserves_all_cyis(self, tmp_path):
        write_history({
            "422": [{"competitor": "Alice"}],
            "904": [{"competitor": "Bob"}],
        }, tmp_path)
        loaded = load_history(tmp_path)
        assert "422" in loaded
        assert "904" in loaded


class TestRankingWriter:
    def _minimal_data(self, cyi=373):
        return build_ranking_json(
            cyi=cyi,
            competition_info={"Name": "Test Ball", "StartDate": "2026-01-29", "EndDate": "2026-02-01", "Location": "Columbus"},
            dance_results=[],
            final_ratings={"Alice": 1550.0, "Bob": 1480.0},
            initial_ratings={"Alice": 1500.0, "Bob": 1500.0},
            assignments={"Alice": "A", "Bob": "A"},
            competitor_studios={"Alice": "Fred Astaire"},
            elo_deltas={"Alice": "+50.0", "Bob": "-20.0"},
            elo_params={"k_factor": 32.0, "partner_weight": 0.3},
        )

    def test_top_level_keys(self):
        data = self._minimal_data()
        for key in ("meta", "leaderboards", "competitors", "studios", "competitor_studios"):
            assert key in data

    def test_leaderboard_sorted_by_elo(self):
        data = self._minimal_data()
        couples = data["leaderboards"]["A"]["couples"]
        assert couples[0]["competitor"] == "Alice"
        assert couples[0]["rank"] == 1

    def test_write_creates_file(self, tmp_path):
        data = self._minimal_data()
        path = write_ranking_json(data, tmp_path)
        assert path.exists()
        assert path.name == "ranking_373.json"

import pytest

from ranking.models import DanceResult
from ranking.parser import parse_results, _join_name
from ranking.skill_rating import parse_skill_category, parse_age_division, get_initial_ratings, SKILL_OFFSETS, AGE_OFFSETS
from ranking.elo import EloCalculator
from ranking.clusters import build_graph, assign_leaderboards
from ranking.elo_store import compute_deltas, load_ratings, save_ratings
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
    def test_parse_full_silver(self):
        assert parse_skill_category("Adult Full Silver Standard") == "full silver"

    def test_parse_open(self):
        assert parse_skill_category("Open Professional Smooth") == "open"

    def test_parse_returns_none_for_unknown(self):
        assert parse_skill_category("Some Unknown Event") is None

    def test_parse_age_adult(self):
        assert parse_age_division("Adult B1 Full Silver") == "adult"

    def test_parse_age_senior(self):
        assert parse_age_division("Senior II Full Gold Standard") == "senior ii"

    def test_initial_rating_uses_prior(self):
        data = _make_results_json([("Alice Smith", "Bob Jones", 1), ("Carol Doe", "Dan Roe", 2)])
        results = parse_results(data)
        prior = {"Alice Smith": {"elo": 1650.0, "num_comps": 3}}
        ratings = get_initial_ratings(results, prior)
        assert ratings["Alice Smith"] == 1650.0

    def test_initial_rating_uses_skill_offset_for_new(self):
        data = _make_results_json([("Alice Smith", "Bob Jones", 1), ("Carol Doe", "Dan Roe", 2)])
        results = parse_results(data)
        ratings = get_initial_ratings(results, {})
        assert ratings["Alice Smith"] == 1500.0 + SKILL_OFFSETS["full silver"]


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
        save_ratings({"Alice": 1620.5}, {}, 373, tmp_path)
        loaded = load_ratings(tmp_path)
        assert loaded["Alice"]["elo"] == 1620.5
        assert loaded["Alice"]["last_cyi"] == 373

    def test_save_increments_num_comps(self, tmp_path):
        prior = {"Alice": {"elo": 1600.0, "num_comps": 2, "last_cyi": 372}}
        save_ratings({"Alice": 1620.5}, prior, 373, tmp_path)
        loaded = load_ratings(tmp_path)
        assert loaded["Alice"]["num_comps"] == 3

    def test_compute_deltas_positive(self):
        deltas = compute_deltas({"Alice": 1550.0}, {"Alice": {"elo": 1500.0}})
        assert deltas["Alice"] == "+50.0"

    def test_compute_deltas_negative(self):
        deltas = compute_deltas({"Alice": 1450.0}, {"Alice": {"elo": 1500.0}})
        assert deltas["Alice"] == "-50.0"

    def test_compute_deltas_new_competitor(self):
        deltas = compute_deltas({"Alice": 1500.0}, {})
        assert deltas["Alice"] == "+0.0"


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

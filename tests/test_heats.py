from datetime import datetime

import pytest

from heats.session_names import infer_session_names, parse_round_time
from heats.parser import parse_heatlists, HeatInstance, HeatEntry
from heats.matchups import compute_top_matchups
from heats.writer import build_heats_json, write_heats_json


def _make_heatlists(entries_per_competitor):
    """entries_per_competitor: list of (competitor_name, studio, heat_entry_list)"""
    result = []
    for name, studio, entries in entries_per_competitor:
        result.append({
            "_metadata": {"competitor_name": name, "studio": studio},
            "Entries": entries,
        })
    return result


def _round_entry(session, time_str, heat="42", event="Adult Full Silver Standard", round_name="Final", bib="100"):
    return {
        "Event_Name": event,
        "Heat": heat,
        "Bib": bib,
        "Rounds": [{"Round_Name": round_name, "Session": session, "Round_Time": time_str, "Complete": 1}],
    }


def _entry(partner_name, events):
    return {
        "Type": "Partner",
        "Couple_ID": 1,
        "Participants": [{"Name": partner_name.split()}],
        "Events": events,
    }


class TestParseRoundTime:
    def test_full_format(self):
        t = parse_round_time("1/23/2026 12:10:42 PM")
        assert t is not None
        assert t.hour == 12
        assert t.minute == 10

    def test_short_format(self):
        t = parse_round_time("1/30/2026 9:00 AM")
        assert t is not None
        assert t.hour == 9

    def test_iso_format(self):
        t = parse_round_time("2026-01-30T09:00:00")
        assert t is not None

    def test_invalid_returns_none(self):
        assert parse_round_time("not a date") is None


class TestSessionNames:
    def test_morning(self):
        hl = _make_heatlists([("Alice", "S", [_entry("Bob Jones", [_round_entry("1", "1/30/2026 9:00 AM")])])])
        names = infer_session_names(hl)
        assert "Morning" in names["1"]

    def test_afternoon(self):
        hl = _make_heatlists([("Alice", "S", [_entry("Bob Jones", [_round_entry("2", "1/30/2026 2:00 PM")])])])
        names = infer_session_names(hl)
        assert "Afternoon" in names["2"]

    def test_evening(self):
        hl = _make_heatlists([("Alice", "S", [_entry("Bob Jones", [_round_entry("3", "1/30/2026 7:30 PM")])])])
        names = infer_session_names(hl)
        assert "Evening" in names["3"]

    def test_uses_earliest_time_in_session(self):
        hl = _make_heatlists([("Alice", "S", [
            _entry("Bob Jones", [_round_entry("1", "1/30/2026 8:00 PM")]),
            _entry("Carol Doe", [_round_entry("1", "1/30/2026 9:00 AM")]),
        ])])
        names = infer_session_names(hl)
        assert "Morning" in names["1"]

    def test_multiple_sessions(self):
        hl = _make_heatlists([("Alice", "S", [
            _entry("Bob Jones", [_round_entry("01", "1/29/2026 9:00 AM")]),
            _entry("Carol Doe", [_round_entry("02", "1/30/2026 7:00 PM")]),
        ])])
        names = infer_session_names(hl)
        assert len(names) == 2


class TestHeatParser:
    def _make_two_competitor_heatlists(self):
        return _make_heatlists([
            ("Alice Smith", "Fred Astaire", [_entry("Bob Jones", [_round_entry("02", "1/30/2026 12:10:42 PM", bib="100")])]),
            ("Carol Doe", "Arthur Murray", [_entry("Dan Roe", [_round_entry("02", "1/30/2026 12:10:42 PM", bib="200")])]),
        ])

    def _make_results(self):
        return [
            {
                "Events": [{
                    "Name": "Adult Full Silver Standard",
                    "Rounds": [{"Name": "Final", "Dances": [{
                        "Dance_ID": 1, "Dance_Name": "Waltz",
                        "Competitors": [
                            {"Result": 1, "Participants": [{"Name": ["Alice", "Smith"]}, {"Name": ["Bob", "Jones"]}]},
                            {"Result": 2, "Participants": [{"Name": ["Carol", "Doe"]}, {"Name": ["Dan", "Roe"]}]},
                        ],
                    }]}],
                }],
            }
        ]

    def test_deduplicates_into_one_heat_instance(self):
        hl = self._make_two_competitor_heatlists()
        instances = parse_heatlists(hl, self._make_results(), {"02": "Thursday Evening"})
        assert len(instances) == 1

    def test_heat_instance_has_two_entries(self):
        hl = self._make_two_competitor_heatlists()
        instances = parse_heatlists(hl, self._make_results(), {"02": "Thursday Evening"})
        assert len(instances[0].entries) == 2

    def test_session_name_applied(self):
        hl = self._make_two_competitor_heatlists()
        instances = parse_heatlists(hl, self._make_results(), {"02": "Thursday Evening"})
        assert instances[0].session_name == "Thursday Evening"

    def test_result_matched(self):
        hl = self._make_two_competitor_heatlists()
        instances = parse_heatlists(hl, self._make_results(), {"02": "Thursday Evening"})
        alice = next(e for e in instances[0].entries if e.competitor1 == "Alice Smith")
        assert alice.result == "1"

    def test_couple_name_formed(self):
        hl = self._make_two_competitor_heatlists()
        instances = parse_heatlists(hl, self._make_results(), {"02": "Thursday Evening"})
        alice = next(e for e in instances[0].entries if e.competitor1 == "Alice Smith")
        assert alice.couple == "Alice Smith & Bob Jones"


class TestMatchups:
    def _make_instances(self):
        def entry(comp1, comp2, bib1, bib2):
            return HeatEntry(couple=f"{comp1} & {comp2}", competitor1=comp1, competitor2=comp2,
                             bib=bib1, studio="", event="", result="")

        instances = []
        for i in range(3):
            inst = HeatInstance(key=f"inst_{i}", heat_number=str(i), session="1",
                                session_name="Friday Morning", time="", round_name="Final")
            inst.entries = [entry("Alice", "Bob", "100", "101"), entry("Carol", "Dan", "200", "201")]
            instances.append(inst)

        single = HeatInstance(key="inst_3", heat_number="3", session="1",
                              session_name="Friday Morning", time="", round_name="Final")
        single.entries = [entry("Alice", "Bob", "100", "101"), entry("Eve", "Frank", "300", "301")]
        instances.append(single)
        return instances

    def test_top_matchup_is_carol(self):
        matchups = compute_top_matchups(self._make_instances())
        assert matchups["Alice"][0]["opponent_couple"] == "Carol & Dan"
        assert matchups["Alice"][0]["count"] == 3

    def test_second_matchup_is_eve(self):
        matchups = compute_top_matchups(self._make_instances())
        assert matchups["Alice"][1]["opponent_couple"] == "Eve & Frank"

    def test_top_n_limit(self):
        matchups = compute_top_matchups(self._make_instances(), top_n=1)
        assert len(matchups["Alice"]) == 1


class TestWriter:
    def test_top_level_keys(self):
        data = build_heats_json(999, {"Competition_Name": "Test", "Date_Range": "Jan 29", "Location": ""}, [], {})
        for key in ("meta", "sessions", "heats", "competitors", "studios",
                    "competitor_studios", "competitor_heats", "top_matchups"):
            assert key in data

    def test_meta_cyi(self):
        data = build_heats_json(999, {"Competition_Name": "T", "Date_Range": "", "Location": ""}, [], {})
        assert data["meta"]["cyi"] == 999

    def test_write_creates_file(self, tmp_path):
        data = build_heats_json(999, {"Competition_Name": "T", "Date_Range": "", "Location": ""}, [], {})
        path = write_heats_json(data, tmp_path)
        assert path.exists()
        assert path.name == "heats_999.json"

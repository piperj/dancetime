import json
from datetime import datetime
from pathlib import Path

import pytest

from heats.session_names import infer_session_names, parse_round_time
from heats.parser import parse_heatlists, HeatInstance, HeatEntry
from heats.matchups import compute_top_matchups
from heats.writer import build_heats_json, write_heats_json

HEATS_JSON = Path(__file__).parent.parent / "data" / "heats_373.json"


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


def _couple_heatlists(pairs, time="1/30/2026 12:10:42 PM", session="01"):
    """Build heatlists where each person in pairs has their own API entry."""
    hl = []
    for c1, c2, studio in pairs:
        for name, partner in [(c1, c2), (c2, c1)]:
            hl.append({
                "_metadata": {"competitor_name": name, "studio": studio},
                "Entries": [_entry(partner, [_round_entry(session, time)])],
            })
    return hl


class TestCoupleDeduplication:
    def test_mirrored_pair_produces_one_entry(self):
        hl = _couple_heatlists([("Alice Smith", "Bob Jones", "Studio A")])
        instances = parse_heatlists(hl, [], {})
        assert len(instances) == 1
        assert len(instances[0].entries) == 1

    def test_two_couples_same_heat_produce_two_entries(self):
        hl = _couple_heatlists([
            ("Alice Smith", "Bob Jones", "Studio A"),
            ("Carol Doe", "Dan Roe", "Studio B"),
        ])
        instances = parse_heatlists(hl, [], {})
        assert len(instances) == 1
        assert len(instances[0].entries) == 2

    def test_both_partners_in_competitors_list(self):
        hl = _couple_heatlists([("Alice Smith", "Bob Jones", "Studio A")])
        instances = parse_heatlists(hl, [], {})
        data = build_heats_json(999, {"Competition_Name": "T", "Date_Range": "", "Location": ""}, instances, {})
        comps = set(data["competitors"])
        assert "Alice Smith" in comps
        assert "Bob Jones" in comps

    def test_all_four_competitors_in_competitors_list(self):
        hl = _couple_heatlists([
            ("Alice Smith", "Bob Jones", "Studio A"),
            ("Carol Doe", "Dan Roe", "Studio B"),
        ])
        instances = parse_heatlists(hl, [], {})
        data = build_heats_json(999, {"Competition_Name": "T", "Date_Range": "", "Location": ""}, instances, {})
        comps = set(data["competitors"])
        for name in ("Alice Smith", "Bob Jones", "Carol Doe", "Dan Roe"):
            assert name in comps

    def test_both_partners_in_competitor_heats(self):
        hl = _couple_heatlists([("Alice Smith", "Bob Jones", "Studio A")])
        instances = parse_heatlists(hl, [], {})
        data = build_heats_json(999, {"Competition_Name": "T", "Date_Range": "", "Location": ""}, instances, {})
        assert "Alice Smith" in data["competitor_heats"]
        assert "Bob Jones" in data["competitor_heats"]

    def test_no_duplicate_couple_keys_in_heat(self):
        hl = _couple_heatlists([
            ("Alice Smith", "Bob Jones", "Studio A"),
            ("Carol Doe", "Dan Roe", "Studio B"),
        ])
        instances = parse_heatlists(hl, [], {})
        for inst in instances:
            seen = set()
            for e in inst.entries:
                key = frozenset([e.competitor1, e.competitor2])
                assert key not in seen
                seen.add(key)


@pytest.mark.skipif(not HEATS_JSON.exists(), reason="real data not present")
class TestRealDataHeats:
    @pytest.fixture(autouse=True)
    def load(self):
        self.data = json.loads(HEATS_JSON.read_text())

    def test_no_mirrored_couples_in_any_heat(self):
        for heat in self.data["heats"]:
            seen = set()
            for e in heat["entries"]:
                key = frozenset([e["competitor1"], e["competitor2"]])
                assert key not in seen, (
                    f"Mirrored duplicate in heat {heat['key']}: "
                    f"{e['competitor1']} & {e['competitor2']}"
                )
                seen.add(key)

    def test_all_partners_in_competitors_list(self):
        comps = set(self.data["competitors"])
        missing = []
        for heat in self.data["heats"]:
            for e in heat["entries"]:
                if e["competitor2"] and e["competitor2"] not in comps:
                    missing.append(e["competitor2"])
        assert not missing, f"Partners missing from competitors list: {missing[:5]}"

    def test_johan_piper_in_competitors(self):
        assert "Johan Piper" in self.data["competitors"]

    def test_all_partners_in_competitor_heats(self):
        ch = self.data["competitor_heats"]
        for heat in self.data["heats"]:
            for e in heat["entries"]:
                if e["competitor2"]:
                    assert e["competitor2"] in ch, f"{e['competitor2']} missing from competitor_heats"

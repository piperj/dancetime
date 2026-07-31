from ranking.session_parser import parse_session_results


def _entry(bib, placement, first1, last1, first2=None, last2=None):
    participants = [{"ID": f"A{bib}1", "Name": [first1, last1]}]
    if first2:
        participants.append({"ID": f"A{bib}2", "Name": [first2, last2]})
    return {
        "Bib": bib,
        "Placement": placement,
        "Competitors": {"ID": f"C{bib}", "Participants": participants, "Residence": "Nowhere, XX"},
    }


def _round(round_id, event_id, name, round_name, entries):
    return {"ID": round_id, "Event_ID": event_id, "Name": name, "Round": round_name, "Entries": entries}


def _heat(title, date_time, rounds):
    return {
        "Type": "Heat",
        "Title": title,
        "Subtitle": "",
        "Duration": "1.0",
        "Date_Time": date_time,
        "Floors": [{"Name": "A", "Rounds": rounds}],
    }


class TestParseSessionResults:
    def test_ignores_activity_items(self):
        items = [{"Type": "Activity", "Title": "Awards"}]
        assert parse_session_results(items, session_id=1) == []

    def test_parses_contested_heat(self):
        entries = [
            _entry("101", "1", "Alice", "Adams", "Bob", "Baker"),
            _entry("102", "2", "Carol", "Chen", "Dan", "Diaz"),
        ]
        items = [_heat("Heat 5", "7/1/2026 8:00 AM", [_round(100, 200, "L-A3 Amer. Cha Cha", "Final", entries)])]
        results = parse_session_results(items, session_id=3)
        assert len(results) == 1
        r = results[0]
        assert r.event_id == 200
        assert r.event_name == "L-A3 Amer. Cha Cha"
        assert r.round_id == 100
        assert r.round_name == "Final"
        assert r.dance_id == 100
        assert r.dance_name == "Final (Combined)"
        assert r.session_id == 3
        assert r.heat_number == 5
        assert r.placements["Alice Adams"] == 1
        assert r.placements["Bob Baker"] == 1
        assert r.partners["Alice Adams"] == "Bob Baker"
        assert r.is_contested()

    def test_x_and_empty_placements_are_not_numeric(self):
        entries = [
            _entry("101", "X", "Alice", "Adams", "Bob", "Baker"),
            _entry("102", "", "Carol", "Chen", "Dan", "Diaz"),
        ]
        items = [_heat("Heat 1", "7/1/2026 8:00 AM", [_round(1, 2, "Event", "Semi-Final", entries)])]
        results = parse_session_results(items, session_id=1)
        # Both entries are present as competitors, but neither has a placement
        # (an unplaced round isn't "contested" per DanceResult.is_contested()).
        assert results == []

    def test_solo_participant_heat(self):
        entries = [
            _entry("101", "1", "Alice", "Adams"),
            _entry("102", "2", "Bob", "Baker"),
        ]
        items = [_heat("Heat 2", "7/1/2026 8:00 AM", [_round(1, 2, "Event", "Final", entries)])]
        results = parse_session_results(items, session_id=1)
        assert len(results) == 1
        assert results[0].competitors == ["Alice Adams", "Bob Baker"]
        assert results[0].partners == {}

    def test_heat_number_extracted_from_title(self):
        entries = [
            _entry("101", "1", "Alice", "Adams", "Bob", "Baker"),
            _entry("102", "2", "Carol", "Chen", "Dan", "Diaz"),
        ]
        items = [_heat("Heat 42", "7/1/2026 8:00 AM", [_round(1, 2, "Event", "Final", entries)])]
        assert parse_session_results(items, session_id=1)[0].heat_number == 42

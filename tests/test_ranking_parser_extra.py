from ranking.parser import (
    _extract_placement,
    _parse_competitor_events,
    _parse_summary_fallback,
    parse_results,
)


# --- _parse_summary_fallback: no summary / no competitors (lines 84-86) ---

def test_summary_fallback_returns_none_when_no_summary():
    result = _parse_summary_fallback(1, "E", 1, "Final", 1, {})
    assert result is None


def test_summary_fallback_returns_none_when_summary_has_no_competitors():
    result = _parse_summary_fallback(1, "E", 1, "Final", 1, {"Summary": {"Competitors": []}})
    assert result is None


def test_summary_fallback_skips_competitor_with_no_participants():
    round_data = {
        "Summary": {"Competitors": [
            {"Participants": [], "Result": ["1"]},
        ]},
    }
    result = _parse_summary_fallback(1, "E", 1, "Final", 1, round_data)
    assert result is None


def test_summary_fallback_produces_combined_dance_result():
    round_data = {
        "Dances": [{"Dance_ID": 42}],
        "Summary": {"Competitors": [
            {"Participants": [{"Name": ["Alice", "Smith"]}], "Result": ["1"]},
            {"Participants": [{"Name": ["Bob", "Jones"]}], "Result": ["2"]},
        ]},
    }
    result = _parse_summary_fallback(1, "E", 1, "Final", 1, round_data)
    assert result is not None
    assert result.dance_id == 42
    assert result.dance_name == "Final (Combined)"
    assert len(result.competitors) == 2


def test_summary_fallback_dance_id_defaults_to_round_id_when_no_dances():
    round_data = {
        "Summary": {"Competitors": [
            {"Participants": [{"Name": ["Alice", "Smith"]}], "Result": ["1"]},
        ]},
    }
    result = _parse_summary_fallback(1, "E", 7, "Final", 1, round_data)
    assert result.dance_id == 7


# --- _parse_competitor_events: falls through to summary fallback branch (31-33) ---

def test_parse_competitor_events_uses_summary_fallback_when_no_individual_results():
    data = {"Events": [{
        "ID": 1, "Name": "Adult Silver",
        "Rounds": [{
            "ID": 1, "Name": "Final", "Session_ID": 1,
            "Dances": [{"Dance_ID": 1, "Competitors": [
                {"Participants": [{"Name": ["A", "B"]}], "Result": None, "Marks": []},
            ]}],
            "Summary": {"Competitors": [
                {"Participants": [{"Name": ["A", "B"]}], "Result": ["1"]},
                {"Participants": [{"Name": ["C", "D"]}], "Result": ["2"]},
            ]},
        }],
    }]}
    results = _parse_competitor_events(data)
    assert len(results) == 1
    assert results[0].dance_name == "Final (Combined)"


def test_parse_competitor_events_skips_round_with_no_usable_results():
    data = {"Events": [{
        "ID": 1, "Name": "E",
        "Rounds": [{"ID": 1, "Name": "Final", "Session_ID": 1, "Dances": []}],
    }]}
    results = _parse_competitor_events(data)
    assert results == []


# --- placement via Marks (line 61 area: participants empty skip in _parse_individual_dances) ---

def test_parse_results_skips_competitor_with_no_participants():
    data = {"results": [{"Events": [{
        "ID": 1, "Name": "E",
        "Rounds": [{"ID": 1, "Name": "Final", "Session_ID": 1, "Dances": [{
            "Dance_ID": 1, "Dance_Name": "Waltz",
            "Competitors": [
                {"Participants": [], "Result": 1},
                {"Participants": [{"Name": ["A", "B"]}], "Result": 1},
                {"Participants": [{"Name": ["C", "D"]}], "Result": 2},
            ],
        }]}],
    }]}]}
    results = parse_results(data)
    assert len(results) == 1
    assert len(results[0].competitors) == 2


# --- _extract_placement: non-numeric list tail, non-numeric circuit place ---

def test_extract_placement_non_numeric_list_tail_falls_through_to_none():
    assert _extract_placement({"Result": ["TIE", "abc"]}) is None


def test_extract_placement_non_numeric_circuit_place_returns_none():
    assert _extract_placement({"Circuit": {"Place": "abc"}}) is None


def test_extract_placement_no_result_no_circuit_returns_none():
    assert _extract_placement({}) is None


# --- placement derived from judges' Marks when Result is None (lines 64-66) ---

def test_parse_results_computes_placement_from_marks():
    data = {"results": [{"Events": [{
        "ID": 1, "Name": "E",
        "Rounds": [{"ID": 1, "Name": "Final", "Session_ID": 1, "Dances": [{
            "Dance_ID": 1, "Dance_Name": "Waltz",
            "Competitors": [
                {"Participants": [{"Name": ["A", "B"]}], "Result": None, "Marks": [1, 1, 2]},
                {"Participants": [{"Name": ["C", "D"]}], "Result": None, "Marks": [2, 2, 1]},
            ],
        }]}],
    }]}]}
    results = parse_results(data)
    assert len(results) == 1
    # num_judges=3, first comp's mark sum=4 -> placement = 3-4+1 = 0
    assert results[0].placements["A B"] == 0

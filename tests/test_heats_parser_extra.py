from heats.parser import (
    HeatEntry,
    HeatInstance,
    _build_name_to_studio,
    _build_result_index,
    _entry_exists,
    _synthesize_rounds_from_results,
    parse_heatlists,
)


# --- _build_result_index: Summary/Circuit fallback (lines 109, 120-129) ---

def test_result_index_summary_circuit_fallback_used_when_no_direct_result():
    results = [{
        "Events": [{
            "Name": "Adult Full Bronze Rhythm",
            "Rounds": [{
                "Name": "Semi-Final",
                "Dances": [{
                    "Dance_ID": 1, "Dance_Name": "Cha Cha",
                    "Competitors": [
                        {"Result": None, "Participants": [{"Name": ["Alice", "Smith"]}]},
                    ],
                }],
                "Summary": {
                    "Competitors": [
                        {"Circuit": {"Place": 3}, "Participants": [{"Name": ["Alice", "Smith"]}]},
                    ]
                },
            }],
        }],
    }]
    index = _build_result_index(results)
    assert index["Adult Full Bronze Rhythm|Semi-Final|Alice Smith"] == "3"


def test_result_index_circuit_place_zero_is_skipped():
    results = [{
        "Events": [{
            "Name": "E",
            "Rounds": [{
                "Name": "R",
                "Summary": {
                    "Competitors": [
                        {"Circuit": {"Place": 0}, "Participants": [{"Name": ["Alice", "Smith"]}]},
                    ]
                },
            }],
        }],
    }]
    index = _build_result_index(results)
    assert "E|R|Alice Smith" not in index


def test_result_index_disambiguates_shared_partner_in_same_round():
    # Regression test: a pro (Yuriy) dancing with two different students in
    # the same round/event used to have his second placement silently
    # overwrite the first's, since the index was keyed by name alone. Both
    # placements must be independently retrievable via the couple-aware key.
    results = [{
        "Events": [{
            "Name": "Top Solo Grand Prix",
            "Rounds": [{
                "Name": "Final",
                "Dances": [{
                    "Competitors": [
                        {"Result": 4, "Participants": [
                            {"Name": ["Sarah", "McClammy"]}, {"Name": ["Yuriy", "Kuvshynov"]},
                        ]},
                        {"Result": 3, "Participants": [
                            {"Name": ["Debbie", "Babcock"]}, {"Name": ["Yuriy", "Kuvshynov"]},
                        ]},
                    ],
                }],
            }],
        }],
    }]
    index = _build_result_index(results)
    assert index["Top Solo Grand Prix|Final|Sarah McClammy|Yuriy Kuvshynov"] == "4"
    assert index["Top Solo Grand Prix|Final|Debbie Babcock|Yuriy Kuvshynov"] == "3"


def test_result_index_summary_does_not_override_direct_result():
    results = [{
        "Events": [{
            "Name": "E",
            "Rounds": [{
                "Name": "R",
                "Dances": [{
                    "Competitors": [
                        {"Result": 1, "Participants": [{"Name": ["Alice", "Smith"]}]},
                    ],
                }],
                "Summary": {
                    "Competitors": [
                        {"Circuit": {"Place": 9}, "Participants": [{"Name": ["Alice", "Smith"]}]},
                    ]
                },
            }],
        }],
    }]
    index = _build_result_index(results)
    assert index["E|R|Alice Smith"] == "1"


# --- _entry_exists (line 146) ---

def test_entry_exists_true_when_competitor_already_present():
    instance = HeatInstance(key="k", heat_number="1", session="01", session_name="S",
                             time="", round_name="Final")
    instance.entries.append(HeatEntry(couple="Alice & Bob", competitor1="Alice",
                                       competitor2="Bob", bib="1", studio="", event="", result=""))
    assert _entry_exists(instance, "Alice", "Bob") is True


def test_entry_exists_false_when_not_present():
    instance = HeatInstance(key="k", heat_number="1", session="01", session_name="S",
                             time="", round_name="Final")
    assert _entry_exists(instance, "Alice", "Bob") is False


# --- _build_name_to_studio ---

def test_build_name_to_studio_skips_missing_studio():
    heatlists = [
        {"_metadata": {"competitor_name": "Alice", "studio": "Arete"}},
        {"_metadata": {"competitor_name": "Bob", "studio": ""}},
    ]
    mapping = _build_name_to_studio(heatlists)
    assert mapping == {"Alice": "Arete"}


# --- _synthesize_rounds_from_results (lines 180-227) ---

def test_synthesize_adds_round_missing_from_heatlists():
    instances = {}
    results = [{
        "Events": [{
            "Name": "Adult Full Silver Standard",
            "Heat": "42",
            "Rounds": [{
                "Name": "Final",
                "Session_ID": 2,
                "Date_Time": "1/30/2026 12:10:42 PM",
                "Summary": {
                    "Competitors": [
                        {"Bib": "100", "Participants": [
                            {"Name": ["Alice", "Smith"]}, {"Name": ["Bob", "Jones"]},
                        ]},
                    ]
                },
            }],
        }],
    }]
    _synthesize_rounds_from_results(instances, results, {"02": "Thursday Evening"}, {}, {})
    assert len(instances) == 1
    inst = next(iter(instances.values()))
    assert inst.heat_number == "42"
    assert inst.round_name == "Final"
    entry = inst.entries[0]
    assert entry.competitor1 == "Alice Smith"
    assert entry.competitor2 == "Bob Jones"
    assert entry.couple == "Alice Smith & Bob Jones"


def test_synthesize_skips_round_already_in_existing():
    inst = HeatInstance(key="k", heat_number="42", session="02", session_name="S",
                         time="", round_name="Final")
    instances = {"k": inst}
    results = [{
        "Events": [{
            "Name": "E", "Heat": "42",
            "Rounds": [{
                "Name": "Final", "Session_ID": 2, "Date_Time": "1/30/2026 12:10:42 PM",
                "Summary": {"Competitors": [
                    {"Bib": "100", "Participants": [{"Name": ["Alice", "Smith"]}]},
                ]},
            }],
        }],
    }]
    _synthesize_rounds_from_results(instances, results, {}, {}, {})
    assert len(instances) == 1
    assert instances["k"].entries == []


def test_synthesize_skips_event_with_no_heat_number():
    instances = {}
    results = [{"Events": [{"Name": "E", "Heat": "", "Rounds": [{"Name": "Final"}]}]}]
    _synthesize_rounds_from_results(instances, results, {}, {}, {})
    assert instances == {}


def test_synthesize_single_competitor_and_studio_lookup():
    instances = {}
    results = [{
        "Events": [{
            "Name": "E", "Heat": "7",
            "Rounds": [{
                "Name": "Final", "Session_ID": None, "Date_Time": "",
                "Summary": {"Competitors": [
                    {"Bib": "5", "Participants": [{"Name": ["Solo", "Dancer"]}]},
                ]},
            }],
        }],
    }]
    name_to_studio = {"Solo Dancer": "Studio X"}
    _synthesize_rounds_from_results(instances, results, {}, name_to_studio, {})
    inst = next(iter(instances.values()))
    entry = inst.entries[0]
    assert entry.competitor1 == "Solo Dancer"
    assert entry.competitor2 == ""
    assert entry.couple == "Solo Dancer"
    assert entry.studio == "Studio X"
    assert inst.session == "00"


def test_synthesize_skips_competitor_with_no_participants():
    instances = {}
    results = [{
        "Events": [{
            "Name": "E", "Heat": "7",
            "Rounds": [{
                "Name": "Final", "Session_ID": 1, "Date_Time": "",
                "Summary": {"Competitors": [
                    {"Bib": "5", "Participants": []},
                ]},
            }],
        }],
    }]
    _synthesize_rounds_from_results(instances, results, {}, {}, {})
    assert instances == {}


def test_parse_heatlists_synthesizes_via_public_api():
    results = [{
        "Events": [{
            "Name": "Adult Full Silver Standard",
            "Heat": "99",
            "Rounds": [{
                "Name": "Final",
                "Session_ID": 3,
                "Date_Time": "1/30/2026 1:00:00 PM",
                "Summary": {"Competitors": [
                    {"Bib": "150", "Participants": [
                        {"Name": ["Zoe", "Reyes"]}, {"Name": ["Yuri", "Petrov"]},
                    ]},
                ]},
            }],
        }],
    }]
    instances = parse_heatlists([], results, {"03": "Friday Night"})
    assert len(instances) == 1
    assert instances[0].heat_number == "99"
    assert instances[0].session_name == "Friday Night"

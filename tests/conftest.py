import json
import zipfile
from pathlib import Path

import pytest


SAMPLE_COMPETITION_INFO = {
    "Status": 1,
    "Result": {
        "ID": 373,
        "Name": "Test Ball",
        "StartDate": "2026-01-29",
        "EndDate": "2026-02-01",
        "Location": "Columbus, OH",
        "Published": True,
    },
}

SAMPLE_COMPETITOR_LIST = {
    "Status": 1,
    "Result": [
        {"ID": "A1", "Type": "Couple"},
        {"ID": "A2", "Type": "Couple"},
    ],
}

SAMPLE_RESULTS_RAW = {
    "Status": 1,
    "Result": {
        "Competitor": {
            "Name": ["Alice", "Smith"],
            "Keywords": "Fred Astaire",
        },
        "Events": [
            {
                "ID": 10,
                "Name": "Adult Full Silver Standard",
                "Rounds": [
                    {
                        "ID": 1,
                        "Name": "Final",
                        "Dances": [
                            {
                                "ID": 1,
                                "Name": "Waltz",
                                "Competitors": [
                                    {
                                        "Bib": 100,
                                        "Participants": [{"Name": ["Bob", "Jones"]}],
                                    }
                                ],
                            }
                        ],
                        "Summary": {
                            "Competitors": [
                                {
                                    "Result": 1,
                                    "Participants": [
                                        {"Name": ["Alice", "Smith"]},
                                        {"Name": ["Bob", "Jones"]},
                                    ],
                                },
                                {
                                    "Result": 2,
                                    "Participants": [
                                        {"Name": ["Carol", "Doe"]},
                                        {"Name": ["Dan", "Roe"]},
                                    ],
                                },
                            ]
                        },
                    }
                ],
            }
        ],
    },
}

SAMPLE_HEATLISTS_RAW = {
    "Status": 1,
    "Result": {
        "Competitor": {
            "Name": ["Alice", "Smith"],
            "Keywords": "Fred Astaire",
        },
        "Entries": [
            {
                "SessionID": 3,
                "HeatNumber": 42,
                "Time": "2026-01-30T12:10:42",
                "EventID": 10,
                "EventName": "Adult Full Silver Standard",
                "RoundID": 1,
                "RoundName": "Final",
                "Bib": 100,
                "Partners": [{"Name": ["Bob", "Jones"]}],
            }
        ],
    },
}


@pytest.fixture
def tmp_data_dir(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    return tmp_path


@pytest.fixture
def sample_competition_info():
    return SAMPLE_COMPETITION_INFO


@pytest.fixture
def sample_competitor_list():
    return SAMPLE_COMPETITOR_LIST


@pytest.fixture
def sample_results_raw():
    return SAMPLE_RESULTS_RAW


@pytest.fixture
def sample_heatlists_raw():
    return SAMPLE_HEATLISTS_RAW


@pytest.fixture
def sample_zip(tmp_path):
    zip_path = tmp_path / "comp_test.zip"
    results_envelope = {
        "downloaded_at": "2026-01-30T00:00:00Z",
        "total_competitors": 2,
        "results": [SAMPLE_RESULTS_RAW["Result"]],
    }
    heatlists_envelope = {
        "downloaded_at": "2026-01-30T00:00:00Z",
        "total_competitors": 2,
        "heatlists": [SAMPLE_HEATLISTS_RAW["Result"]],
    }
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("competition_info.json", json.dumps(SAMPLE_COMPETITION_INFO["Result"]))
        zf.writestr("results.json", json.dumps(results_envelope))
        zf.writestr("heatlists.json", json.dumps(heatlists_envelope))
    return zip_path

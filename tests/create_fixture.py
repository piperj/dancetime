"""Run once to create tests/fixtures/comp_test.zip with real API structure."""
import json
import zipfile
from pathlib import Path

COMP_INFO = {
    "Competition_ID": 11,
    "Comp_Year_ID": 999,
    "Competition_Name": "Test Ball",
    "Start_Date": "01/29/2026",
    "End_Date": "02/01/2026",
    "Date_Range": "Jan 29 to Feb 1, 2026",
    "Location": "Test City",
}

RESULTS = {
    "downloaded_at": "2026-01-30T00:00:00Z",
    "total_competitors": 2,
    "results": [
        {
            "_metadata": {"competitor_id": "A155", "competitor_name": "Alice Smith", "studio": "Fred Astaire"},
            "Competitor": {
                "ID": "A155", "Name": ["Alice", "Smith"], "Keywords": "Fred Astaire",
            },
            "Events": [{
                "ID": 10,
                "Name": "Adult Full Silver Standard",
                "Rounds": [{
                    "ID": 1, "Name": "Final", "Session_ID": 2, "Date_Time": "1/30/2026 12:10 PM",
                    "Dances": [{
                        "Dance_ID": 1, "Dance_Name": "Waltz",
                        "Competitors": [
                            {"Result": 1, "Participants": [{"Name": ["Alice", "Smith"]}, {"Name": ["Bob", "Jones"]}]},
                            {"Result": 2, "Participants": [{"Name": ["Carol", "Doe"]}, {"Name": ["Dan", "Roe"]}]},
                        ],
                    }],
                    "Summary": {"Competitors": []},
                }],
            }],
        },
        {
            "_metadata": {"competitor_id": "A200", "competitor_name": "Carol Doe", "studio": "Arthur Murray"},
            "Competitor": {
                "ID": "A200", "Name": ["Carol", "Doe"], "Keywords": "Arthur Murray",
            },
            "Events": [{
                "ID": 10,
                "Name": "Adult Full Silver Standard",
                "Rounds": [{
                    "ID": 1, "Name": "Final", "Session_ID": 2, "Date_Time": "1/30/2026 12:10 PM",
                    "Dances": [{
                        "Dance_ID": 1, "Dance_Name": "Waltz",
                        "Competitors": [
                            {"Result": 1, "Participants": [{"Name": ["Alice", "Smith"]}, {"Name": ["Bob", "Jones"]}]},
                            {"Result": 2, "Participants": [{"Name": ["Carol", "Doe"]}, {"Name": ["Dan", "Roe"]}]},
                        ],
                    }],
                    "Summary": {"Competitors": []},
                }],
            }],
        },
    ],
}

HEATLISTS = {
    "downloaded_at": "2026-01-30T00:00:00Z",
    "total_competitors": 2,
    "heatlists": [
        {
            "_metadata": {"competitor_id": "155", "competitor_name": "Alice Smith", "studio": "Fred Astaire"},
            "ID": 155, "Name": ["Alice", "Smith"], "Keywords": "Fred Astaire",
            "Entries": [{
                "Type": "Partner",
                "Couple_ID": 97,
                "Participants": [{"ID": 156, "Name": ["Bob", "Jones"]}],
                "Events": [{
                    "Event_ID": 10,
                    "Event_Name": "Adult Full Silver Standard",
                    "Heat": "42",
                    "Bib": "100",
                    "Rounds": [{"Round_Name": "Final", "Session": "02", "Round_Time": "1/30/2026 12:10:42 PM", "Complete": 1}],
                }],
            }],
        },
        {
            "_metadata": {"competitor_id": "200", "competitor_name": "Carol Doe", "studio": "Arthur Murray"},
            "ID": 200, "Name": ["Carol", "Doe"], "Keywords": "Arthur Murray",
            "Entries": [{
                "Type": "Partner",
                "Couple_ID": 98,
                "Participants": [{"ID": 201, "Name": ["Dan", "Roe"]}],
                "Events": [{
                    "Event_ID": 10,
                    "Event_Name": "Adult Full Silver Standard",
                    "Heat": "42",
                    "Bib": "200",
                    "Rounds": [{"Round_Name": "Final", "Session": "02", "Round_Time": "1/30/2026 12:10:42 PM", "Complete": 1}],
                }],
            }],
        },
    ],
}

if __name__ == "__main__":
    out = Path(__file__).parent / "fixtures" / "comp_test.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("competition_info.json", json.dumps(COMP_INFO, indent=2))
        zf.writestr("results.json", json.dumps(RESULTS, indent=2))
        zf.writestr("heatlists.json", json.dumps(HEATLISTS, indent=2))
    print(f"Created {out}")

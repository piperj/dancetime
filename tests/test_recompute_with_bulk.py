import json

from ranking.bulk_store import read_bulk_archive, write_bulk_archive
from ranking.elo_store import load_ratings_full
from scrape.zip_store import save_json
from tools.recompute_with_bulk import recompute


def _couple_result(event_id, event_name, winner, loser):
    """Build a results.json-shaped payload: winner beats loser, 1 dance."""
    dance = {
        "Dance_ID": 1, "Dance_Name": "Waltz",
        "Competitors": [
            {"Result": 1, "Participants": [{"Name": [winner[0].split()[0], winner[0].split()[1]]},
                                            {"Name": [winner[1].split()[0], winner[1].split()[1]]}]},
            {"Result": 2, "Participants": [{"Name": [loser[0].split()[0], loser[0].split()[1]]},
                                            {"Name": [loser[1].split()[0], loser[1].split()[1]]}]},
        ],
    }
    event = {"ID": event_id, "Name": event_name, "Rounds": [
        {"ID": 1, "Name": "Final", "Session_ID": 1, "Dances": [dance]}
    ]}
    # parse_results reads one "Events" list per competitor _metadata entry, and
    # _deduplicate merges same (event_id, round_id, dance_id) records back
    # together — one entry per name is enough, all four show up in Competitors.
    all_names = [*winner, *loser]
    return {"results": [{"_metadata": {"competitor_name": n, "studio": "Star Studio"}, "Events": [event]}
                         for n in all_names]}


def _write_tracked_zip(raw_dir, cyi, start_date_mmddyyyy, event_id, event_name, winner, loser):
    zip_path = raw_dir / f"comp_{cyi}.zip"
    save_json({"Start_Date": start_date_mmddyyyy, "Competition_Name": f"Tracked {cyi}"},
              zip_path, "competition_info.json")
    save_json(_couple_result(event_id, event_name, winner, loser), zip_path, "results.json")
    return zip_path


class _ScriptedClient:
    """Session-feed fixture: one contested heat per cyi, scripted by the caller."""

    def __init__(self, heats_by_cyi: dict):
        self._heats = heats_by_cyi

    def fetch_session_list(self, cyi):
        return {"Ballrooms": [{"ID": 1, "Sessions": [{"ID": 1}]}]}

    def fetch_session(self, cyi, session, ballroom=1, feed_type=2):
        winner, loser = self._heats[cyi]

        def _entry(placement, names):
            return {
                "Placement": placement,
                "Competitors": {"Participants": [
                    {"Name": [names[0].split()[0], names[0].split()[1]]},
                    {"Name": [names[1].split()[0], names[1].split()[1]]},
                ]},
            }

        return [{
            "Type": "Heat", "Title": "Heat 1", "Date_Time": "1/1/2024 8:00 AM",
            "Floors": [{"Rounds": [{
                "ID": 1, "Event_ID": 1, "Name": "Event", "Round": "Final",
                "Entries": [_entry("1", winner), _entry("2", loser)],
            }]}],
        }]


class TestRecomputeChronologicalOrder:
    """Tracked comp 100 (Jan) -> bulk comp 200 (Jun) -> tracked comp 300 (Dec).

    Comp 200 sits chronologically between the two tracked comps, so a correct
    recompute must process it in between them — not "all tracked, then all
    bulk" — for comp 300's initial ratings to reflect comp 200's outcome.
    """

    def _setup(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        out_dir = tmp_path

        # Comp 100 (tracked, 2024-01-01): Alice & Bob beat Carol & Dan.
        _write_tracked_zip(
            raw_dir, 100, "01/01/2024", 1, "Event",
            winner=("Alice Adams", "Bob Baker"), loser=("Carol Chen", "Dan Diaz"),
        )
        # Comp 300 (tracked, 2024-12-01): Alice & Bob beat Eve & Frank.
        _write_tracked_zip(
            raw_dir, 300, "12/01/2024", 1, "Event",
            winner=("Alice Adams", "Bob Baker"), loser=("Eve Evans", "Frank Ford"),
        )

        # Comp 200 (bulk, 2024-06-01): Carol & Dan beat Eve & Frank — sits
        # between the two tracked comps above.
        calendar = {
            "competitions": [
                {"cyi": 100, "competition_id": 1, "start_date": "2024-01-01", "end_date": "2024-01-01",
                 "tracked": True, "published": True, "name": "Tracked 100"},
                {"cyi": 300, "competition_id": 1, "start_date": "2024-12-01", "end_date": "2024-12-01",
                 "tracked": True, "published": True, "name": "Tracked 300"},
                {"cyi": 200, "competition_id": 2, "start_date": "2024-06-01", "end_date": "2024-06-01",
                 "published": True, "name": "Bulk 200", "location": "Nowhere, XX"},
            ]
        }
        (out_dir / "calendar.json").write_text(json.dumps(calendar))
        # A stub existing bulk archive — recompute must overwrite it, not skip it.
        write_bulk_archive(200, {"meta": {}, "couples": []}, [], out_dir)

        client = _ScriptedClient({200: (("Carol Chen", "Dan Diaz"), ("Eve Evans", "Frank Ford"))})
        return raw_dir, out_dir, client

    def test_all_three_comps_produce_output(self, tmp_path):
        raw_dir, out_dir, client = self._setup(tmp_path)
        recompute(raw_dir, out_dir, client=client)

        assert (out_dir / "ranking" / "100.json").exists()
        assert (out_dir / "ranking" / "300.json").exists()
        bulk = read_bulk_archive(200, out_dir)
        assert bulk is not None

    def test_comp_100_starts_from_baseline(self, tmp_path):
        raw_dir, out_dir, client = self._setup(tmp_path)
        recompute(raw_dir, out_dir, client=client)

        ranking_100 = json.loads((out_dir / "ranking" / "100.json").read_text())
        alice = next(c for c in ranking_100["couples"] if "Alice Adams" in (c["competitor"], c["partner"]))
        assert alice["initial_elo"] == 1500.0

    def test_comp_300_inherits_comp_200s_bulk_outcome_for_eve(self, tmp_path):
        raw_dir, out_dir, client = self._setup(tmp_path)
        recompute(raw_dir, out_dir, client=client)

        bulk_200 = read_bulk_archive(200, out_dir)
        eve_after_200 = next(
            c["elo"] for c in bulk_200["ranking"]["couples"]
            if "Eve Evans" in (c["competitor"], c["partner"])
        )

        ranking_300 = json.loads((out_dir / "ranking" / "300.json").read_text())
        eve_before_300 = next(
            c["initial_elo"] for c in ranking_300["couples"]
            if "Eve Evans" in (c["competitor"], c["partner"])
        )

        # Eve never appeared before comp 200 (bulk), so if the recompute got the
        # chronological order wrong (e.g. processed all tracked comps before any
        # bulk comp), comp 300 would see her at an untouched baseline instead.
        assert eve_before_300 != 1500.0
        assert eve_before_300 == eve_after_200

    def test_carol_and_dan_carry_comp_100_result_into_bulk_comp_200(self, tmp_path):
        raw_dir, out_dir, client = self._setup(tmp_path)
        recompute(raw_dir, out_dir, client=client)

        ranking_100 = json.loads((out_dir / "ranking" / "100.json").read_text())
        carol_after_100 = next(
            c["elo"] for c in ranking_100["couples"]
            if "Carol Chen" in (c["competitor"], c["partner"])
        )

        bulk_200 = read_bulk_archive(200, out_dir)
        carol_before_200 = next(
            c["initial_elo"] for c in bulk_200["ranking"]["couples"]
            if "Carol Chen" in (c["competitor"], c["partner"])
        )

        # Carol lost comp 100, so she enters the bulk comp below baseline —
        # proving the bulk comp's own computation also picks up tracked history.
        assert carol_before_200 != 1500.0
        assert carol_before_200 == carol_after_100

    def test_final_cumulative_ratings_include_everyone(self, tmp_path):
        raw_dir, out_dir, client = self._setup(tmp_path)
        recompute(raw_dir, out_dir, client=client)

        ratings = load_ratings_full(out_dir)
        assert set(ratings["ratings"]) == {
            "Alice Adams", "Bob Baker", "Carol Chen", "Dan Diaz", "Eve Evans", "Frank Ford",
        }
        assert ratings["last_cyi"] == 300

    def test_studio_directory_merged_from_tracked_comps(self, tmp_path):
        raw_dir, out_dir, client = self._setup(tmp_path)
        recompute(raw_dir, out_dir, client=client)

        directory = json.loads((out_dir / "studio_directory.json").read_text())
        assert directory["Alice Adams"] == "Star Studio"

    def test_stale_bulk_archive_is_overwritten_not_skipped(self, tmp_path):
        raw_dir, out_dir, client = self._setup(tmp_path)
        stale_mtime = (out_dir / "bulk" / "200.tar.xz").stat().st_mtime

        recompute(raw_dir, out_dir, client=client)

        assert (out_dir / "bulk" / "200.tar.xz").stat().st_mtime >= stale_mtime
        bulk = read_bulk_archive(200, out_dir)
        assert bulk["ranking"]["couples"] != []

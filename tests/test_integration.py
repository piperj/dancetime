"""End-to-end pipeline tests using the committed fixture ZIP."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "comp_test.zip"


@pytest.fixture
def pipeline_dirs(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    shutil.copy2(FIXTURE_ZIP, raw_dir / "comp_999.zip")
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>dancetime</html>")
    (static_dir / "favicon.ico").write_bytes(b"")
    (static_dir / "judges-scores.js").write_text("")
    (static_dir / "heat-card.js").write_text("")
    (static_dir / "program.js").write_text("")
    (static_dir / "now-line.js").write_text("")
    return tmp_path


def _args(cyi=999, data_dir=None, out_dir=None, **kwargs):
    return SimpleNamespace(
        cyi=cyi,
        data_dir=str(data_dir or "data/raw"),
        out_dir=str(out_dir or "data"),
        force=False,
        iterations=100,
        deploy=False,
        **kwargs,
    )


class TestHeatsPipeline:
    def test_produces_heats_json(self, pipeline_dirs):
        import heats
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        heats.run(args)
        out = pipeline_dirs / "data" / "heats" / "999.json"
        assert out.exists()

    def test_heats_json_valid_schema(self, pipeline_dirs):
        import heats
        from publish.validator import validate_heats_json
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        heats.run(args)
        errors = validate_heats_json(pipeline_dirs / "data" / "heats" / "999.json")
        assert errors == [], errors

    def test_heats_json_contains_expected_data(self, pipeline_dirs):
        import heats
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        heats.run(args)
        data = json.loads((pipeline_dirs / "data" / "heats" / "999.json").read_text())
        assert data["meta"]["cyi"] == 999
        assert len(data["heats"]) == 1
        assert len(data["heats"][0]["entries"]) == 2
        couples = [e["competitor1"] for e in data["heats"][0]["entries"]]
        assert "Alice Smith" in couples


class TestRankingPipeline:
    def test_produces_ranking_json(self, pipeline_dirs):
        import ranking
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        ranking.run(args)
        out = pipeline_dirs / "data" / "ranking" / "999.json"
        assert out.exists()

    def test_ranking_json_valid_schema(self, pipeline_dirs):
        import ranking
        from publish.validator import validate_ranking_json
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        ranking.run(args)
        errors = validate_ranking_json(pipeline_dirs / "data" / "ranking" / "999.json")
        assert errors == [], errors

    def test_ranking_contains_couples(self, pipeline_dirs):
        import ranking
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        ranking.run(args)
        data = json.loads((pipeline_dirs / "data" / "ranking" / "999.json").read_text())
        assert len(data["couples"]) >= 2

    def test_winner_ranked_first(self, pipeline_dirs):
        import ranking
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        ranking.run(args)
        data = json.loads((pipeline_dirs / "data" / "ranking" / "999.json").read_text())
        couples = data["couples"]
        if couples:
            assert couples[0]["rank"] == 1
            assert couples[0]["elo"] >= couples[-1]["elo"]


class TestFullPipeline:
    def test_end_to_end(self, pipeline_dirs):
        import os, heats, ranking, publish

        orig = os.getcwd()
        os.chdir(pipeline_dirs)
        try:
            data_raw = pipeline_dirs / "data" / "raw"
            data_dir = pipeline_dirs / "data"

            heats.run(_args(data_dir=data_raw, out_dir=data_dir))
            ranking.run(_args(data_dir=data_raw, out_dir=data_dir))
            publish.run(_args(out_dir=data_dir))

            assert (pipeline_dirs / "index.html").exists()
            assert (pipeline_dirs / "data" / "index.json").exists()
            assert (pipeline_dirs / "data" / "heats" / "999.json").exists()
            assert (pipeline_dirs / "data" / "ranking" / "999.json").exists()
        finally:
            os.chdir(orig)

    def test_index_json_lists_competition(self, pipeline_dirs):
        import os, heats, ranking, publish

        orig = os.getcwd()
        os.chdir(pipeline_dirs)
        try:
            data_raw = pipeline_dirs / "data" / "raw"
            data_dir = pipeline_dirs / "data"
            heats.run(_args(data_dir=data_raw, out_dir=data_dir))
            ranking.run(_args(data_dir=data_raw, out_dir=data_dir))
            publish.run(_args(out_dir=data_dir))

            index = json.loads((data_dir / "index.json").read_text())
            assert len(index["competitions"]) == 1
            assert index["competitions"][0]["cyi"] == 999
        finally:
            os.chdir(orig)


class TestRankingIncremental:
    """Regression tests for the production bug where ranking --cyi X wiped elo_ratings.json
    when X had no results, or when prior CYIs' zips were absent (data/raw/ is gitignored)."""

    def test_skips_when_cyi_has_no_results(self, tmp_path):
        """A future comp with empty results.json must not clobber cumulative ratings."""
        import ranking
        from ranking.elo_store import save_ratings
        import zipfile

        raw_dir = tmp_path / "data" / "raw"
        raw_dir.mkdir(parents=True)
        out_dir = tmp_path / "data"
        # Seed an existing ratings file
        save_ratings({"Alice": 1600.0, "Bob": 1500.0}, {"Alice": 3, "Bob": 2}, 373, out_dir)
        prior_bytes = (out_dir / "elo_ratings.json").read_bytes()
        # Create a zip for CYI 904 with empty results
        empty_zip = raw_dir / "comp_904.zip"
        with zipfile.ZipFile(empty_zip, "w") as z:
            z.writestr("competition_info.json", json.dumps({"Start_Date": "07/01/2026"}))
            z.writestr("results.json", json.dumps({"results": []}))

        ranking.run(_args(cyi=904, data_dir=raw_dir, out_dir=out_dir))

        # Ratings file untouched, byte-for-byte
        assert (out_dir / "elo_ratings.json").read_bytes() == prior_bytes

    def test_preserves_prior_competitors_when_only_subset_on_disk(self, pipeline_dirs):
        """The CI invariant: data/raw/ only has the just-scraped zip, but elo_ratings.json
        must retain competitors from prior CYIs that aren't on disk anymore."""
        import ranking
        from ranking.elo_store import save_ratings, load_ratings

        raw_dir = pipeline_dirs / "data" / "raw"
        out_dir = pipeline_dirs / "data"
        # Seed prior ratings from comps whose zips are no longer on disk
        save_ratings(
            {"Charlie": 1700.0, "Dana": 1450.0},
            {"Charlie": 5, "Dana": 4},
            755,
            out_dir,
        )

        ranking.run(_args(cyi=999, data_dir=raw_dir, out_dir=out_dir))

        loaded = load_ratings(out_dir)
        assert loaded["Charlie"] == 1700.0
        assert loaded["Dana"] == 1450.0
        # And the fixture's competitors should also be present
        assert len(loaded) > 2

    def test_rerank_same_cyi_is_idempotent(self, pipeline_dirs):
        """Polling a comp twice (e.g. an hourly cron after no upstream change) must produce
        the same elo and comp_counts as a single rank — no double-counting."""
        import ranking
        from ranking.elo_store import load_ratings

        raw_dir = pipeline_dirs / "data" / "raw"
        out_dir = pipeline_dirs / "data"

        ranking.run(_args(cyi=999, data_dir=raw_dir, out_dir=out_dir))
        first = json.loads((out_dir / "elo_ratings.json").read_text())["ratings"]
        ranking.run(_args(cyi=999, data_dir=raw_dir, out_dir=out_dir))
        second = json.loads((out_dir / "elo_ratings.json").read_text())["ratings"]

        # Same competitors, same elo, same num_comps after re-rank
        assert set(first.keys()) == set(second.keys())
        for name in first:
            assert first[name]["elo"] == second[name]["elo"]
            assert first[name]["num_comps"] == second[name]["num_comps"]

    def test_rerank_uncontested_comp_does_not_inflate_num_comps(self, tmp_path):
        """A comp whose only heat so far has a single couple (no opponent to compare
        against) produces no heat_history for anyone. Re-ranking it hourly while it's
        still in progress must not keep bumping num_comps — there's nothing to rewind."""
        import ranking
        import zipfile

        raw_dir = tmp_path / "data" / "raw"
        raw_dir.mkdir(parents=True)
        out_dir = tmp_path / "data"
        zip_path = raw_dir / "comp_777.zip"
        results = {
            "results": [{
                "_metadata": {"competitor_name": "Alice Smith", "studio": "Fred Astaire"},
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
                            "Competitors": [{
                                "Result": 1,
                                "Participants": [
                                    {"Name": ["Alice", "Smith"]},
                                    {"Name": ["Bob", "Jones"]},
                                ],
                            }],
                        }],
                    }],
                }],
            }],
        }
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("competition_info.json", json.dumps({"Start_Date": "07/01/2026"}))
            z.writestr("results.json", json.dumps(results))

        ranking.run(_args(cyi=777, data_dir=raw_dir, out_dir=out_dir))
        first = json.loads((out_dir / "elo_ratings.json").read_text())["ratings"]
        ranking.run(_args(cyi=777, data_dir=raw_dir, out_dir=out_dir))
        second = json.loads((out_dir / "elo_ratings.json").read_text())["ratings"]

        assert first == second


class TestSortedCompetitionsTiebreak:
    """Two comps sharing a start_date (genuinely concurrent competitions) must sort
    deterministically — by scrape order (zip mtime), not by glob()'s unordered
    filesystem iteration."""

    def _write_zip(self, path: Path, start_date: str) -> None:
        import zipfile
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("competition_info.json", json.dumps({"Start_Date": start_date}))
            z.writestr("results.json", json.dumps({"results": []}))

    def test_ties_broken_by_zip_mtime_not_glob_order(self, tmp_path):
        import os
        import time
        from ranking import sorted_competitions

        raw_dir = tmp_path / "data" / "raw"
        raw_dir.mkdir(parents=True)
        later_zip = raw_dir / "comp_200.zip"
        earlier_zip = raw_dir / "comp_100.zip"

        # Write "later_zip" (higher cyi) first, so it gets the earlier mtime —
        # if the sort fell back to cyi or filename order, this would fail.
        self._write_zip(later_zip, "01/01/2026")
        time.sleep(0.01)
        self._write_zip(earlier_zip, "01/01/2026")
        earlier_mtime = os.stat(earlier_zip).st_mtime
        later_mtime = os.stat(later_zip).st_mtime
        assert later_mtime < earlier_mtime  # sanity: later_zip really was scraped first

        comps = sorted_competitions(raw_dir)
        assert [c[0] for c in comps] == [200, 100]

    def test_result_is_stable_across_repeated_calls(self, tmp_path):
        from ranking import sorted_competitions

        raw_dir = tmp_path / "data" / "raw"
        raw_dir.mkdir(parents=True)
        for cyi in (301, 302, 303):
            self._write_zip(raw_dir / f"comp_{cyi}.zip", "03/01/2026")

        first = [c[0] for c in sorted_competitions(raw_dir)]
        second = [c[0] for c in sorted_competitions(raw_dir)]
        assert first == second


class TestRankingStablePhase:
    """A full rebuild (no --cyi) must skip reprocessing comps whose calendar dates
    put them outside the "live" phase, once they already have ranking + history
    output on disk — see schedule/phases.py::comp_phase."""

    def _write_calendar(self, out_dir: Path, cyi: int, start: str, end: str) -> None:
        (out_dir / "calendar.json").write_text(json.dumps({
            "competitions": [{"cyi": cyi, "start_date": start, "end_date": end}],
        }))

    def test_distant_comp_is_skipped_on_second_full_rebuild(self, pipeline_dirs):
        import ranking

        raw_dir = pipeline_dirs / "data" / "raw"
        out_dir = pipeline_dirs / "data"
        # Comp 999's fixture dates are Jan 2026; treat "now" as far enough past
        # that it's unambiguously "distant" regardless of when this test runs.
        self._write_calendar(out_dir, 999, "2020-01-29", "2020-02-01")

        ranking.run(_args(cyi=None, data_dir=raw_dir, out_dir=out_dir))
        ranking_path = out_dir / "ranking" / "999.json"
        history_path = out_dir / "elo_history" / "999.json"
        assert ranking_path.exists() and history_path.exists()
        first_ranking_mtime = ranking_path.stat().st_mtime_ns
        first_history_mtime = history_path.stat().st_mtime_ns
        first_ratings = json.loads((out_dir / "elo_ratings.json").read_text())["ratings"]

        ranking.run(_args(cyi=None, data_dir=raw_dir, out_dir=out_dir))

        assert ranking_path.stat().st_mtime_ns == first_ranking_mtime
        assert history_path.stat().st_mtime_ns == first_history_mtime
        second_ratings = json.loads((out_dir / "elo_ratings.json").read_text())["ratings"]
        assert first_ratings == second_ratings

    def test_live_comp_is_reprocessed_on_full_rebuild(self, pipeline_dirs):
        import ranking

        raw_dir = pipeline_dirs / "data" / "raw"
        out_dir = pipeline_dirs / "data"
        # A date window spanning "now" keeps comp_phase() returning "live"
        # indefinitely, so it must be reprocessed every rebuild.
        self._write_calendar(out_dir, 999, "2020-01-01", "2099-01-01")

        ranking.run(_args(cyi=None, data_dir=raw_dir, out_dir=out_dir))
        ranking_path = out_dir / "ranking" / "999.json"
        first_mtime = ranking_path.stat().st_mtime_ns

        ranking.run(_args(cyi=None, data_dir=raw_dir, out_dir=out_dir))

        assert ranking_path.stat().st_mtime_ns > first_mtime
        # Still idempotent in content even though the file was rewritten.
        first_ratings = json.loads((out_dir / "elo_ratings.json").read_text())["ratings"]
        ranking.run(_args(cyi=None, data_dir=raw_dir, out_dir=out_dir))
        second_ratings = json.loads((out_dir / "elo_ratings.json").read_text())["ratings"]
        assert first_ratings == second_ratings

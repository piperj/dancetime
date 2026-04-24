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
        out = pipeline_dirs / "data" / "heats_999.json"
        assert out.exists()

    def test_heats_json_valid_schema(self, pipeline_dirs):
        import heats
        from publish.validator import validate_heats_json
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        heats.run(args)
        errors = validate_heats_json(pipeline_dirs / "data" / "heats_999.json")
        assert errors == [], errors

    def test_heats_json_contains_expected_data(self, pipeline_dirs):
        import heats
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        heats.run(args)
        data = json.loads((pipeline_dirs / "data" / "heats_999.json").read_text())
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
        out = pipeline_dirs / "data" / "ranking_999.json"
        assert out.exists()

    def test_ranking_json_valid_schema(self, pipeline_dirs):
        import ranking
        from publish.validator import validate_ranking_json
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        ranking.run(args)
        errors = validate_ranking_json(pipeline_dirs / "data" / "ranking_999.json")
        assert errors == [], errors

    def test_ranking_contains_leaderboard(self, pipeline_dirs):
        import ranking
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        ranking.run(args)
        data = json.loads((pipeline_dirs / "data" / "ranking_999.json").read_text())
        assert len(data["leaderboards"]) >= 1
        first_lb = list(data["leaderboards"].values())[0]
        assert len(first_lb["couples"]) >= 2

    def test_winner_ranked_first(self, pipeline_dirs):
        import ranking
        args = _args(data_dir=pipeline_dirs / "data" / "raw", out_dir=pipeline_dirs / "data")
        ranking.run(args)
        data = json.loads((pipeline_dirs / "data" / "ranking_999.json").read_text())
        for lb in data["leaderboards"].values():
            if lb["couples"]:
                assert lb["couples"][0]["rank"] == 1
                assert lb["couples"][0]["elo"] >= lb["couples"][-1]["elo"]


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
            assert (pipeline_dirs / "data" / "heats_999.json").exists()
            assert (pipeline_dirs / "data" / "ranking_999.json").exists()
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

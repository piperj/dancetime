import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from publish.validator import validate_heats_json, validate_index_json, validate_ranking_json


VALID_HEATS = {
    "meta": {"cyi": 373, "name": "Test Ball", "date_range": "Jan 29", "location": "Columbus", "generated_at": "2026-01-30T00:00:00Z"},
    "sessions": {"3": "Thursday Evening"},
    "heats": [],
    "competitors": [],
    "studios": [],
    "competitor_studios": {},
    "competitor_heats": {},
    "top_matchups": {},
}

VALID_RANKING = {
    "meta": {"cyi": 373, "name": "Test Ball", "date_range": "Jan 29", "location": "Columbus", "generated_at": "2026-01-30T00:00:00Z", "elo_params": {}},
    "leaderboards": {},
    "competitors": [],
    "studios": [],
    "competitor_studios": {},
}

VALID_INDEX = {
    "updated_at": "2026-01-30T00:00:00Z",
    "competitions": [],
}


class TestValidator:
    def test_valid_heats_no_errors(self, tmp_path):
        p = tmp_path / "heats_373.json"
        p.write_text(json.dumps(VALID_HEATS))
        assert validate_heats_json(p) == []

    def test_heats_missing_meta(self, tmp_path):
        bad = dict(VALID_HEATS)
        del bad["meta"]
        p = tmp_path / "heats.json"
        p.write_text(json.dumps(bad))
        errors = validate_heats_json(p)
        assert any("meta" in e for e in errors)

    def test_heats_missing_key(self, tmp_path):
        bad = dict(VALID_HEATS)
        del bad["top_matchups"]
        p = tmp_path / "heats.json"
        p.write_text(json.dumps(bad))
        errors = validate_heats_json(p)
        assert any("top_matchups" in e for e in errors)

    def test_valid_ranking_no_errors(self, tmp_path):
        p = tmp_path / "ranking_373.json"
        p.write_text(json.dumps(VALID_RANKING))
        assert validate_ranking_json(p) == []

    def test_ranking_missing_leaderboards(self, tmp_path):
        bad = dict(VALID_RANKING)
        del bad["leaderboards"]
        p = tmp_path / "ranking.json"
        p.write_text(json.dumps(bad))
        errors = validate_ranking_json(p)
        assert any("leaderboards" in e for e in errors)

    def test_valid_index_no_errors(self, tmp_path):
        p = tmp_path / "index.json"
        p.write_text(json.dumps(VALID_INDEX))
        assert validate_index_json(p) == []

    def test_file_not_found_returns_error(self, tmp_path):
        errors = validate_heats_json(tmp_path / "nonexistent.json")
        assert len(errors) == 1

    def test_invalid_json_returns_error(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json {{{")
        errors = validate_heats_json(p)
        assert len(errors) == 1


class TestPublishRun:
    def test_copies_index_html(self, tmp_path):
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html>test</html>")
        (static_dir / "favicon.ico").write_bytes(b"")

        out_dir = tmp_path / "data"
        out_dir.mkdir()

        args = MagicMock()
        args.out_dir = str(out_dir)
        args.deploy = False

        import os
        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            import publish
            publish.run(args)
        finally:
            os.chdir(orig_dir)

        assert (tmp_path / "index.html").exists()
        assert (tmp_path / "index.html").read_text() == "<html>test</html>"

    def test_deploy_calls_wrangler(self, tmp_path):
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html/>")
        (static_dir / "favicon.ico").write_bytes(b"")

        out_dir = tmp_path / "data"
        out_dir.mkdir()

        args = MagicMock()
        args.out_dir = str(out_dir)
        args.deploy = True

        import os
        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch("subprocess.run") as mock_run:
                import publish
                publish.run(args)
                mock_run.assert_called_once()
                assert "wrangler" in mock_run.call_args[0][0]
        finally:
            os.chdir(orig_dir)

    def test_no_deploy_skips_wrangler(self, tmp_path):
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html/>")
        (static_dir / "favicon.ico").write_bytes(b"")

        out_dir = tmp_path / "data"
        out_dir.mkdir()

        args = MagicMock()
        args.out_dir = str(out_dir)
        args.deploy = False

        import os
        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch("subprocess.run") as mock_run:
                import publish
                publish.run(args)
                mock_run.assert_not_called()
        finally:
            os.chdir(orig_dir)

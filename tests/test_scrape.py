import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scrape.client import NDCAClient
from scrape.fetcher import fetch_all
from scrape.zip_store import list_files, load_json, save_json


class TestNDCAClient:
    def _make_client(self, response_data):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status.return_value = None
        mock_session.get.return_value = mock_resp
        return NDCAClient(session=mock_session)

    def test_get_returns_result_on_success(self):
        client = self._make_client({"Status": 1, "Result": {"name": "Test"}})
        result = client._get("/feed/test/")
        assert result == {"name": "Test"}

    def test_get_returns_none_on_bad_status(self):
        client = self._make_client({"Status": 0, "Result": {}})
        assert client._get("/feed/test/") is None

    def test_get_returns_none_on_network_error(self):
        import requests
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.RequestException("timeout")
        client = NDCAClient(session=mock_session)
        assert client._get("/feed/test/") is None

    def test_get_returns_none_on_json_error(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("bad json")
        mock_session.get.return_value = mock_resp
        client = NDCAClient(session=mock_session)
        assert client._get("/feed/test/") is None

    def test_fetch_competitor_list_returns_empty_on_non_list(self):
        client = self._make_client({"Status": 1, "Result": {"not": "a list"}})
        assert client.fetch_competitor_list(373) == []

    def test_fetch_competition_info(self):
        # compyears endpoint uses "Events" key, not "Result"
        mock_data = {"Status": 1, "Events": [{"Competition_Name": "Test Ball", "Comp_Year_ID": 373}]}
        client = self._make_client(mock_data)
        result = client.fetch_competition_info(373)
        assert result["Competition_Name"] == "Test Ball"


class TestZipStore:
    def test_save_and_load_roundtrip(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        data = {"key": "value", "num": 42}
        save_json(data, zip_path, "test.json")
        loaded = load_json(zip_path, "test.json")
        assert loaded == data

    def test_save_creates_parent_dirs(self, tmp_path):
        zip_path = tmp_path / "sub" / "dir" / "test.zip"
        save_json({"x": 1}, zip_path, "f.json")
        assert zip_path.exists()

    def test_save_replaces_existing_file(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        save_json({"v": 1}, zip_path, "data.json")
        save_json({"v": 2}, zip_path, "data.json")
        loaded = load_json(zip_path, "data.json")
        assert loaded["v"] == 2

    def test_save_preserves_other_files(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        save_json({"a": 1}, zip_path, "a.json")
        save_json({"b": 2}, zip_path, "b.json")
        assert "a.json" in list_files(zip_path)
        assert "b.json" in list_files(zip_path)

    def test_list_files(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        save_json({}, zip_path, "alpha.json")
        save_json({}, zip_path, "beta.json")
        files = list_files(zip_path)
        assert sorted(files) == ["alpha.json", "beta.json"]


class TestFetcher:
    def _make_mock_client(self, sample_competition_info, sample_results_raw, sample_heatlists_raw):
        client = MagicMock(spec=NDCAClient)
        client.fetch_competition_info.return_value = sample_competition_info["Result"]
        client.fetch_competitor_list.return_value = [
            {"ID": "A1", "Type": "Couple"},
            {"ID": "A2", "Type": "Couple"},
        ]
        client.fetch_competitor_results.return_value = sample_results_raw["Result"]
        client.fetch_competitor_heatlists.return_value = sample_heatlists_raw["Result"]
        return client

    def test_creates_zip_with_three_files(self, tmp_data_dir, sample_competition_info, sample_results_raw, sample_heatlists_raw):
        client = self._make_mock_client(sample_competition_info, sample_results_raw, sample_heatlists_raw)
        zip_path = fetch_all(373, tmp_data_dir / "raw", force=False, client=client)
        assert zip_path.exists()
        files = list_files(zip_path)
        assert "competition_info.json" in files
        assert "results.json" in files
        assert "heatlists.json" in files

    def test_skips_download_when_cached(self, tmp_data_dir, sample_competition_info, sample_results_raw, sample_heatlists_raw):
        client = self._make_mock_client(sample_competition_info, sample_results_raw, sample_heatlists_raw)
        raw_dir = tmp_data_dir / "raw"
        zip_path = fetch_all(373, raw_dir, force=False, client=client)
        call_count = client.fetch_competition_info.call_count

        fetch_all(373, raw_dir, force=False, client=client)
        assert client.fetch_competition_info.call_count == call_count  # no new call

    def test_force_redownloads(self, tmp_data_dir, sample_competition_info, sample_results_raw, sample_heatlists_raw):
        client = self._make_mock_client(sample_competition_info, sample_results_raw, sample_heatlists_raw)
        raw_dir = tmp_data_dir / "raw"
        fetch_all(373, raw_dir, force=False, client=client)
        fetch_all(373, raw_dir, force=True, client=client)
        assert client.fetch_competition_info.call_count == 2

    def test_results_envelope_structure(self, tmp_data_dir, sample_competition_info, sample_results_raw, sample_heatlists_raw):
        client = self._make_mock_client(sample_competition_info, sample_results_raw, sample_heatlists_raw)
        zip_path = fetch_all(373, tmp_data_dir / "raw", force=False, client=client)
        results = load_json(zip_path, "results.json")
        assert "total_competitors" in results
        assert "results" in results
        assert isinstance(results["results"], list)

    def test_metadata_attached_to_results(self, tmp_data_dir, sample_competition_info, sample_results_raw, sample_heatlists_raw):
        client = self._make_mock_client(sample_competition_info, sample_results_raw, sample_heatlists_raw)
        zip_path = fetch_all(373, tmp_data_dir / "raw", force=False, client=client)
        results = load_json(zip_path, "results.json")
        first = results["results"][0]
        assert "_metadata" in first
        assert "competitor_name" in first["_metadata"]

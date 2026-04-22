import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from schedule.calendar import _normalize, _to_iso, load_calendar, parse_date, refresh_calendar
from cal.server import _auto_scrape, _build_competitions


# --- _to_iso ---

def test_to_iso_mm_dd_yyyy():
    assert _to_iso("01/22/2026") == "2026-01-22"

def test_to_iso_already_iso():
    assert _to_iso("2026-01-22") == "2026-01-22"

def test_to_iso_empty():
    assert _to_iso("") == ""

def test_to_iso_unknown_returns_as_is():
    assert _to_iso("not-a-date") == "not-a-date"


# --- _normalize ---

NDCA_RAW = {
    "Comp_Year_ID": 373,
    "compyear_id": 373,
    "Competition_ID": 11,
    "competition_id": 11,
    "Comp_Year_Name": "City Lights Open",
    "Competition_Name": "City Lights Open",
    "Approved_Location": ["San Jose", "CA"],
    "Start_Date": "01/22/2026",
    "End_Date": "01/25/2026",
    "Publish_Results": 1,
}

def test_normalize_cyi():
    assert _normalize(NDCA_RAW)["cyi"] == 373

def test_normalize_competition_id():
    assert _normalize(NDCA_RAW)["competition_id"] == 11

def test_normalize_name():
    assert _normalize(NDCA_RAW)["name"] == "City Lights Open"

def test_normalize_location_joins_list():
    assert _normalize(NDCA_RAW)["location"] == "San Jose, CA"

def test_normalize_dates_to_iso():
    n = _normalize(NDCA_RAW)
    assert n["start_date"] == "2026-01-22"
    assert n["end_date"] == "2026-01-25"

def test_normalize_published_from_publish_results():
    assert _normalize(NDCA_RAW)["published"] is True
    assert _normalize({**NDCA_RAW, "Publish_Results": 0})["published"] is False

def test_normalize_already_normalized_passthrough():
    stored = {
        "cyi": 373, "competition_id": 11, "name": "City Lights Open",
        "location": "San Jose, CA", "start_date": "2026-01-22",
        "end_date": "2026-01-25", "published": True,
    }
    n = _normalize(stored)
    assert n["cyi"] == 373
    assert n["start_date"] == "2026-01-22"

def test_normalize_location_string_passthrough():
    comp = {**NDCA_RAW, "Approved_Location": None, "location": "Columbus, OH"}
    assert _normalize(comp)["location"] == "Columbus, OH"


# --- refresh_calendar ---

def test_refresh_calendar_writes_file(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    fake_events = [NDCA_RAW]
    mock_client = type("C", (), {"fetch_calendar": lambda self: fake_events})()
    cal = refresh_calendar(tmp_path, mock_client)
    path = tmp_path / "calendar.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert len(data["competitions"]) == 1
    assert data["competitions"][0]["cyi"] == 373

def test_refresh_calendar_handles_api_failure(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    mock_client = type("C", (), {"fetch_calendar": lambda self: None})()
    cal = refresh_calendar(tmp_path, mock_client)
    assert cal["competitions"] == []


# --- load_calendar ---

def test_load_calendar_missing_file(tmp_path):
    result = load_calendar(tmp_path)
    assert result == {"competitions": []}

def test_load_calendar_reads_existing(tmp_path):
    data = {"competitions": [{"cyi": 1}]}
    (tmp_path / "calendar.json").write_text(json.dumps(data))
    assert load_calendar(tmp_path)["competitions"][0]["cyi"] == 1


# --- _auto_scrape ---

def test_auto_scrape_live():
    today = date(2026, 1, 23)
    assert _auto_scrape("2026-01-22", "2026-01-25", today) == "live"

def test_auto_scrape_live_grace_day():
    today = date(2026, 1, 26)  # one day after end
    assert _auto_scrape("2026-01-22", "2026-01-25", today) == "live"

def test_auto_scrape_soon():
    today = date(2026, 1, 12)
    assert _auto_scrape("2026-01-22", "2026-01-25", today) == "soon"

def test_auto_scrape_none_far_future():
    today = date(2026, 1, 1)
    assert _auto_scrape("2026-06-01", "2026-06-05", today) is None

def test_auto_scrape_none_past():
    today = date(2026, 3, 1)
    assert _auto_scrape("2026-01-22", "2026-01-25", today) is None

def test_auto_scrape_bad_dates():
    assert _auto_scrape("", "", date.today()) is None


# --- _build_competitions ---

def _make_calendar(tmp_path, comps, extra=None):
    data = {"competitions": comps}
    if extra:
        data.update(extra)
    (tmp_path / "calendar.json").write_text(json.dumps(data))
    (tmp_path / "raw").mkdir(exist_ok=True)


def test_build_skips_null_cyi(tmp_path):
    _make_calendar(tmp_path, [{"cyi": None, "name": "Bad", "start_date": "", "end_date": ""}])
    assert _build_competitions(tmp_path)["competitions"] == []


def test_build_scraped_flag(tmp_path):
    _make_calendar(tmp_path, [{"cyi": 373, "competition_id": 11, "name": "X", "start_date": "2024-01-01", "end_date": "2024-01-03"}])
    (tmp_path / "raw" / "comp_373.zip").write_bytes(b"fake")
    result = _build_competitions(tmp_path)["competitions"]
    assert result[0]["scraped"] is True
    assert result[0]["heats"] is False
    assert result[0]["ranking"] is False


def test_build_competition_id_from_calendar(tmp_path):
    _make_calendar(tmp_path, [{"cyi": 373, "competition_id": 11, "name": "X", "start_date": "2024-01-01", "end_date": "2024-01-03"}])
    result = _build_competitions(tmp_path)["competitions"]
    assert result[0]["competition_id"] == 11


def test_build_auto_scrape_soon(tmp_path):
    today = date.today()
    start = (today + timedelta(days=5)).isoformat()
    end = (today + timedelta(days=8)).isoformat()
    _make_calendar(tmp_path, [{"cyi": 1, "competition_id": 99, "name": "X", "start_date": start, "end_date": end}])
    result = _build_competitions(tmp_path)["competitions"]
    assert result[0]["auto_scrape"] == "soon"


def test_build_includes_active_cyi(tmp_path):
    _make_calendar(tmp_path, [{"cyi": 1, "competition_id": 99, "name": "X", "start_date": "2024-01-01", "end_date": "2024-01-03"}], extra={"active_cyi": 1})
    assert _build_competitions(tmp_path)["active_cyi"] == 1

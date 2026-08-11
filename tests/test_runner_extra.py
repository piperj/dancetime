import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from schedule.runner import (
    _known_calendar,
    _known_cyis,
    _load_last_runs,
    _nearest_comp,
    detect_active_cyi,
    due_cyis,
    mark_run,
    run_status,
    should_run,
)


def _now(date_str, hour=12, minute=0):
    return datetime(*[int(x) for x in date_str.split("-")], hour, minute, tzinfo=timezone.utc)


def _write_calendar(data_dir, comps, active_cyi=None):
    cal = {"competitions": comps}
    if active_cyi is not None:
        cal["active_cyi"] = active_cyi
    (data_dir / "calendar.json").write_text(json.dumps(cal))


# --- due_cyis (default now=None) ---

def test_due_cyis_defaults_now_to_current_time(tmp_path):
    _write_calendar(tmp_path, [])
    assert due_cyis(tmp_path) == []


# --- _due_from_calendar via due_cyis: skip cyi None, override match, bad dates ---

def test_due_skips_comp_with_null_cyi(tmp_path):
    _write_calendar(tmp_path, [{"cyi": None, "start_date": "2026-01-01", "end_date": "2026-01-02"}])
    assert due_cyis(tmp_path, _now("2026-01-01")) == []


def test_due_active_cyi_override_forces_live(tmp_path):
    _write_calendar(tmp_path, [{"cyi": 5, "start_date": "2099-01-01", "end_date": "2099-01-02"}],
                     active_cyi=5)
    assert due_cyis(tmp_path, _now("2026-01-01")) == [5]


def test_due_skips_comp_with_unparseable_dates(tmp_path):
    _write_calendar(tmp_path, [{"cyi": 5, "start_date": "", "end_date": ""}])
    assert due_cyis(tmp_path, _now("2026-01-01")) == []


# --- _load_last_runs error branches ---

def test_load_last_runs_missing_file(tmp_path):
    assert _load_last_runs(tmp_path) == {}


def test_load_last_runs_non_dict_json(tmp_path):
    (tmp_path / "last_run.json").write_text("[1, 2, 3]")
    assert _load_last_runs(tmp_path) == {}


def test_load_last_runs_malformed_json(tmp_path):
    (tmp_path / "last_run.json").write_text("not json")
    assert _load_last_runs(tmp_path) == {}


def test_load_last_runs_valid(tmp_path):
    (tmp_path / "last_run.json").write_text(json.dumps({"5": "2026-01-01T00:00:00+00:00"}))
    result = _load_last_runs(tmp_path)
    assert result[5].year == 2026


# --- mark_run: naive datetime branch, malformed existing file ---

def test_mark_run_with_naive_datetime(tmp_path):
    naive_now = datetime(2026, 1, 1, 12, 0)
    mark_run(tmp_path, [1], naive_now)
    data = json.loads((tmp_path / "last_run.json").read_text())
    assert "1" in data


def test_mark_run_defaults_now_to_current_time(tmp_path):
    mark_run(tmp_path, [3])
    data = json.loads((tmp_path / "last_run.json").read_text())
    assert "3" in data


def test_mark_run_overwrites_malformed_existing_file(tmp_path):
    (tmp_path / "last_run.json").write_text("not json")
    mark_run(tmp_path, [2], _now("2026-01-01"))
    data = json.loads((tmp_path / "last_run.json").read_text())
    assert "2" in data


# --- should_run ---

def test_should_run_false_when_nothing_due(tmp_path):
    _write_calendar(tmp_path, [])
    assert should_run(tmp_path, _now("2026-01-01")) is False


def test_should_run_true_when_due(tmp_path):
    _write_calendar(tmp_path, [{"cyi": 5, "start_date": "2026-01-01", "end_date": "2026-01-02"}])
    assert should_run(tmp_path, _now("2026-01-01")) is True


# --- run_status ---

def test_run_status_defaults_now_to_current_time(tmp_path):
    _write_calendar(tmp_path, [])
    run, cyi, name, reason = run_status(tmp_path)
    assert run is False


def test_run_status_up_to_date_with_nearest_comp(tmp_path):
    _write_calendar(tmp_path, [{"cyi": 5, "name": "Far Comp", "start_date": "2099-01-01", "end_date": "2099-01-02"}])
    run, cyi, name, reason = run_status(tmp_path, _now("2026-01-01"))
    assert run is False
    assert cyi == 5
    assert name == "Far Comp"
    assert reason == "up to date"


def test_run_status_up_to_date_no_comps_at_all(tmp_path):
    _write_calendar(tmp_path, [])
    run, cyi, name, reason = run_status(tmp_path, _now("2026-01-01"))
    assert run is False
    assert cyi is None
    assert name == "unknown"
    assert reason == "up to date"


def test_run_status_due_single_comp(tmp_path):
    _write_calendar(tmp_path, [{"cyi": 5, "name": "Live Comp", "start_date": "2026-01-01", "end_date": "2026-01-02"}])
    run, cyi, name, reason = run_status(tmp_path, _now("2026-01-01"))
    assert run is True
    assert cyi == 5
    assert name == "Live Comp"
    assert reason == "due"


def test_run_status_due_multiple_comps_shows_suffix(tmp_path):
    _write_calendar(tmp_path, [
        {"cyi": 5, "name": "A", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        {"cyi": 6, "name": "B", "start_date": "2026-01-01", "end_date": "2026-01-02"},
    ])
    run, cyi, name, reason = run_status(tmp_path, _now("2026-01-01"))
    assert run is True
    assert "(+1 more)" in reason


# --- _nearest_comp ---

def test_nearest_comp_skips_unparseable_dates():
    calendar = {"competitions": [
        {"cyi": 1, "start_date": "", "end_date": ""},
        {"cyi": 2, "start_date": "2026-01-01", "end_date": "2026-01-02"},
    ]}
    comp, phase = _nearest_comp(calendar, _now("2026-01-01"))
    assert comp["cyi"] == 2


# --- detect_active_cyi ---

def test_detect_active_cyi_returns_active(tmp_path):
    mock_client = MagicMock()
    mock_client.fetch_calendar.return_value = [
        {"Comp_Year_ID": 5, "Competition_ID": 1, "Comp_Year_Name": "X",
         "Approved_Location": "", "Start_Date": "2026-01-01", "End_Date": "2026-01-02",
         "Publish_Results": 1},
    ]
    with patch("schedule.runner.is_comp_active", return_value=(True, 5)):
        cyi = detect_active_cyi(tmp_path, mock_client)
    assert cyi == 5


def test_detect_active_cyi_filters_to_known_and_falls_back_to_last(tmp_path):
    (tmp_path / "index.json").write_text(json.dumps({"competitions": [{"cyi": 5}]}))
    mock_client = MagicMock()
    mock_client.fetch_calendar.return_value = [
        {"Comp_Year_ID": 5, "Competition_ID": 1, "Comp_Year_Name": "X",
         "Approved_Location": "", "Start_Date": "2020-01-01", "End_Date": "2020-01-02",
         "Publish_Results": 1},
        {"Comp_Year_ID": 6, "Competition_ID": 2, "Comp_Year_Name": "Y",
         "Approved_Location": "", "Start_Date": "2020-02-01", "End_Date": "2020-02-02",
         "Publish_Results": 1},
    ]
    cyi = detect_active_cyi(tmp_path, mock_client)
    assert cyi == 5


def test_detect_active_cyi_no_comps_returns_none(tmp_path):
    mock_client = MagicMock()
    mock_client.fetch_calendar.return_value = None
    assert detect_active_cyi(tmp_path, mock_client) is None


# --- _known_calendar / _known_cyis ---

def test_known_calendar_returns_all_when_none_known(tmp_path):
    _write_calendar(tmp_path, [{"cyi": 5, "start_date": "2026-01-01", "end_date": "2026-01-02"}])
    result = _known_calendar(tmp_path)
    assert len(result["competitions"]) == 1


def test_known_calendar_filters_to_known(tmp_path):
    _write_calendar(tmp_path, [
        {"cyi": 5, "start_date": "2026-01-01", "end_date": "2026-01-02", "tracked": True},
        {"cyi": 6, "start_date": "2026-01-01", "end_date": "2026-01-02"},
    ])
    result = _known_calendar(tmp_path)
    assert [c["cyi"] for c in result["competitions"]] == [5]


def test_known_cyis_malformed_index_json_ignored(tmp_path):
    (tmp_path / "index.json").write_text("not json")
    _write_calendar(tmp_path, [{"cyi": 5, "tracked": True}])
    known = _known_cyis(tmp_path)
    assert known == {5}


def test_known_cyis_from_index_json(tmp_path):
    (tmp_path / "index.json").write_text(json.dumps({"competitions": [{"cyi": 7}]}))
    known = _known_cyis(tmp_path)
    assert 7 in known

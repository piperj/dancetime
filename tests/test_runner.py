import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from schedule.runner import _is_due, _nearest_comp, due_cyis, mark_run


# --- helpers ---

def _d(s): return date.fromisoformat(s)

def _now(date_str, hour=12, minute=0):
    return datetime(
        *[int(x) for x in date_str.split("-")],
        hour, minute, tzinfo=timezone.utc,
    )

def _calendar(*comps, active_cyi=None):
    cal = {"competitions": list(comps)}
    if active_cyi is not None:
        cal["active_cyi"] = active_cyi
    return cal

def _comp(cyi, start, end, name="Test"):
    return {"cyi": cyi, "name": name, "start_date": start, "end_date": end}


# --- _is_due ---

def test_is_due_never_run():
    assert _is_due(_now("2026-01-23"), None, timedelta(hours=1)) is True

def test_is_due_just_ran():
    t = _now("2026-01-23", hour=14)
    assert _is_due(t, t, timedelta(hours=1)) is False

def test_is_due_interval_elapsed():
    t = _now("2026-01-23", hour=14)
    assert _is_due(t, t - timedelta(hours=1), timedelta(hours=1)) is True

def test_is_due_within_tolerance():
    # 10 min tolerance: 51 min after last run still counts as due for a 1h interval
    t = _now("2026-01-23", hour=14)
    assert _is_due(t, t - timedelta(minutes=51), timedelta(hours=1)) is True

def test_is_due_outside_tolerance():
    t = _now("2026-01-23", hour=14)
    assert _is_due(t, t - timedelta(minutes=49), timedelta(hours=1)) is False


# --- _nearest_comp ---

def test_nearest_live():
    cal = _calendar(_comp(1, "2026-01-22", "2026-01-25"))
    c, phase = _nearest_comp(cal, _now("2026-01-23"))
    assert phase == "live"
    assert c["cyi"] == 1

def test_nearest_grace_day():
    cal = _calendar(_comp(1, "2026-01-22", "2026-01-25"))
    _, phase = _nearest_comp(cal, _now("2026-01-26"))
    assert phase == "live"

def test_nearest_soon_1_day():
    cal = _calendar(_comp(1, "2026-01-22", "2026-01-25"))
    _, phase = _nearest_comp(cal, _now("2026-01-21"))
    assert phase == "soon"

def test_nearest_soon_10_days():
    cal = _calendar(_comp(1, "2026-02-01", "2026-02-04"))
    _, phase = _nearest_comp(cal, _now("2026-01-22"))
    assert phase == "soon"

def test_nearest_upcoming_11_days():
    cal = _calendar(_comp(1, "2026-02-02", "2026-02-05"))
    _, phase = _nearest_comp(cal, _now("2026-01-22"))
    assert phase == "upcoming"

def test_nearest_distant_future():
    cal = _calendar(_comp(1, "2026-04-01", "2026-04-04"))
    _, phase = _nearest_comp(cal, _now("2026-01-22"))
    assert phase == "distant"

def test_nearest_recent():
    cal = _calendar(_comp(1, "2026-01-10", "2026-01-13"))
    _, phase = _nearest_comp(cal, _now("2026-01-15"))
    assert phase == "recent"

def test_nearest_distant_past():
    cal = _calendar(_comp(1, "2026-01-10", "2026-01-13"))
    _, phase = _nearest_comp(cal, _now("2026-03-01"))
    assert phase == "distant"

def test_nearest_active_cyi_override():
    cal = _calendar(_comp(1, "2026-06-01", "2026-06-05"), active_cyi=1)
    _, phase = _nearest_comp(cal, _now("2026-01-01"))
    assert phase == "live"

def test_nearest_urgency_beats_proximity():
    # recent ended 3 days ago (24h), soon starts in 5 days (1h) — soon wins
    cal = _calendar(
        _comp(1, "2026-01-15", "2026-01-18"),
        _comp(2, "2026-01-27", "2026-01-30"),
    )
    c, phase = _nearest_comp(cal, _now("2026-01-22"))
    assert c["cyi"] == 2
    assert phase == "soon"

def test_nearest_same_urgency_picks_closer():
    cal = _calendar(
        _comp(1, "2026-01-08", "2026-01-11"),   # ended 11 days ago
        _comp(2, "2025-12-01", "2025-12-04"),   # ended 49 days ago — distant
    )
    c, phase = _nearest_comp(cal, _now("2026-01-22"))
    assert c["cyi"] == 1
    assert phase == "recent"

def test_nearest_no_comps():
    c, phase = _nearest_comp({"competitions": []}, _now("2026-01-22"))
    assert phase == "none"
    assert c == {}


# --- due_cyis (integration via tmp_path) ---

def _setup(tmp_path, cyis, comps, active_cyi=None, last_runs=None):
    (tmp_path / "index.json").write_text(json.dumps({
        "competitions": [{"cyi": c} for c in cyis]
    }))
    data = {"competitions": comps}
    if active_cyi is not None:
        data["active_cyi"] = active_cyi
    (tmp_path / "calendar.json").write_text(json.dumps(data))
    if last_runs:
        (tmp_path / "last_run.json").write_text(json.dumps({
            str(k): v.isoformat() for k, v in last_runs.items()
        }))


def test_due_bootstrap_no_last_run(tmp_path):
    # No last_run.json → every comp with a defined interval is due on first run.
    _setup(tmp_path, [1], [_comp(1, "2026-01-22", "2026-01-25")])
    assert due_cyis(tmp_path, _now("2026-01-23")) == [1]


def test_due_live_interval_elapsed(tmp_path):
    t = _now("2026-01-23", hour=14)
    _setup(tmp_path, [1], [_comp(1, "2026-01-22", "2026-01-25")],
           last_runs={1: t - timedelta(minutes=55)})
    assert due_cyis(tmp_path, t) == [1]


def test_due_live_too_soon(tmp_path):
    t = _now("2026-01-23", hour=14)
    _setup(tmp_path, [1], [_comp(1, "2026-01-22", "2026-01-25")],
           last_runs={1: t - timedelta(minutes=2)})
    assert due_cyis(tmp_path, t) == []


def test_due_soon_interval_elapsed(tmp_path):
    t = _now("2026-01-22", hour=14)
    start = (t.date() + timedelta(days=5)).isoformat()
    end = (t.date() + timedelta(days=8)).isoformat()
    _setup(tmp_path, [1], [_comp(1, start, end)],
           last_runs={1: t - timedelta(hours=6)})
    assert due_cyis(tmp_path, t) == [1]


def test_due_soon_too_soon(tmp_path):
    t = _now("2026-01-22", hour=14)
    start = (t.date() + timedelta(days=5)).isoformat()
    end = (t.date() + timedelta(days=8)).isoformat()
    _setup(tmp_path, [1], [_comp(1, start, end)],
           last_runs={1: t - timedelta(hours=2)})
    assert due_cyis(tmp_path, t) == []


def test_due_distant_never_due(tmp_path):
    _setup(tmp_path, [1], [_comp(1, "2026-06-01", "2026-06-05")])
    assert due_cyis(tmp_path, _now("2026-01-22")) == []


def test_due_per_cyi_independence(tmp_path):
    """Each CYI tracks its own last_run; one due, one not."""
    t = _now("2026-01-23", hour=14)
    _setup(tmp_path, [1, 2], [
        _comp(1, "2026-01-22", "2026-01-25"),   # live (1h)
        _comp(2, "2026-01-22", "2026-01-25"),   # live (1h)
    ], last_runs={1: t - timedelta(minutes=55), 2: t - timedelta(minutes=2)})
    result = due_cyis(tmp_path, t)
    assert result == [1]


def test_mark_run_round_trip(tmp_path):
    t = _now("2026-01-23", hour=14)
    _setup(tmp_path, [1, 2], [
        _comp(1, "2026-01-22", "2026-01-25"),
        _comp(2, "2026-01-22", "2026-01-25"),
    ])
    mark_run(tmp_path, [1], now=t)
    # CYI 1 just ran → not due; CYI 2 has no entry → still due
    assert due_cyis(tmp_path, t) == [2]
    mark_run(tmp_path, [2], now=t)
    assert due_cyis(tmp_path, t) == []



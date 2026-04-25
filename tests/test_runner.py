import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from schedule.runner import _interval_label, _nearest_comp, _slot_due, due_cyis


# --- helpers ---

def _d(s): return date.fromisoformat(s)

def _now(date_str, hour=12, minute=0):
    return datetime(
        *[int(x) for x in date_str.split("-")],
        hour, minute, tzinfo=timezone.utc,
    )

def _on_slot(base: datetime, interval: timedelta) -> datetime:
    """Snap base down to the nearest slot boundary (floor to interval)."""
    secs = int(interval.total_seconds())
    ts = int(base.timestamp())
    return datetime.fromtimestamp(ts - ts % secs, tz=timezone.utc)

def _calendar(*comps, active_cyi=None):
    cal = {"competitions": list(comps)}
    if active_cyi is not None:
        cal["active_cyi"] = active_cyi
    return cal

def _comp(cyi, start, end, name="Test"):
    return {"cyi": cyi, "name": name, "start_date": start, "end_date": end}


# --- _slot_due ---

def test_slot_due_15min_always_due():
    # 15-min interval: any value mod 900 is in [0, 899] which is always < 900
    interval = timedelta(minutes=15)
    assert _slot_due(_now("2026-01-23"), interval) is True
    assert _slot_due(_now("2026-01-23", minute=7), interval) is True

def test_slot_due_1h_at_top_of_hour():
    interval = timedelta(hours=1)
    t = _on_slot(_now("2026-01-22", hour=14), interval)   # 14:00 UTC
    assert _slot_due(t, interval) is True

def test_slot_due_1h_at_15min_past():
    interval = timedelta(hours=1)
    t = _on_slot(_now("2026-01-22", hour=14), interval) + timedelta(minutes=15)
    assert _slot_due(t, interval) is False

def test_slot_due_24h_at_midnight():
    interval = timedelta(hours=24)
    t = _on_slot(_now("2026-01-22", hour=0), interval)    # UTC midnight
    assert _slot_due(t, interval) is True

def test_slot_due_24h_at_noon():
    interval = timedelta(hours=24)
    t = _on_slot(_now("2026-01-22", hour=0), interval) + timedelta(hours=12)
    assert _slot_due(t, interval) is False


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

def _setup(tmp_path, cyis, comps, active_cyi=None):
    (tmp_path / "index.json").write_text(json.dumps({
        "competitions": [{"cyi": c} for c in cyis]
    }))
    data = {"competitions": comps}
    if active_cyi is not None:
        data["active_cyi"] = active_cyi
    (tmp_path / "calendar.json").write_text(json.dumps(data))


def test_due_live_always_due(tmp_path):
    # 15-min interval: every slot is in-slot, so live comps are always due
    _setup(tmp_path, [1], [_comp(1, "2026-01-22", "2026-01-25")])
    assert due_cyis(tmp_path, _now("2026-01-23")) == [1]
    assert due_cyis(tmp_path, _now("2026-01-23", minute=7)) == [1]

def test_due_soon_at_top_of_hour(tmp_path):
    base = _now("2026-01-22", hour=14)
    t = _on_slot(base, timedelta(hours=1))   # exactly 14:00 UTC
    start = (t.date() + timedelta(days=5)).isoformat()
    end = (t.date() + timedelta(days=8)).isoformat()
    _setup(tmp_path, [1], [_comp(1, start, end)])
    assert due_cyis(tmp_path, t) == [1]

def test_due_soon_not_at_top_of_hour(tmp_path):
    base = _now("2026-01-22", hour=14)
    t = _on_slot(base, timedelta(hours=1)) + timedelta(minutes=15)  # 14:15
    start = (t.date() + timedelta(days=5)).isoformat()
    end = (t.date() + timedelta(days=8)).isoformat()
    _setup(tmp_path, [1], [_comp(1, start, end)])
    assert due_cyis(tmp_path, t) == []

def test_due_distant_never_due(tmp_path):
    _setup(tmp_path, [1], [_comp(1, "2026-06-01", "2026-06-05")])
    assert due_cyis(tmp_path, _now("2026-01-22")) == []

def test_due_multiple_independent(tmp_path):
    """Live (15 min) and soon (1 h) comps checked independently — only live due at :15."""
    t = _on_slot(_now("2026-01-23", hour=14), timedelta(hours=1)) + timedelta(minutes=15)
    _setup(tmp_path, [1, 2], [
        _comp(1, "2026-01-22", "2026-01-25"),   # live → always due
        _comp(2, "2026-01-28", "2026-01-31"),   # soon → only due at top of hour
    ])
    result = due_cyis(tmp_path, t)
    assert 1 in result
    assert 2 not in result

def test_due_multiple_both_due(tmp_path):
    """At the top of an hour, both a live and a soon comp are due."""
    t = _on_slot(_now("2026-01-23", hour=14), timedelta(hours=1))  # 14:00 UTC
    _setup(tmp_path, [1, 2], [
        _comp(1, "2026-01-22", "2026-01-25"),   # live → always due
        _comp(2, "2026-01-28", "2026-01-31"),   # soon → due at top of hour
    ])
    result = due_cyis(tmp_path, t)
    assert 1 in result
    assert 2 in result


# --- _interval_label ---

def test_interval_label_minutes():
    assert _interval_label(timedelta(minutes=15)) == "15m"

def test_interval_label_hours():
    assert _interval_label(timedelta(hours=1)) == "1h"
    assert _interval_label(timedelta(hours=23)) == "23h"

def test_interval_label_days():
    assert _interval_label(timedelta(days=1)) == "1d"
    assert _interval_label(timedelta(days=2)) == "2d"

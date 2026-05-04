from datetime import date
from schedule.phases import (
    GRACE_DAYS, PHASE_INTERVALS, SOON_DAYS, UPCOMING_DAYS,
    comp_phase, interval_label,
)


# ── comp_phase ────────────────────────────────────────────────────────────────

def _phase(start_str, end_str, today_str):
    return comp_phase(
        date.fromisoformat(start_str),
        date.fromisoformat(end_str),
        date.fromisoformat(today_str),
    )


def test_phase_live_during():
    assert _phase("2026-04-01", "2026-04-05", "2026-04-03") == "live"

def test_phase_live_grace():
    assert _phase("2026-04-01", "2026-04-05", "2026-04-06") == "live"

def test_phase_live_grace_boundary():
    # One day past grace period → recent
    assert _phase("2026-04-01", "2026-04-05", f"2026-04-0{5 + GRACE_DAYS + 1}") == "recent"

def test_phase_soon():
    assert _phase("2026-04-10", "2026-04-14", "2026-04-05") == "soon"

def test_phase_soon_boundary():
    start = date(2026, 5, 1)
    today = date(2026, 5, 1) - __import__("datetime").timedelta(days=SOON_DAYS)
    assert comp_phase(start, date(2026, 5, 5), today) == "soon"

def test_phase_upcoming():
    assert _phase("2026-05-15", "2026-05-19", "2026-04-20") == "upcoming"

def test_phase_upcoming_boundary():
    import datetime
    start = date(2026, 5, 1)
    today = start - datetime.timedelta(days=UPCOMING_DAYS)
    assert comp_phase(start, date(2026, 5, 5), today) == "upcoming"

def test_phase_distant():
    assert _phase("2026-09-01", "2026-09-05", "2026-04-01") == "distant"

def test_phase_recent():
    assert _phase("2026-01-01", "2026-01-05", "2026-01-20") == "recent"

def test_phase_distant_past():
    assert _phase("2026-01-01", "2026-01-05", "2026-04-01") == "distant"


# ── interval_label ────────────────────────────────────────────────────────────

def test_interval_label_live():
    iv = PHASE_INTERVALS["live"]
    assert interval_label("live") == f"every {int(iv.total_seconds()) // 60} min"

def test_interval_label_soon():
    iv = PHASE_INTERVALS["soon"]
    assert interval_label("soon") == f"every {int(iv.total_seconds()) // 3600}h"

def test_interval_label_upcoming():
    iv = PHASE_INTERVALS["upcoming"]
    assert interval_label("upcoming") == f"every {int(iv.total_seconds()) // 86400}d"

def test_interval_label_distant_none():
    assert interval_label("distant") is None

def test_interval_label_unknown_none():
    assert interval_label("nonexistent") is None

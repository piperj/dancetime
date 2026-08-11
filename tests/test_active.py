from datetime import datetime, timezone

from schedule.active import is_comp_active


def test_active_cyi_override_short_circuits():
    calendar = {"active_cyi": 99, "competitions": []}
    assert is_comp_active(calendar) == (True, 99)


def test_active_cyi_override_as_string_is_int():
    calendar = {"active_cyi": "99"}
    active, cyi = is_comp_active(calendar)
    assert active is True
    assert cyi == 99
    assert isinstance(cyi, int)


def test_no_competitions_returns_false():
    calendar = {"competitions": []}
    assert is_comp_active(calendar) == (False, None)


def test_comp_within_range_is_active():
    calendar = {"competitions": [
        {"cyi": 5, "start_date": "2026-01-22", "end_date": "2026-01-25"},
    ]}
    now = datetime(2026, 1, 23, tzinfo=timezone.utc)
    assert is_comp_active(calendar, now) == (True, 5)


def test_comp_grace_day_after_end_is_active():
    calendar = {"competitions": [
        {"cyi": 5, "start_date": "2026-01-22", "end_date": "2026-01-25"},
    ]}
    now = datetime(2026, 1, 26, tzinfo=timezone.utc)
    assert is_comp_active(calendar, now) == (True, 5)


def test_comp_two_days_after_end_is_inactive():
    calendar = {"competitions": [
        {"cyi": 5, "start_date": "2026-01-22", "end_date": "2026-01-25"},
    ]}
    now = datetime(2026, 1, 27, tzinfo=timezone.utc)
    assert is_comp_active(calendar, now) == (False, None)


def test_comp_before_start_is_inactive():
    calendar = {"competitions": [
        {"cyi": 5, "start_date": "2026-01-22", "end_date": "2026-01-25"},
    ]}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert is_comp_active(calendar, now) == (False, None)


def test_comp_with_unparseable_dates_skipped():
    calendar = {"competitions": [
        {"cyi": 5, "start_date": "", "end_date": ""},
        {"cyi": 6, "start_date": "2026-01-22", "end_date": "2026-01-25"},
    ]}
    now = datetime(2026, 1, 23, tzinfo=timezone.utc)
    assert is_comp_active(calendar, now) == (True, 6)


def test_defaults_now_to_current_time():
    active, cyi = is_comp_active({"competitions": []})
    assert active is False
    assert cyi is None

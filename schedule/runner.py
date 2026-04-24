import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from schedule.active import is_comp_active
from schedule.calendar import load_calendar, refresh_calendar


def should_run(data_dir: Path, now: datetime | None = None) -> bool:
    run, _, _, _ = run_status(data_dir, now)
    return run


def run_status(data_dir: Path, now: datetime | None = None) -> tuple[bool, int | None, str, str]:
    """Return (run, cyi, name, reason) for logging."""
    if now is None:
        now = datetime.now(timezone.utc)

    calendar = _known_calendar(data_dir)
    active, cyi = is_comp_active(calendar, now)

    comp = next((c for c in calendar.get("competitions", []) if c.get("cyi") == cyi), None)
    if comp is None:
        comps = calendar.get("competitions", [])
        comp = comps[-1] if comps else {}

    name = comp.get("name", "unknown")
    cyi = cyi or comp.get("cyi")

    if active:
        return True, cyi, name, "active"

    last_update = _last_update_time(data_dir)
    if last_update is None:
        return True, cyi, name, "no prior update"

    if (now - last_update) >= timedelta(hours=23):
        return True, cyi, name, "periodic update"

    return False, cyi, name, "up to date"


def detect_active_cyi(data_dir: Path, client) -> int | None:
    """Refresh calendar, filter to known competitions, return active or most recent CYI."""
    cal = refresh_calendar(data_dir, client)
    known = _known_cyis(data_dir)
    if known:
        cal = {**cal, "competitions": [c for c in cal.get("competitions", []) if c.get("cyi") in known]}
    active, cyi = is_comp_active(cal)
    if cyi:
        return cyi
    comps = cal.get("competitions", [])
    return comps[-1]["cyi"] if comps else None


def _known_calendar(data_dir: Path) -> dict:
    calendar = load_calendar(data_dir)
    known = _known_cyis(data_dir)
    if not known:
        return calendar
    return {**calendar, "competitions": [c for c in calendar.get("competitions", []) if c.get("cyi") in known]}


def _known_cyis(data_dir: Path) -> set:
    index_path = Path(data_dir) / "index.json"
    if not index_path.exists():
        return set()
    try:
        data = json.loads(index_path.read_text())
        return {c["cyi"] for c in data.get("competitions", [])}
    except (ValueError, KeyError, json.JSONDecodeError):
        return set()


def _last_update_time(data_dir: Path) -> datetime | None:
    index_path = Path(data_dir) / "index.json"
    if not index_path.exists():
        return None
    try:
        data = json.loads(index_path.read_text())
        ts = data.get("updated_at", "")
        return datetime.fromisoformat(ts)
    except (ValueError, KeyError, json.JSONDecodeError):
        return None

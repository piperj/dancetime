import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from schedule.active import is_comp_active
from schedule.calendar import load_calendar, parse_date, refresh_calendar

_PHASE_INTERVALS: dict[str, timedelta | None] = {
    "live":     timedelta(minutes=15),
    "soon":     timedelta(hours=1),
    "upcoming": timedelta(hours=24),
    "recent":   timedelta(hours=24),
    "distant":  None,
    "none":     None,
}

_PHASE_URGENCY = {"live": 0, "soon": 1, "upcoming": 2, "recent": 2, "distant": 3, "none": 4}


def due_cyis(data_dir: Path, now: datetime | None = None) -> list[int]:
    """Return CYIs due for an update this 15-minute slot.

    Uses modular arithmetic: a comp is due whenever now falls in the first 15-minute
    window of its interval cycle (top of each hour for 1h, midnight UTC for 24h).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return _due_from_calendar(_known_calendar(data_dir), now)


def _due_from_calendar(calendar: dict, now: datetime) -> list[int]:
    now_date = now.date()
    override = calendar.get("active_cyi")
    result = []

    for comp in calendar.get("competitions", []):
        cyi = comp.get("cyi")
        if cyi is None:
            continue

        if override is not None and cyi == int(override):
            phase = "live"
        else:
            start = parse_date(comp.get("start_date", ""))
            end = parse_date(comp.get("end_date", ""))
            if start is None or end is None:
                continue
            phase = _comp_phase(start, end, now_date)

        interval = _PHASE_INTERVALS.get(phase)
        if interval is None:
            continue

        if _slot_due(now, interval):
            result.append(cyi)

    return result


def _slot_due(now: datetime, interval: timedelta) -> bool:
    """True if now falls in the first 15-minute slot of the interval cycle."""
    return int(now.timestamp()) % int(interval.total_seconds()) < 15 * 60


def should_run(data_dir: Path, now: datetime | None = None) -> bool:
    return bool(due_cyis(data_dir, now))


def run_status(data_dir: Path, now: datetime | None = None) -> tuple[bool, int | None, str, str]:
    """Return (run, cyi, name, reason) for logging."""
    if now is None:
        now = datetime.now(timezone.utc)

    calendar = _known_calendar(data_dir)
    cyis = _due_from_calendar(calendar, now)

    if not cyis:
        comp, _ = _nearest_comp(calendar, now)
        cyi = comp.get("cyi") if comp else None
        name = comp.get("name", "unknown") if comp else "unknown"
        return False, cyi, name, "up to date"

    comp = next((c for c in calendar.get("competitions", []) if c.get("cyi") == cyis[0]), {})
    name = comp.get("name", "unknown")
    suffix = f" (+{len(cyis) - 1} more)" if len(cyis) > 1 else ""
    return True, cyis[0], name, f"due{suffix}"


def _comp_phase(start: date, end: date, now_date: date) -> str:
    if start <= now_date <= end + timedelta(days=1):
        return "live"
    if now_date < start:
        days = (start - now_date).days
        if days <= 10:
            return "soon"
        if days <= 30:
            return "upcoming"
        return "distant"
    days = (now_date - end).days
    if days <= 30:
        return "recent"
    return "distant"


def _nearest_comp(calendar: dict, now: datetime) -> tuple[dict, str]:
    """Return the most urgent competition and its phase (urgency > proximity)."""
    override = calendar.get("active_cyi")
    if override is not None:
        comp = next((c for c in calendar.get("competitions", []) if c.get("cyi") == int(override)), {})
        return comp, "live"

    now_date = now.date()
    best_comp: dict | None = None
    best_days: int | None = None
    best_phase = "none"

    for comp in calendar.get("competitions", []):
        start = parse_date(comp.get("start_date", ""))
        end = parse_date(comp.get("end_date", ""))
        if start is None or end is None:
            continue

        phase = _comp_phase(start, end, now_date)
        if phase == "live":
            return comp, "live"

        days = (start - now_date).days if now_date < start else (now_date - end).days
        more_urgent = _PHASE_URGENCY[phase] < _PHASE_URGENCY[best_phase]
        same_urgency_and_closer = (
            _PHASE_URGENCY[phase] == _PHASE_URGENCY[best_phase] and (best_days is None or days < best_days)
        )
        if more_urgent or same_urgency_and_closer:
            best_days = days
            best_comp = comp
            best_phase = phase

    return best_comp or {}, best_phase


def _interval_label(iv: timedelta) -> str:
    total = int(iv.total_seconds())
    if total < 3600:
        return f"{total // 60}m"
    if total < 86400:
        return f"{total // 3600}h"
    return f"{total // 86400}d"


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

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from schedule.active import is_comp_active
from schedule.calendar import load_calendar, parse_date, refresh_calendar
from schedule.phases import PHASE_INTERVALS, PHASE_URGENCY, comp_phase

# GitHub Actions cron is best-effort and routinely skips ticks under load. We track
# last-run per CYI and fire whenever the interval has elapsed (with slack so a run
# that lands a few minutes early still counts).
TOLERANCE = timedelta(minutes=10)


def due_cyis(data_dir: Path, now: datetime | None = None) -> list[int]:
    """Return CYIs whose interval has elapsed since their last recorded run."""
    if now is None:
        now = datetime.now(timezone.utc)
    last_runs = _load_last_runs(data_dir)
    return _due_from_calendar(_known_calendar(data_dir), now, last_runs)


def _due_from_calendar(calendar: dict, now: datetime, last_runs: dict[int, datetime]) -> list[int]:
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
            phase = comp_phase(start, end, now_date)

        interval = PHASE_INTERVALS.get(phase)
        if interval is None:
            continue

        if _is_due(now, last_runs.get(cyi), interval):
            result.append(cyi)

    return result


def _is_due(now: datetime, last_run: datetime | None, interval: timedelta) -> bool:
    """True if interval (minus tolerance) has elapsed since last_run, or never run."""
    if last_run is None:
        return True
    return (now - last_run) >= (interval - TOLERANCE)


def _last_run_path(data_dir: Path) -> Path:
    return Path(data_dir) / "last_run.json"


def _load_last_runs(data_dir: Path) -> dict[int, datetime]:
    path = _last_run_path(data_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict):
            return {}
        return {int(k): datetime.fromisoformat(v) for k, v in raw.items()}
    except (ValueError, KeyError, TypeError):
        return {}


def mark_run(data_dir: Path, cyis: list[int], now: datetime | None = None) -> None:
    """Record that the given CYIs were scraped at `now` (defaults to now UTC)."""
    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    path = _last_run_path(data_dir)
    existing: dict[str, str] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                existing = loaded
        except ValueError:
            existing = {}
    stamp = now.isoformat()
    for cyi in cyis:
        existing[str(cyi)] = stamp
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def should_run(data_dir: Path, now: datetime | None = None) -> bool:
    return bool(due_cyis(data_dir, now))


def run_status(data_dir: Path, now: datetime | None = None) -> tuple[bool, int | None, str, str]:
    """Return (run, cyi, name, reason) for logging."""
    if now is None:
        now = datetime.now(timezone.utc)

    calendar = _known_calendar(data_dir)
    cyis = _due_from_calendar(calendar, now, _load_last_runs(data_dir))

    if not cyis:
        comp, _ = _nearest_comp(calendar, now)
        cyi = comp.get("cyi") if comp else None
        name = comp.get("name", "unknown") if comp else "unknown"
        return False, cyi, name, "up to date"

    comp = next((c for c in calendar.get("competitions", []) if c.get("cyi") == cyis[0]), {})
    name = comp.get("name", "unknown")
    suffix = f" (+{len(cyis) - 1} more)" if len(cyis) > 1 else ""
    return True, cyis[0], name, f"due{suffix}"



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

        phase = comp_phase(start, end, now_date)
        if phase == "live":
            return comp, "live"

        days = (start - now_date).days if now_date < start else (now_date - end).days
        more_urgent = PHASE_URGENCY[phase] < PHASE_URGENCY[best_phase]
        same_urgency_and_closer = (
            PHASE_URGENCY[phase] == PHASE_URGENCY[best_phase] and (best_days is None or days < best_days)
        )
        if more_urgent or same_urgency_and_closer:
            best_days = days
            best_comp = comp
            best_phase = phase

    return best_comp or {}, best_phase



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
    known = _known_cyis(data_dir, calendar)
    if not known:
        return calendar
    return {**calendar, "competitions": [c for c in calendar.get("competitions", []) if c.get("cyi") in known]}


def _known_cyis(data_dir: Path, calendar: dict | None = None) -> set[int]:
    known: set[int] = set()
    index_path = Path(data_dir) / "index.json"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text())
            known.update(c["cyi"] for c in data.get("competitions", []))
        except (ValueError, KeyError):
            pass
    cal = calendar if calendar is not None else load_calendar(data_dir)
    for c in cal.get("competitions", []):
        if c.get("tracked") and c.get("cyi"):
            known.add(c["cyi"])
    return known

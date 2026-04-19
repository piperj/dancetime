import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from schedule.active import is_comp_active
from schedule.calendar import load_calendar


def should_run(data_dir: Path, now: datetime | None = None) -> bool:
    if now is None:
        now = datetime.now(timezone.utc)

    calendar = load_calendar(data_dir)
    active, _ = is_comp_active(calendar, now)
    if active:
        return True

    last_update = _last_update_time(data_dir)
    if last_update is None:
        return True

    return (now - last_update) >= timedelta(hours=23)


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

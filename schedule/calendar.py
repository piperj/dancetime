import json
from datetime import datetime, timezone
from pathlib import Path

from scrape.client import NDCAClient


def refresh_calendar(data_dir: Path, client: NDCAClient) -> dict:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "calendar.json"

    raw = client.fetch_calendar()
    competitions = raw if isinstance(raw, list) else []

    calendar = {
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "competitions": [_normalize(c) for c in competitions],
    }
    path.write_text(json.dumps(calendar, indent=2, ensure_ascii=False))
    return calendar


def load_calendar(data_dir: Path) -> dict:
    path = Path(data_dir) / "calendar.json"
    if not path.exists():
        return {"competitions": []}
    return json.loads(path.read_text())


def _normalize(comp: dict) -> dict:
    return {
        "cyi": comp.get("ID") or comp.get("cyi"),
        "name": comp.get("Name") or comp.get("name", ""),
        "location": comp.get("Location") or comp.get("location", ""),
        "start_date": comp.get("StartDate") or comp.get("start_date", ""),
        "end_date": comp.get("EndDate") or comp.get("end_date", ""),
        "published": bool(comp.get("Published") or comp.get("published", False)),
    }

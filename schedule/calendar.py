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


def parse_date(date_str: str):
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            pass
    return None


def _to_iso(date_str: str) -> str:
    d = parse_date(date_str)
    return d.isoformat() if d is not None else (date_str or "")


def _normalize(comp: dict) -> dict:
    location_raw = comp.get("Approved_Location") or comp.get("location", "")
    location = ", ".join(location_raw) if isinstance(location_raw, list) else (location_raw or "")

    return {
        "cyi": comp.get("Comp_Year_ID") or comp.get("compyear_id") or comp.get("cyi"),
        "competition_id": comp.get("Competition_ID") or comp.get("competition_id"),
        "name": comp.get("Comp_Year_Name") or comp.get("Competition_Name") or comp.get("name", ""),
        "location": location,
        "start_date": _to_iso(comp.get("Start_Date") or comp.get("start_date", "")),
        "end_date": _to_iso(comp.get("End_Date") or comp.get("end_date", "")),
        "published": bool(comp.get("Publish_Results") or comp.get("published", False)),
    }

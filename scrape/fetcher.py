from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from scrape.client import NDCAClient
from scrape.zip_store import list_files, load_json, save_json


def fetch_all(cyi: int, data_dir: Path, force: bool, client: NDCAClient) -> Path:
    zip_path = Path(data_dir) / f"comp_{cyi}.zip"

    if not force and zip_path.exists():
        existing = list_files(zip_path)
        if all(f in existing for f in ("competition_info.json", "results.json", "heatlists.json")):
            fresh_info = client.fetch_competition_info(cyi)
            cached_info = load_json(zip_path, "competition_info.json")
            if fresh_info is not None and _publish_dates(fresh_info) == _publish_dates(cached_info):
                print(f"scrape: no new data for {cyi}")
                return zip_path

    print(f"scrape: downloading competition {cyi}")

    info = client.fetch_competition_info(cyi)
    if info is None:
        raise RuntimeError(f"Could not fetch competition info for cyi={cyi}")
    save_json(info, zip_path, "competition_info.json")

    # Results: letter-prefixed IDs (e.g. "A155")
    results_ids = client.fetch_competitor_list(cyi, "results")
    results = []
    for entry in tqdm(results_ids, desc="results", unit="competitor"):
        cid = entry.get("ID")
        data = client.fetch_competitor_results(cyi, cid, "")
        if data:
            data["_metadata"] = _results_metadata(entry, data)
            results.append(data)

    save_json(
        {"downloaded_at": _now(), "total_competitors": len(results), "results": results},
        zip_path,
        "results.json",
    )

    # Heatlists: numeric IDs (e.g. 155) — separate competitor list
    hl_ids = client.fetch_competitor_list(cyi, "heatlists")
    heatlists = []
    for entry in tqdm(hl_ids, desc="heatlists", unit="competitor"):
        cid = entry.get("ID")
        data = client.fetch_competitor_heatlists(cyi, str(cid), "")
        if data:
            data["_metadata"] = _heatlists_metadata(entry, data)
            heatlists.append(data)

    save_json(
        {"downloaded_at": _now(), "total_competitors": len(heatlists), "heatlists": heatlists},
        zip_path,
        "heatlists.json",
    )

    print(f"scrape: saved {zip_path}")
    return zip_path


def fetch_calendar(data_dir: Path, client: NDCAClient) -> Path:
    from schedule.calendar import refresh_calendar
    refresh_calendar(Path(data_dir), client)
    return Path(data_dir) / "calendar.json"


def _results_metadata(entry: dict, data: dict) -> dict:
    competitor = data.get("Competitor", {})
    name_parts = competitor.get("Name", [])
    name = " ".join(str(p) for p in name_parts) if name_parts else str(entry.get("ID", ""))
    return {
        "competitor_id": str(entry.get("ID", "")),
        "competitor_name": name,
        "studio": str(competitor.get("Keywords", "")),
    }


def _heatlists_metadata(entry: dict, data: dict) -> dict:
    # For heatlists, the top-level result IS the competitor data
    name_parts = data.get("Name") or entry.get("Name", [])
    name = " ".join(str(p) for p in name_parts) if name_parts else str(entry.get("ID", ""))
    return {
        "competitor_id": str(entry.get("ID", "")),
        "competitor_name": name,
        "studio": str(data.get("Keywords", "") or entry.get("Keywords", "")),
    }



def _publish_dates(info: dict) -> dict:
    return info.get("Publish_Dates") or {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

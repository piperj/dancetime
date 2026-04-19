from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from scrape.client import NDCAClient
from scrape.zip_store import list_files, load_json, save_json


def fetch_all(cyi: int, data_dir: Path, force: bool, client: NDCAClient) -> Path:
    zip_path = Path(data_dir) / f"comp_{cyi}.zip"

    if zip_path.exists() and not force:
        existing = list_files(zip_path)
        if all(f in existing for f in ("competition_info.json", "results.json", "heatlists.json")):
            print(f"scrape: using cached {zip_path}")
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
    import json
    out_path = Path(data_dir) / "calendar.json"
    data = client.fetch_calendar()
    competitions = []
    if isinstance(data, list):
        for c in data:
            competitions.append({
                "cyi": c.get("Comp_Year_ID") or c.get("cyi"),
                "name": c.get("Competition_Name") or c.get("name", ""),
                "location": c.get("Location") or c.get("location", ""),
                "start_date": _normalize_date(c.get("Start_Date") or c.get("start_date", "")),
                "end_date": _normalize_date(c.get("End_Date") or c.get("end_date", "")),
                "published": bool(c.get("Results_Published") or c.get("published", False)),
            })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"downloaded_at": _now(), "competitions": competitions},
        indent=2,
        ensure_ascii=False,
    ))
    return out_path


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


def _normalize_date(date_str: str) -> str:
    """Convert MM/DD/YYYY to YYYY-MM-DD."""
    if not date_str:
        return ""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime as dt
            return dt.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date_str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

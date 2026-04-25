import json
from datetime import datetime, timezone
from pathlib import Path

from common import comp_meta, short_name
from heats.parser import HeatInstance


def build_heats_json(
    cyi: int,
    competition_info: dict,
    heat_instances: list[HeatInstance],
    top_matchups: dict,
) -> dict:
    sessions = {}
    competitors = set()
    studios = set()
    competitor_studios: dict[str, str] = {}
    competitor_heats: dict[str, list[str]] = {}

    for instance in heat_instances:
        sessions[instance.session] = instance.session_name
        for entry in instance.entries:
            competitors.add(entry.competitor1)
            if entry.competitor2:
                competitors.add(entry.competitor2)
            if entry.studio:
                studios.add(entry.studio)
                competitor_studios[entry.competitor1] = entry.studio
            competitor_heats.setdefault(entry.competitor1, []).append(instance.key)
            if entry.competitor2:
                competitor_heats.setdefault(entry.competitor2, []).append(instance.key)

    heats_list = [
        {
            "key": h.key,
            "heat_number": h.heat_number,
            "session": h.session,
            "session_name": h.session_name,
            "time": h.time,
            "round": h.round_name,
            "entries": [
                {
                    "couple": e.couple,
                    "competitor1": e.competitor1,
                    "competitor2": e.competitor2,
                    "bib": e.bib,
                    "studio": e.studio,
                    "event": e.event,
                    "result": e.result,
                }
                for e in h.entries
            ],
        }
        for h in heat_instances
    ]

    name, date_range, location = comp_meta(competition_info)
    competition_id = competition_info.get("Competition_ID") or competition_info.get("competition_id")

    return {
        "meta": {
            "cyi": cyi,
            "competition_id": competition_id,
            "name": name,
            "short_name": short_name(name),
            "date_range": date_range,
            "location": location,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "sessions": sessions,
        "heats": heats_list,
        "competitors": sorted(competitors),
        "studios": sorted(studios),
        "competitor_studios": competitor_studios,
        "competitor_heats": competitor_heats,
        "top_matchups": top_matchups,
    }


def write_heats_json(data: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cyi = data["meta"]["cyi"]
    path = out_dir / f"heats_{cyi}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return path

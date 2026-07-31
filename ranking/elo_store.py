import json
from pathlib import Path


def load_ratings(out_dir: Path) -> dict[str, float]:
    path = Path(out_dir) / "elo_ratings.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {k: v["elo"] for k, v in data.get("ratings", {}).items()}


def load_ratings_full(out_dir: Path) -> dict:
    """Return the full elo_ratings.json (last_cyi + per-competitor elo/num_comps/last_cyi)."""
    path = Path(out_dir) / "elo_ratings.json"
    if not path.exists():
        return {"last_cyi": None, "ratings": {}}
    data = json.loads(path.read_text())
    return {"last_cyi": data.get("last_cyi"), "ratings": data.get("ratings", {})}


def save_ratings(
    final_ratings: dict[str, float],
    comp_counts: dict[str, int],
    last_cyi: int,
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "elo_ratings.json"
    # Refuse to truncate a populated ratings file to empty — that's never a
    # legitimate state once the system has run once, and silently allowing it
    # has already cost us cumulative data in production.
    if not final_ratings and path.exists():
        try:
            existing = json.loads(path.read_text()).get("ratings", {})
        except ValueError:
            existing = {}
        if existing:
            raise RuntimeError(
                f"save_ratings refused to truncate {path} "
                f"({len(existing)} competitors → 0); preserving prior data."
            )
    ratings = {
        competitor: {
            "elo": round(elo, 2),
            # Count of comps that have actually contributed a contested (2+ couple)
            # heat to this competitor's elo. Not surfaced anywhere else — it exists
            # so _rewind_cyi (ranking/__init__.py) knows when a rewound comp was the
            # competitor's only one and their rating entry should be dropped rather
            # than left as an orphaned/never-contested phantom.
            "num_comps": comp_counts.get(competitor, 1),
            "last_cyi": last_cyi,
        }
        for competitor, elo in final_ratings.items()
    }
    path.write_text(json.dumps(
        {
            "last_cyi": last_cyi,
            "ratings": ratings,
        },
        indent=2,
        ensure_ascii=False,
    ))
    return path


_EVENT_FIELDS = ("event_name", "round_name", "dance_name")


def load_history(out_dir: Path, cyi: int) -> list:
    """Return the flat per-heat entry list for `cyi`, reconstructed from the
    on-disk {events, names, rows} storage (see write_history_for_cyi) so callers
    don't need to know about the index indirection.

    Competitor/partner names are stored as indices into heats_{cyi}.json's
    `competitors` list (falling back to this file's own small `names` overflow
    table for anyone not found there — see write_history_for_cyi) rather than
    repeated in full on every row, so resolving them here re-reads that file."""
    path = Path(out_dir) / "elo_history" / f"{cyi}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    events = data.get("events", [])
    names = data.get("names", [])
    heats_competitors = load_heats_competitors(out_dir, cyi)

    def _resolve_name(ref):
        if ref is None:
            return ""
        if ref >= 0:
            return heats_competitors[ref] if ref < len(heats_competitors) else ""
        return names[-ref - 1]

    entries = []
    for row in data.get("rows", []):
        event_name, round_name, dance_name = events[row["e"]] if "e" in row else ("", "", "")
        entry = {
            "event_name": event_name,
            "round_name": round_name,
            "dance_name": dance_name,
            "competitor": _resolve_name(row.get("c")),
            "partner": _resolve_name(row.get("p")),
        }
        entry.update({k: v for k, v in row.items() if k not in ("e", "c", "p")})
        entries.append(entry)
    return entries


def load_heats_competitors(out_dir: Path, cyi: int) -> list[str]:
    path = Path(out_dir) / f"heats_{cyi}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text()).get("competitors", [])
    except ValueError:
        return []


def write_history_for_cyi(
    cyi: int,
    heat_history: list,
    out_dir: Path,
    competitor_index: list[str] | None = None,
) -> Path:
    """Store `heat_history` deduplicating (1) the repeated (event_name,
    round_name, dance_name) triple across rows into a small `events` lookup
    table, since the same triple is shared by every couple dancing the same
    heat, and (2) competitor/partner name strings by referencing
    `competitor_index` (heats_{cyi}.json's `competitors` list, which the SPA
    already loads via index.json at startup — a free lookup, unlike fetching
    heats_{cyi}.json itself just for this). Names not found there (or when no
    index is supplied, e.g. isolated tests) fall back to a small local `names`
    overflow table, encoded as a negative reference, so this never crashes on
    a mismatch between the heats and ranking pipelines."""
    history_dir = Path(out_dir) / "elo_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / f"{cyi}.json"

    events: list[list] = []
    event_index: dict[tuple, int] = {}
    name_pos = {name: i for i, name in enumerate(competitor_index or [])}
    names: list[str] = []
    name_overflow: dict[str, int] = {}

    def _name_ref(name):
        if not name:
            return None
        if name in name_pos:
            return name_pos[name]
        if name not in name_overflow:
            name_overflow[name] = len(names)
            names.append(name)
        return -(name_overflow[name] + 1)

    rows = []
    for entry in heat_history:
        key = tuple(entry.get(f, "") for f in _EVENT_FIELDS)
        if key not in event_index:
            event_index[key] = len(events)
            events.append(list(key))
        row = {
            "e": event_index[key],
            "c": _name_ref(entry.get("competitor")),
            "p": _name_ref(entry.get("partner")),
        }
        row.update({
            k: v for k, v in entry.items()
            if k not in (*_EVENT_FIELDS, "competitor", "partner")
        })
        rows.append(row)

    path.write_text(json.dumps(
        {"events": events, "names": names, "rows": rows}, indent=2, ensure_ascii=False,
    ))
    return path

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


def load_history(out_dir: Path) -> dict:
    path = Path(out_dir) / "elo_history.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data.get("history", {})


def write_history(history: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "elo_history.json"
    path.write_text(json.dumps(
        {
            "history": history,
        },
        indent=2,
        ensure_ascii=False,
    ))
    return path


def compute_deltas(
    final_ratings: dict[str, float],
    prior_ratings: dict[str, float],
) -> dict[str, str]:
    deltas = {}
    for competitor, elo in final_ratings.items():
        prior_elo = prior_ratings.get(competitor, elo)
        delta = elo - prior_elo
        sign = "+" if delta >= 0 else ""
        deltas[competitor] = f"{sign}{delta:.1f}"
    return deltas

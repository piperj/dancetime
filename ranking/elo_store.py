import json
from datetime import datetime, timezone
from pathlib import Path


def load_ratings(out_dir: Path) -> dict[str, float]:
    path = Path(out_dir) / "elo_ratings.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {k: v["elo"] for k, v in data.get("ratings", {}).items()}


def save_ratings(
    final_ratings: dict[str, float],
    comp_counts: dict[str, int],
    last_cyi: int,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "elo_ratings.json"
    ratings = {
        competitor: {
            "elo": round(elo, 2),
            "num_comps": comp_counts.get(competitor, 1),
            "last_cyi": last_cyi,
        }
        for competitor, elo in final_ratings.items()
    }
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    if existing.get("last_cyi") == last_cyi and existing.get("ratings") == ratings:
        return
    path.write_text(json.dumps(
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_cyi": last_cyi,
            "ratings": ratings,
        },
        indent=2,
        ensure_ascii=False,
    ))


def load_history(out_dir: Path) -> dict:
    path = Path(out_dir) / "elo_history.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data.get("history", {})


def write_history(history: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "elo_history.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    if existing.get("history") == history:
        return
    path.write_text(json.dumps(
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "history": history,
        },
        indent=2,
        ensure_ascii=False,
    ))


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

import json
from datetime import datetime, timezone
from pathlib import Path


def load_ratings(out_dir: Path) -> dict[str, dict]:
    path = Path(out_dir) / "elo_ratings.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data.get("ratings", {})


def save_ratings(
    final_ratings: dict[str, float],
    prior_ratings: dict[str, dict],
    cyi: int,
    out_dir: Path,
) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "elo_ratings.json"

    merged = dict(prior_ratings)
    for competitor, elo in final_ratings.items():
        prior = prior_ratings.get(competitor, {})
        merged[competitor] = {
            "elo": round(elo, 2),
            "num_comps": prior.get("num_comps", 0) + 1,
            "last_cyi": cyi,
        }

    path.write_text(json.dumps(
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_cyi": cyi,
            "ratings": merged,
        },
        indent=2,
        ensure_ascii=False,
    ))


def compute_deltas(
    final_ratings: dict[str, float],
    prior_ratings: dict[str, dict],
) -> dict[str, str]:
    deltas = {}
    for competitor, elo in final_ratings.items():
        prior_elo = prior_ratings.get(competitor, {}).get("elo", elo)
        delta = elo - prior_elo
        sign = "+" if delta >= 0 else ""
        deltas[competitor] = f"{sign}{delta:.1f}"
    return deltas

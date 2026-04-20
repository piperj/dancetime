import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from common import comp_meta
from ranking.models import DanceResult


def dedup_couples(couples: list[dict]) -> list[dict]:
    """Return couples with mirrored pairs (A&B / B&A) collapsed to the first occurrence."""
    seen: set[tuple] = set()
    out = []
    for c in couples:
        a, b = c["competitor"], c.get("partner") or ""
        key = (a, b) if a < b else (b, a)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def build_ranking_json(
    cyi: int,
    competition_info: dict,
    dance_results: list[DanceResult],
    final_ratings: dict[str, float],
    initial_ratings: dict[str, float],
    assignments: dict[str, str],
    competitor_studios: dict[str, str],
    elo_deltas: dict[str, str],
    elo_params: dict,
) -> dict:
    opponent_counts: dict[str, set] = defaultdict(set)
    heats_per_competitor: dict[str, int] = defaultdict(int)
    for r in dance_results:
        for c in r.competitors:
            heats_per_competitor[c] += 1
            for other in r.competitors:
                if other != c:
                    opponent_counts[c].add(other)

    partners: dict[str, str] = {}
    for r in dance_results:
        partners.update(r.partners)

    leaderboards: dict[str, list] = defaultdict(list)
    for competitor, elo in final_ratings.items():
        label = assignments.get(competitor, "Not Rated")
        partner = partners.get(competitor, "")
        studio = competitor_studios.get(competitor, "")
        partner_studio = competitor_studios.get(partner, "") if partner else ""

        leaderboards[label].append({
            "competitor": competitor,
            "partner": partner,
            "studio": studio,
            "partner_studio": partner_studio,
            "elo": round(elo, 2),
            "elo_delta": elo_deltas.get(competitor, "+0.0"),
            "initial_elo": round(initial_ratings.get(competitor, elo), 2),
            "heats_processed": heats_per_competitor.get(competitor, 0),
            "num_opponents": len(opponent_counts.get(competitor, set())),
        })

    result_leaderboards = {}
    for label, couples in leaderboards.items():
        couples.sort(key=lambda x: x["elo"], reverse=True)
        couples = dedup_couples(couples)
        for rank, couple in enumerate(couples, start=1):
            couple["rank"] = rank
        result_leaderboards[label] = {"label": label, "size": len(couples), "couples": couples}

    name, date_range, location = comp_meta(competition_info)

    all_competitors = sorted(final_ratings.keys())
    studios = sorted({s for s in competitor_studios.values() if s})

    return {
        "meta": {
            "cyi": cyi,
            "name": name,
            "date_range": date_range,
            "location": location,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elo_params": elo_params,
        },
        "leaderboards": result_leaderboards,
        "competitors": all_competitors,
        "studios": studios,
        "competitor_studios": competitor_studios,
    }


def write_ranking_json(data: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cyi = data["meta"]["cyi"]
    path = out_dir / f"ranking_{cyi}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return path

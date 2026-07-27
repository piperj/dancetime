import json
from collections import defaultdict
from pathlib import Path

from common import comp_meta, short_name
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
) -> dict:
    # Keyed by (competitor, partner) rather than just competitor: a competitor
    # can have more than one partner within the same competition (different
    # divisions, pro-am students, etc), and each such partnership needs its
    # own heats/opponents tally rather than one blended per-person total.
    partnership_heats: dict[tuple[str, str], int] = defaultdict(int)
    partnership_opponents: dict[tuple[str, str], set] = defaultdict(set)
    partners_seen: dict[str, set[str]] = defaultdict(set)
    for r in dance_results:
        for c in r.competitors:
            partner = r.partners.get(c, "")
            key = (c, partner)
            partnership_heats[key] += 1
            if partner:
                partners_seen[c].add(partner)
            for other in r.competitors:
                if other != c and other != partner:
                    partnership_opponents[key].add(other)

    leaderboards: dict[str, list] = defaultdict(list)
    for competitor, elo in final_ratings.items():
        label = assignments.get(competitor, "Not Rated")
        studio = competitor_studios.get(competitor, "")
        # Competitors with no couple heats this competition (solo entries only,
        # or no dance_results at all) get a single partner-less row.
        for partner in sorted(partners_seen.get(competitor) or {""}):
            key = (competitor, partner)
            partner_studio = competitor_studios.get(partner, "") if partner else ""

            leaderboards[label].append({
                "competitor": competitor,
                "partner": partner,
                "studio": studio,
                "partner_studio": partner_studio,
                "elo": round(elo, 2),
                "elo_delta": elo_deltas.get(competitor, "+0.0"),
                "initial_elo": round(initial_ratings.get(competitor, elo), 2),
                "heats_processed": partnership_heats.get(key, 0),
                "num_opponents": len(partnership_opponents.get(key, set())),
            })

    result_leaderboards = {}
    for label, couples in leaderboards.items():
        # Tie-break by name so elo ties resolve the same way every run, regardless
        # of upstream dict/set iteration order.
        couples.sort(key=lambda x: (-x["elo"], x["competitor"]))
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
            "short_name": short_name(name),
            "date_range": date_range,
            "location": location,
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

from datetime import datetime
from pathlib import Path

from scrape.zip_store import load_json
from ranking.parser import parse_results
from ranking.skill_rating import get_initial_ratings
from ranking.elo import EloCalculator
from ranking.clusters import assign_leaderboards, build_graph
from ranking.elo_store import (
    compute_deltas, load_history, load_ratings_full, save_ratings, write_history,
)
from ranking.writer import build_ranking_json, write_ranking_json


def _sorted_competitions(data_dir: Path) -> list[tuple[int, Path, str, dict]]:
    comps = []
    for zip_path in data_dir.glob("comp_*.zip"):
        try:
            cyi = int(zip_path.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        info = load_json(zip_path, "competition_info.json")
        raw_date = info.get("Start_Date", "")
        try:
            start = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
        except ValueError:
            start = ""
        comps.append((cyi, zip_path, start, info))
    return sorted(comps, key=lambda x: x[2])


def _rewind_cyi(current_elo: dict, comp_counts: dict, prior_history: dict, cyi: int) -> None:
    """Undo a prior rank of `cyi`: roll competitors back to their elo_before-first-heat
    and decrement their comp_counts. Lets a re-rank produce the same result as the first."""
    entries = prior_history.get(str(cyi), [])
    if not entries:
        return
    first_before: dict[str, float] = {}
    for h in entries:
        c = h.get("competitor")
        if c and c not in first_before:
            first_before[c] = h.get("elo_before")
    for c, elo in first_before.items():
        if c in comp_counts:
            comp_counts[c] -= 1
            if comp_counts[c] <= 0:
                comp_counts.pop(c, None)
                current_elo.pop(c, None)
                continue
        if elo is not None:
            current_elo[c] = elo


def run(args):
    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)

    sorted_comps = _sorted_competitions(data_dir)
    if not sorted_comps:
        print("ranking: no competition zips found")
        return

    incremental = getattr(args, "cyi", None) is not None
    if incremental:
        sorted_comps = [c for c in sorted_comps if c[0] == args.cyi]
        if not sorted_comps:
            print(f"ranking: zip for CYI {args.cyi} not found in {data_dir}; skipping")
            return
        # Guard against re-ranking a not-yet-happened comp from empty results.
        # Without this, save_ratings would replace cumulative data with 0 competitors.
        zip_path = sorted_comps[0][1]
        if not parse_results(load_json(zip_path, "results.json")):
            print(f"ranking: CYI {args.cyi} has no results yet; preserving cumulative ratings")
            return

    prior_history = load_history(out_dir)

    if incremental:
        # Seed accumulator from disk so that comps not in data/raw/ this run survive.
        # In CI, data/raw/ is gitignored — only the just-scraped zips are present.
        prior = load_ratings_full(out_dir)
        current_elo: dict[str, float] = {n: r["elo"] for n, r in prior["ratings"].items()}
        comp_counts: dict[str, int] = {n: r.get("num_comps", 1) for n, r in prior["ratings"].items()}
        # If we've ranked this CYI before, rewind its contribution first so a poll-driven
        # re-rank produces the same result as the first rank.
        for cyi, _, _, _ in sorted_comps:
            _rewind_cyi(current_elo, comp_counts, prior_history, cyi)
        prior_last_cyi = prior.get("last_cyi") or 0
    else:
        current_elo = {}
        comp_counts = {}
        prior_last_cyi = 0

    new_history = {}
    last_cyi = max(prior_last_cyi, sorted_comps[-1][0])

    for cyi, zip_path, start_date, competition_info in sorted_comps:
        results_data = load_json(zip_path, "results.json")
        dance_results = parse_results(results_data)

        if not dance_results:
            if str(cyi) in prior_history:
                new_history[str(cyi)] = prior_history[str(cyi)]
            continue

        initial_ratings = get_initial_ratings(dance_results, current_elo)

        calc = EloCalculator()
        calc.initialize(initial_ratings)
        heat_history = []
        contested_competitors: set = set()
        for result in dance_results:
            changes = calc.process_heat(result)
            for competitor, (elo_before, elo_after) in changes.items():
                heat_history.append({
                    "event_name": result.event_name,
                    "round_name": result.round_name,
                    "dance_name": result.dance_name,
                    "competitor": competitor,
                    "partner": result.partners.get(competitor, ""),
                    "elo_before": round(elo_before, 2),
                    "elo_after": round(elo_after, 2),
                })
                contested_competitors.add(competitor)

        # comp_counts must only credit competitors whose elo actually moved here:
        # _rewind_cyi can only undo what's recorded in heat_history, so crediting
        # someone whose only heats were uncontested/walkovers would double-count
        # them on every re-rank of a still-in-progress comp (nothing to rewind).
        for c in contested_competitors:
            comp_counts[c] = comp_counts.get(c, 0) + 1

        final_ratings = calc.ratings
        new_history[str(cyi)] = heat_history
        current_elo = {**current_elo, **final_ratings}

        graph = build_graph(dance_results)
        assignments = assign_leaderboards(graph)

        competitor_studios = {}
        for comp_data in results_data.get("results", []):
            meta = comp_data.get("_metadata", {})
            name = meta.get("competitor_name", "")
            studio = meta.get("studio", "")
            if name and studio:
                competitor_studios[name] = studio

        elo_deltas = compute_deltas(final_ratings, initial_ratings)

        data = build_ranking_json(
            cyi=cyi,
            competition_info=competition_info,
            dance_results=dance_results,
            final_ratings=final_ratings,
            initial_ratings=initial_ratings,
            assignments=assignments,
            competitor_studios=competitor_studios,
            elo_deltas=elo_deltas,
        )
        path = write_ranking_json(data, out_dir)
        print(f"ranking: wrote {path} ({start_date})")

    # Preserve history for CYIs not present in data/raw/ this run.
    for old_cyi, old_hist in prior_history.items():
        if old_cyi not in new_history:
            new_history[old_cyi] = old_hist

    ratings_path = save_ratings(current_elo, comp_counts, last_cyi, out_dir)
    print(f"ranking: wrote {ratings_path} ({len(current_elo)} competitors)")
    history_path = write_history(new_history, out_dir)
    cyis = sorted(new_history.keys())
    print(f"ranking: wrote {history_path} (CYIs: {', '.join(cyis)})")

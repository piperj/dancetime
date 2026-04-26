from datetime import datetime
from pathlib import Path

from scrape.zip_store import load_json
from ranking.parser import parse_results
from ranking.skill_rating import get_initial_ratings
from ranking.elo import EloCalculator
from ranking.clusters import assign_leaderboards, build_graph
from ranking.elo_store import compute_deltas, load_history, save_ratings, write_history
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


def run(args):
    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)

    sorted_comps = _sorted_competitions(data_dir)
    if not sorted_comps:
        print("ranking: no competition zips found")
        return

    prior_history = load_history(out_dir)
    new_history = {}
    current_elo: dict[str, float] = {}
    comp_counts: dict[str, int] = {}
    last_cyi = sorted_comps[-1][0]

    for cyi, zip_path, start_date, competition_info in sorted_comps:
        results_data = load_json(zip_path, "results.json")
        dance_results = parse_results(results_data)

        if not dance_results:
            if str(cyi) in prior_history:
                new_history[str(cyi)] = prior_history[str(cyi)]
            continue

        initial_ratings = get_initial_ratings(dance_results, current_elo)

        comp_competitors = {c for r in dance_results for c in r.competitors}
        for c in comp_competitors:
            comp_counts[c] = comp_counts.get(c, 0) + 1

        calc = EloCalculator()
        calc.initialize(initial_ratings)
        heat_history = []
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

    save_ratings(current_elo, comp_counts, last_cyi, out_dir)
    write_history(new_history, out_dir)

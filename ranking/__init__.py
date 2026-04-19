from pathlib import Path

from scrape.zip_store import load_json
from ranking.parser import parse_results
from ranking.skill_rating import get_initial_ratings
from ranking.elo import EloCalculator
from ranking.clusters import assign_leaderboards, build_graph
from ranking.elo_store import compute_deltas, load_ratings, save_ratings
from ranking.writer import build_ranking_json, write_ranking_json

ELO_PARAMS = {"k_factor": 32.0, "partner_weight": 0.3}


def run(args):
    zip_path = Path(args.data_dir) / f"comp_{args.cyi}.zip"
    out_dir = Path(args.out_dir)

    competition_info = load_json(zip_path, "competition_info.json")
    results_data = load_json(zip_path, "results.json")

    prior_ratings = load_ratings(out_dir)
    dance_results = parse_results(results_data)

    initial_ratings = get_initial_ratings(dance_results, prior_ratings)

    calc = EloCalculator(**ELO_PARAMS)
    calc.initialize(initial_ratings)
    for result in dance_results:
        calc.process_heat(result)
    final_ratings = calc.ratings

    graph = build_graph(dance_results)
    assignments = assign_leaderboards(graph)

    competitor_studios = {}
    for comp_data in results_data.get("results", []):
        meta = comp_data.get("_metadata", {})
        name = meta.get("competitor_name", "")
        studio = meta.get("studio", "")
        if name and studio:
            competitor_studios[name] = studio

    elo_deltas = compute_deltas(final_ratings, prior_ratings)

    data = build_ranking_json(
        cyi=args.cyi,
        competition_info=competition_info,
        dance_results=dance_results,
        final_ratings=final_ratings,
        initial_ratings=initial_ratings,
        assignments=assignments,
        competitor_studios=competitor_studios,
        elo_deltas=elo_deltas,
        elo_params=ELO_PARAMS,
    )
    path = write_ranking_json(data, out_dir)
    print(f"ranking: wrote {path}")

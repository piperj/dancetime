from pathlib import Path

from scrape.zip_store import load_json
from heats.session_names import infer_session_names
from heats.parser import parse_heatlists
from heats.matchups import compute_top_matchups
from heats.writer import build_heats_json, write_heats_json


def run(args):
    zip_path = Path(args.data_dir) / f"comp_{args.cyi}.zip"
    competition_info = load_json(zip_path, "competition_info.json")
    heatlists_data = load_json(zip_path, "heatlists.json")
    results_data = load_json(zip_path, "results.json")

    heatlists = heatlists_data.get("heatlists", [])
    results = results_data.get("results", [])

    session_names = infer_session_names(heatlists)
    heat_instances = parse_heatlists(heatlists, results, session_names)
    top_matchups = compute_top_matchups(heat_instances)
    data = build_heats_json(args.cyi, competition_info, heat_instances, top_matchups)
    path = write_heats_json(data, Path(args.out_dir))
    print(f"heats: wrote {path}")

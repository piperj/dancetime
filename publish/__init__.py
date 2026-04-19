import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from publish.validator import validate_heats_json, validate_index_json, validate_ranking_json


def run(args):
    out_dir = Path(args.out_dir)
    _update_index(out_dir)

    shutil.copy2(Path("static/index.html"), Path("index.html"))
    print("publish: copied static/index.html → index.html")

    _validate_outputs(out_dir)

    if args.deploy:
        subprocess.run(["wrangler", "pages", "deploy", "public/"], check=True)


def _update_index(out_dir: Path) -> None:
    competitions = []
    for heats_file in sorted(out_dir.glob("heats_*.json")):
        try:
            data = json.loads(heats_file.read_text())
            meta = data.get("meta", {})
            cyi = meta.get("cyi")
            ranking_file = out_dir / f"ranking_{cyi}.json"
            competitions.append({
                "cyi": cyi,
                "name": meta.get("name", ""),
                "date_range": meta.get("date_range", ""),
                "location": meta.get("location", ""),
                "heats_file": f"{out_dir.name}/{heats_file.name}",
                "ranking_file": f"{out_dir.name}/{ranking_file.name}",
            })
        except (json.JSONDecodeError, KeyError):
            pass

    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps(
        {"updated_at": datetime.now(timezone.utc).isoformat(), "competitions": competitions},
        indent=2,
        ensure_ascii=False,
    ))
    print(f"publish: wrote {index_path} ({len(competitions)} competition(s))")


def _validate_outputs(out_dir: Path) -> None:
    index_path = out_dir / "index.json"
    errors = validate_index_json(index_path)
    if errors:
        print(f"publish: WARNING index.json errors: {errors}")

    for heats_file in out_dir.glob("heats_*.json"):
        errors = validate_heats_json(heats_file)
        if errors:
            print(f"publish: WARNING {heats_file.name} errors: {errors}")

    for ranking_file in out_dir.glob("ranking_*.json"):
        errors = validate_ranking_json(ranking_file)
        if errors:
            print(f"publish: WARNING {ranking_file.name} errors: {errors}")

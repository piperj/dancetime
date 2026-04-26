import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import short_name as _short_name
from ranking.elo import ELO_SCALE, PARTNER_WEIGHT_BASE

from publish.validator import validate_heats_json, validate_index_json, validate_ranking_json


def run(args):
    out_dir = Path(args.out_dir)
    _update_index(out_dir)

    _publish_html(Path("static/index.html"), Path("index.html"))
    print("publish: copied static/index.html → index.html")
    shutil.copy2(Path("static/favicon.ico"), Path("favicon.ico"))
    print("publish: copied static/favicon.ico → favicon.ico")

    _validate_outputs(out_dir)

    if args.deploy:
        subprocess.run(["wrangler", "pages", "deploy", "public/"], check=True)


def _publish_html(src: Path, dst: Path) -> None:
    html = src.read_text()
    html = re.sub(r'/\*\[\[ELO_SCALE\]\]\*/ [\d.]+', f'/*[[ELO_SCALE]]*/ {ELO_SCALE}', html)
    html = re.sub(r'/\*\[\[PARTNER_WEIGHT_BASE\]\]\*/ [\d.]+', f'/*[[PARTNER_WEIGHT_BASE]]*/ {PARTNER_WEIGHT_BASE}', html)
    dst.write_text(html)


def _parse_start_date(date_range: str) -> str:
    """Parse 'Nov 28 to 30, 2025' → '2025-11-28'."""
    m = re.match(r'^(\w+)\s+(\d+).*?(\d{4})$', date_range.strip())
    if not m:
        return ''
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").strftime("%Y-%m-%d")
    except ValueError:
        return ''


def _update_index(out_dir: Path) -> None:
    competitions = []
    for heats_file in sorted(out_dir.glob("heats_*.json")):
        try:
            data = json.loads(heats_file.read_text())
            meta = data.get("meta", {})
            cyi = meta.get("cyi")
            if not data.get("heats") and not data.get("competitors"):
                continue
            ranking_file = out_dir / f"ranking_{cyi}.json"
            name = meta.get("name", "")
            competitions.append({
                "cyi": cyi,
                "competition_id": meta.get("competition_id"),
                "name": name,
                "short_name": meta.get("short_name") or _short_name(name),
                "date_range": meta.get("date_range", ""),
                "start_date": _parse_start_date(meta.get("date_range", "")),
                "location": meta.get("location", ""),
                "heats_file": f"{out_dir.name}/{heats_file.name}",
                "ranking_file": f"{out_dir.name}/{ranking_file.name}",
            })
        except (json.JSONDecodeError, KeyError):
            pass

    competitions.sort(key=lambda c: c.get("start_date", ""), reverse=True)

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

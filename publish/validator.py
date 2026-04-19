import json
from pathlib import Path


def validate_heats_json(path: Path) -> list[str]:
    errors = []
    try:
        data = json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return [str(e)]
    for key in ("meta", "sessions", "heats", "competitors", "studios", "competitor_studios", "competitor_heats", "top_matchups"):
        if key not in data:
            errors.append(f"missing key: {key}")
    if "meta" in data:
        for meta_key in ("cyi", "name", "generated_at"):
            if meta_key not in data["meta"]:
                errors.append(f"missing meta.{meta_key}")
    return errors


def validate_ranking_json(path: Path) -> list[str]:
    errors = []
    try:
        data = json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return [str(e)]
    for key in ("meta", "leaderboards", "competitors", "studios", "competitor_studios"):
        if key not in data:
            errors.append(f"missing key: {key}")
    if "meta" in data:
        for meta_key in ("cyi", "name", "generated_at", "elo_params"):
            if meta_key not in data["meta"]:
                errors.append(f"missing meta.{meta_key}")
    return errors


def validate_index_json(path: Path) -> list[str]:
    errors = []
    try:
        data = json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return [str(e)]
    for key in ("updated_at", "competitions"):
        if key not in data:
            errors.append(f"missing key: {key}")
    return errors

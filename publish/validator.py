import json
from pathlib import Path


def _validate_json(path: Path, top_keys: tuple, meta_keys: tuple = ()) -> list[str]:
    errors = []
    try:
        data = json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return [str(e)]
    for key in top_keys:
        if key not in data:
            errors.append(f"missing key: {key}")
    if meta_keys and "meta" in data:
        for meta_key in meta_keys:
            if meta_key not in data["meta"]:
                errors.append(f"missing meta.{meta_key}")
    return errors


def validate_heats_json(path: Path) -> list[str]:
    return _validate_json(
        path,
        ("meta", "sessions", "heats", "competitors", "studios", "competitor_studios", "competitor_heats", "top_matchups"),
        ("cyi", "name", "generated_at"),
    )


def validate_ranking_json(path: Path) -> list[str]:
    return _validate_json(
        path,
        ("meta", "leaderboards", "competitors", "studios", "competitor_studios"),
        ("cyi", "name", "generated_at"),
    )


def validate_index_json(path: Path) -> list[str]:
    return _validate_json(path, ("updated_at", "competitions"))

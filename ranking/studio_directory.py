import json
from pathlib import Path


def load_studio_directory(out_dir: Path) -> dict[str, str]:
    path = Path(out_dir) / "studio_directory.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def merge_studio_directory(out_dir: Path, new_entries: dict[str, str]) -> None:
    """Fill-if-absent merge: a name's studio is sticky once known and never
    overwritten, since studios rarely change and session-feed comps have no
    studio of their own to overwrite it with."""
    directory = load_studio_directory(out_dir)
    changed = False
    for name, studio in new_entries.items():
        if name and studio and name not in directory:
            directory[name] = studio
            changed = True
    if changed:
        path = Path(out_dir) / "studio_directory.json"
        path.write_text(json.dumps(directory, indent=2, ensure_ascii=False, sort_keys=True))


def lookup_studio(directory: dict[str, str], name: str) -> str:
    return directory.get(name, "")

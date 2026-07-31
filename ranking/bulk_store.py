import io
import json
import tarfile
from pathlib import Path

# Bulk (session-feed-backfilled) comps are Python-only consumers — never
# fetched by the SPA (gated by the `tracked` filter in publish._update_index)
# — and written once, never re-ranked. So instead of the tracked-comp layout
# (loose ranking/{cyi}.json + elo_history/{cyi}.json, designed for the SPA's
# lazy per-file fetch), bundle both into one lzma-compressed tar per comp.
# Measured on comp 904's reference-based files: gzip's 32KB window can't see
# across multi-MB files, so bundling gzip'd files buys nothing (12.6x either
# way); lzma's much larger window does capture real cross-file redundancy
# (22.0x bundled vs 21.5x separate) — see thor.md session 2026-07-30 and the
# elo-refactor-phase-a branch chat that followed it.

_MEMBERS = ("ranking.json", "elo_history.json")


def _archive_path(cyi: int, out_dir: Path) -> Path:
    return Path(out_dir) / "bulk" / f"{cyi}.tar.xz"


def write_bulk_archive(cyi: int, ranking_json: dict, elo_history_rows: list, out_dir: Path) -> Path:
    path = _archive_path(cyi, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payloads = {
        "ranking.json": ranking_json,
        "elo_history.json": elo_history_rows,
    }
    with tarfile.open(path, "w:xz") as tar:
        for name in _MEMBERS:
            payload = json.dumps(payloads[name], ensure_ascii=False, indent=2).encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return path


def read_bulk_archive(cyi: int, out_dir: Path) -> dict | None:
    path = _archive_path(cyi, out_dir)
    if not path.exists():
        return None
    result: dict = {}
    with tarfile.open(path, "r:xz") as tar:
        for member in tar.getmembers():
            f = tar.extractfile(member)
            if f is None:
                continue
            key = member.name.removesuffix(".json")
            result[key] = json.loads(f.read())
    return result


def bulk_archive_exists(cyi: int, out_dir: Path) -> bool:
    return _archive_path(cyi, out_dir).exists()

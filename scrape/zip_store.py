import io
import json
import zipfile
from pathlib import Path


def load_json(zip_path: Path, filename: str) -> dict:
    with zipfile.ZipFile(zip_path, "r") as zf:
        return json.loads(zf.read(filename))


def save_json(data: dict, zip_path: Path, filename: str) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode()
    if zip_path.exists():
        # Read existing entries, replace or add the target file
        buf = io.BytesIO()
        with zipfile.ZipFile(zip_path, "r") as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename != filename:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(filename, payload)
        zip_path.write_bytes(buf.getvalue())
    else:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(filename, payload)


def list_files(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        return zf.namelist()

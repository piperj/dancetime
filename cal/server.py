import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path

from schedule.calendar import load_calendar, parse_date


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _auto_scrape(start_str: str, end_str: str, today: date) -> str | None:
    start = parse_date(start_str)
    end = parse_date(end_str)
    if start is None or end is None:
        return None
    if start <= today <= end + timedelta(days=1):
        return "live"
    if timedelta(0) <= (start - today) <= timedelta(days=10):
        return "soon"
    return None


def _has_heats(path: Path) -> bool:
    try:
        return bool(json.loads(path.read_text()).get("competitors"))
    except Exception:
        return False


def _has_ranking(path: Path) -> bool:
    try:
        lbs = json.loads(path.read_text()).get("leaderboards", {})
        return any(lb.get("couples") for lb in lbs.values())
    except Exception:
        return False


def _build_competitions(data_dir: Path) -> dict:
    calendar = load_calendar(data_dir)
    today = datetime.now(timezone.utc).date()
    raw_dir = data_dir / "raw"

    raw_files = {p.name for p in raw_dir.iterdir()} if raw_dir.exists() else set()
    data_files = {p.name for p in data_dir.iterdir() if p.suffix == ".json"}

    comps = []
    for c in calendar.get("competitions", []):
        cyi = c.get("cyi")
        if not cyi:
            continue
        comps.append({
            "cyi": cyi,
            "competition_id": c.get("competition_id"),
            "name": c.get("name", ""),
            "location": c.get("location", ""),
            "start_date": c.get("start_date", ""),
            "end_date": c.get("end_date", ""),
            "published": c.get("published", False),
            "scraped": f"comp_{cyi}.zip" in raw_files,
            "heats": _has_heats(data_dir / f"heats_{cyi}.json"),
            "ranking": _has_ranking(data_dir / f"ranking_{cyi}.json"),
            "auto_scrape": _auto_scrape(c.get("start_date", ""), c.get("end_date", ""), today),
        })
    return {"competitions": comps, "active_cyi": calendar.get("active_cyi")}


def _json_response(handler, data, status=200):
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_chunk(wfile, payload: dict):
    data = (json.dumps(payload) + "\n").encode()
    wfile.write(f"{len(data):x}\r\n".encode())
    wfile.write(data)
    wfile.write(b"\r\n")
    wfile.flush()


def _end_stream(wfile):
    wfile.write(b"0\r\n\r\n")
    wfile.flush()


def _stream_pipeline(wfile, steps: list[tuple[str, list[str]]]):
    try:
        for name, cmd in steps:
            _write_chunk(wfile, {"type": "step", "step": name})
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            for raw_line in proc.stdout:
                text = raw_line.split("\r")[-1].strip()
                if text:
                    _write_chunk(wfile, {"type": "line", "step": name, "text": text})
            proc.wait()
            if proc.returncode != 0:
                _write_chunk(wfile, {"type": "done", "ok": False, "failed_step": name})
                _end_stream(wfile)
                return
        _write_chunk(wfile, {"type": "done", "ok": True})
        _end_stream(wfile)
    except BrokenPipeError:
        pass


def make_handler(data_dir: Path):
    calendar_html = (Path(__file__).parent / "static" / "calendar.html").read_bytes()
    favicon_svg = (Path(__file__).parent / "static" / "favicon.svg").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            if self.path in ("/", "/calendar.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(calendar_html)))
                self.end_headers()
                self.wfile.write(calendar_html)
            elif self.path == "/favicon.svg":
                data = favicon_svg
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif self.path == "/api/competitions":
                _json_response(self, _build_competitions(data_dir))
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path == "/api/publish":
                from datetime import datetime, timezone
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                steps = [
                    ("publish", ["uv", "run", "python", "dancetime_cli.py", "publish"]),
                    ("git add", ["git", "add", "data/", "index.html", "favicon.ico"]),
                    ("git commit", ["bash", "-c",
                        f"git diff --cached --quiet && echo '(nothing to commit)' "
                        f"|| git commit -m 'publish: update data {ts}'"]),
                    ("git push", ["git", "push"]),
                ]
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                _stream_pipeline(self.wfile, steps)
            elif self.path.startswith("/api/scrape/"):
                try:
                    cyi = int(self.path[len("/api/scrape/"):].split("?")[0])
                except ValueError:
                    return self.send_error(400)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                force = b"force=true" in body

                steps = [
                    ("scrape", ["uv", "run", "python", "dancetime_cli.py", "scrape",
                     "--cyi", str(cyi), "--data-dir", str(data_dir / "raw")]
                     + (["--force"] if force else [])),
                    ("heats", ["uv", "run", "python", "dancetime_cli.py", "heats",
                     "--cyi", str(cyi), "--data-dir", str(data_dir / "raw"), "--out-dir", str(data_dir)]),
                    ("ranking", ["uv", "run", "python", "dancetime_cli.py", "ranking",
                     "--cyi", str(cyi), "--data-dir", str(data_dir / "raw"), "--out-dir", str(data_dir)]),
                ]

                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                _stream_pipeline(self.wfile, steps)
            else:
                self.send_error(404)

        def do_PUT(self):
            if self.path == "/api/active":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                cal_path = data_dir / "calendar.json"
                cal = load_calendar(data_dir)
                cyi = body.get("active_cyi")
                if cyi is None:
                    cal.pop("active_cyi", None)
                else:
                    cal["active_cyi"] = int(cyi)
                cal_path.write_text(json.dumps(cal, indent=2, ensure_ascii=False))
                _json_response(self, {"ok": True, "active_cyi": cal.get("active_cyi")})
            else:
                self.send_error(404)

        def do_DELETE(self):
            if self.path.startswith("/api/competitions/"):
                try:
                    cyi = int(self.path[len("/api/competitions/"):])
                except ValueError:
                    return self.send_error(400)
                deleted = []
                for p in [
                    data_dir / "raw" / f"comp_{cyi}.zip",
                    data_dir / f"heats_{cyi}.json",
                    data_dir / f"ranking_{cyi}.json",
                ]:
                    try:
                        p.unlink()
                        deleted.append(p.name)
                    except FileNotFoundError:
                        pass
                _json_response(self, {"ok": True, "deleted": deleted})
            else:
                self.send_error(404)

    return Handler

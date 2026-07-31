import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path

from schedule.calendar import load_calendar, parse_date
from schedule.phases import comp_phase, interval_label


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _auto_scrape(start_str: str, end_str: str, today: date) -> str | None:
    start = parse_date(start_str)
    end = parse_date(end_str)
    if start is None or end is None:
        return None
    return comp_phase(start, end, today)


def _has_heats(path: Path) -> bool:
    try:
        return bool(json.loads(path.read_text()).get("competitors"))
    except Exception:
        return False


def _has_ranking(path: Path) -> bool:
    try:
        return bool(json.loads(path.read_text()).get("couples"))
    except Exception:
        return False


def _set_tracked(data_dir: Path, cyi: int, tracked: bool = True) -> None:
    cal_path = data_dir / "calendar.json"
    cal = load_calendar(data_dir)
    for c in cal.get("competitions", []):
        if c.get("cyi") == cyi:
            c["tracked"] = tracked
            break
    cal_path.write_text(json.dumps(cal, indent=2, ensure_ascii=False))


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
        scraped = f"comp_{cyi}.zip" in raw_files
        has_heats = _has_heats(data_dir / f"heats_{cyi}.json")
        has_ranking = _has_ranking(data_dir / f"ranking_{cyi}.json")
        # data/raw/ is gitignored, so the raw zip alone misses comps whose
        # processed outputs survived a raw-cleanup or fresh checkout.
        scraped = scraped or has_heats or has_ranking
        phase = _auto_scrape(c.get("start_date", ""), c.get("end_date", ""), today)
        end_date = c.get("end_date", "")
        comps.append({
            "cyi": cyi,
            "competition_id": c.get("competition_id"),
            "name": c.get("name", ""),
            "location": c.get("location", ""),
            "start_date": c.get("start_date", ""),
            "end_date": end_date,
            "scraped": scraped,
            "heats": has_heats,
            "ranking": has_ranking,
            "needs_publish": scraped and not has_heats and bool(end_date) and end_date < today.isoformat(),
            "auto_scrape": phase,
            "interval_label": interval_label(phase or "none"),
        })
    return {"competitions": comps}


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


def make_handler(data_dir: Path, port: int):
    calendar_html = (Path(__file__).parent / "static" / "calendar.html").read_bytes()
    favicon_svg = (Path(__file__).parent / "static" / "favicon.svg").read_bytes()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        # Block DNS rebinding: a malicious site whose DNS resolves to 127.0.0.1
        # would still send its own hostname in Host. Reject anything that isn't
        # an exact localhost match.
        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in allowed_hosts

        # Block CSRF: browsers always send Origin on cross-origin POSTs (and on
        # same-origin POSTs in modern browsers). If Origin is present it must
        # match; same-origin form posts without Origin can still fall back to
        # Referer. Requests with neither header are non-browser callers (curl)
        # which can't be weaponized via a victim's session.
        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is not None:
                return origin in allowed_origins
            referer = self.headers.get("Referer", "")
            if referer:
                return any(referer.startswith(o + "/") or referer == o
                           for o in allowed_origins)
            return True

        def do_GET(self):
            if not self._host_ok():
                return self.send_error(403)
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
            if not self._host_ok() or not self._origin_ok():
                return self.send_error(403)
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

                # Mark comp as tracked in calendar.json so CI scheduler sees it.
                _set_tracked(data_dir, cyi)

                steps = [
                    ("scrape", ["uv", "run", "python", "dancetime_cli.py", "scrape",
                     "--cyi", str(cyi), "--data-dir", str(data_dir / "raw")]
                     + (["--force"] if force else [])),
                    ("heats", ["uv", "run", "python", "dancetime_cli.py", "heats",
                     "--cyi", str(cyi), "--data-dir", str(data_dir / "raw"), "--out-dir", str(data_dir)]),
                    ("ranking", ["uv", "run", "python", "dancetime_cli.py", "ranking",
                     "--cyi", str(cyi), "--data-dir", str(data_dir / "raw"), "--out-dir", str(data_dir)]),
                    ("publish", ["uv", "run", "python", "dancetime_cli.py", "publish",
                     "--out-dir", "."]),
                ]

                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                _stream_pipeline(self.wfile, steps)
            else:
                self.send_error(404)

        def do_DELETE(self):
            if not self._host_ok() or not self._origin_ok():
                return self.send_error(403)
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
                _set_tracked(data_dir, cyi, tracked=False)
                _json_response(self, {"ok": True, "deleted": deleted})
            else:
                self.send_error(404)

    return Handler

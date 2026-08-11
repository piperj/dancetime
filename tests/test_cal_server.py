import http.client
import json
import socket
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from cal.server import (
    ThreadingHTTPServer,
    _has_heats,
    _has_ranking,
    _set_tracked,
    make_handler,
)


@pytest.fixture
def running_server(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "calendar.json").write_text(json.dumps({"competitions": []}))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = make_handler(tmp_path, port=port)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield tmp_path, port
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _conn(port):
    return http.client.HTTPConnection("127.0.0.1", port, timeout=5)


# --- _has_heats / _has_ranking ---

def test_has_heats_true(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({"competitors": ["a"]}))
    assert _has_heats(p) is True


def test_has_heats_empty_list(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({"competitors": []}))
    assert _has_heats(p) is False


def test_has_heats_missing_file(tmp_path):
    assert _has_heats(tmp_path / "missing.json") is False


def test_has_heats_malformed_json(tmp_path):
    p = tmp_path / "h.json"
    p.write_text("not json")
    assert _has_heats(p) is False


def test_has_ranking_true(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"couples": ["a"]}))
    assert _has_ranking(p) is True


def test_has_ranking_missing_file(tmp_path):
    assert _has_ranking(tmp_path / "missing.json") is False


# --- _set_tracked ---

def test_set_tracked_updates_matching_cyi(tmp_path):
    (tmp_path / "calendar.json").write_text(
        json.dumps({"competitions": [{"cyi": 5, "tracked": False}]})
    )
    _set_tracked(tmp_path, 5, tracked=True)
    data = json.loads((tmp_path / "calendar.json").read_text())
    assert data["competitions"][0]["tracked"] is True


def test_set_tracked_no_matching_cyi_noop(tmp_path):
    (tmp_path / "calendar.json").write_text(
        json.dumps({"competitions": [{"cyi": 5, "tracked": False}]})
    )
    _set_tracked(tmp_path, 999, tracked=True)
    data = json.loads((tmp_path / "calendar.json").read_text())
    assert data["competitions"][0]["tracked"] is False


# --- GET ---

def test_get_root_serves_html(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.request("GET", "/")
    resp = conn.getresponse()
    assert resp.status == 200
    assert resp.getheader("Content-Type") == "text/html"
    body = resp.read()
    assert b"<html" in body.lower() or len(body) > 0
    conn.close()


def test_get_favicon(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.request("GET", "/favicon.svg")
    resp = conn.getresponse()
    assert resp.status == 200
    assert resp.getheader("Content-Type") == "image/svg+xml"
    resp.read()
    conn.close()


def test_get_api_competitions(running_server):
    tmp_path, port = running_server
    (tmp_path / "calendar.json").write_text(json.dumps({
        "competitions": [{"cyi": 373, "competition_id": 11, "name": "X",
                           "start_date": "2024-01-01", "end_date": "2024-01-03"}]
    }))
    conn = _conn(port)
    conn.request("GET", "/api/competitions")
    resp = conn.getresponse()
    assert resp.status == 200
    data = json.loads(resp.read())
    assert data["competitions"][0]["cyi"] == 373
    conn.close()


def test_get_unknown_path_404(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.request("GET", "/nope")
    resp = conn.getresponse()
    assert resp.status == 404
    resp.read()
    conn.close()


def test_get_bad_host_rejected(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.putrequest("GET", "/", skip_host=True)
    conn.putheader("Host", "evil.example.com")
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 403
    resp.read()
    conn.close()


# --- POST ---

class _FakeProc:
    def __init__(self, lines, returncode=0):
        self.stdout = lines
        self.returncode = returncode

    def wait(self):
        return self.returncode


def test_post_bad_host_rejected(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.putrequest("POST", "/api/publish", skip_host=True)
    conn.putheader("Host", "evil.example.com")
    conn.putheader("Content-Length", "0")
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 403
    resp.read()
    conn.close()


def test_post_bad_origin_rejected(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.putrequest("POST", "/api/publish")
    conn.putheader("Origin", "http://evil.example.com")
    conn.putheader("Content-Length", "0")
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 403
    resp.read()
    conn.close()


def test_post_publish_success_streams_ndjson(running_server):
    tmp_path, port = running_server
    with patch("cal.server.subprocess.Popen") as mock_popen:
        mock_popen.side_effect = [
            _FakeProc(["line one\n", "line two\n"], returncode=0),
            _FakeProc([], returncode=0),
            _FakeProc(["(nothing to commit)\n"], returncode=0),
            _FakeProc([], returncode=0),
        ]
        conn = _conn(port)
        conn.request("POST", "/api/publish", body=b"")
        resp = conn.getresponse()
        assert resp.status == 200
        body = resp.read().decode()
        conn.close()
    events = [json.loads(line) for line in body.splitlines() if line]
    assert events[-1] == {"type": "done", "ok": True}
    assert any(e.get("type") == "line" and e.get("text") == "line one" for e in events)


def test_post_publish_step_failure_reports_failed_step(running_server):
    tmp_path, port = running_server
    with patch("cal.server.subprocess.Popen") as mock_popen:
        mock_popen.return_value = _FakeProc(["boom\n"], returncode=1)
        conn = _conn(port)
        conn.request("POST", "/api/publish", body=b"")
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
    events = [json.loads(line) for line in body.splitlines() if line]
    assert events[-1] == {"type": "done", "ok": False, "failed_step": "publish"}


def test_post_scrape_marks_tracked_and_streams(running_server):
    tmp_path, port = running_server
    (tmp_path / "calendar.json").write_text(
        json.dumps({"competitions": [{"cyi": 42, "tracked": False}]})
    )
    with patch("cal.server.subprocess.Popen") as mock_popen:
        mock_popen.return_value = _FakeProc([], returncode=0)
        conn = _conn(port)
        conn.request("POST", "/api/scrape/42", body=b"force=false")
        resp = conn.getresponse()
        assert resp.status == 200
        resp.read()
        conn.close()
    data = json.loads((tmp_path / "calendar.json").read_text())
    assert data["competitions"][0]["tracked"] is True


def test_post_scrape_bad_cyi_400(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.request("POST", "/api/scrape/not-a-number", body=b"")
    resp = conn.getresponse()
    assert resp.status == 400
    resp.read()
    conn.close()


def test_post_unknown_path_404(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.request("POST", "/api/nope", body=b"")
    resp = conn.getresponse()
    assert resp.status == 404
    resp.read()
    conn.close()


# --- DELETE ---

def test_delete_removes_files_and_untracks(running_server):
    tmp_path, port = running_server
    (tmp_path / "calendar.json").write_text(
        json.dumps({"competitions": [{"cyi": 7, "tracked": True}]})
    )
    (tmp_path / "raw" / "comp_7.zip").write_bytes(b"fake")
    (tmp_path / "heats").mkdir()
    (tmp_path / "heats" / "7.json").write_text("{}")

    conn = _conn(port)
    conn.request("DELETE", "/api/competitions/7")
    resp = conn.getresponse()
    assert resp.status == 200
    data = json.loads(resp.read())
    conn.close()

    assert "raw/comp_7.zip" in data["deleted"]
    assert "heats/7.json" in data["deleted"]
    assert not (tmp_path / "raw" / "comp_7.zip").exists()
    cal = json.loads((tmp_path / "calendar.json").read_text())
    assert cal["competitions"][0]["tracked"] is False


def test_delete_missing_files_still_ok(running_server):
    tmp_path, port = running_server
    (tmp_path / "calendar.json").write_text(
        json.dumps({"competitions": [{"cyi": 8, "tracked": True}]})
    )
    conn = _conn(port)
    conn.request("DELETE", "/api/competitions/8")
    resp = conn.getresponse()
    assert resp.status == 200
    data = json.loads(resp.read())
    conn.close()
    assert data["deleted"] == []


def test_delete_bad_cyi_400(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.request("DELETE", "/api/competitions/not-a-number")
    resp = conn.getresponse()
    assert resp.status == 400
    resp.read()
    conn.close()


def test_delete_unknown_path_404(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.request("DELETE", "/nope")
    resp = conn.getresponse()
    assert resp.status == 404
    resp.read()
    conn.close()


def test_delete_bad_origin_rejected(running_server):
    _, port = running_server
    conn = _conn(port)
    conn.putrequest("DELETE", "/api/competitions/7")
    conn.putheader("Origin", "http://evil.example.com")
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 403
    resp.read()
    conn.close()

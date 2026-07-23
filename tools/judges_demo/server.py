"""Local host for the judges-scores demo page.

Serves the repo root (so the demo page can load /static/judges-scores.js the
same way the real SPA will) with the demo page as the default URL to open.
"""
import threading
import webbrowser
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PORT = 8090


def run(port=DEFAULT_PORT, open_browser=True):
    handler = partial(SimpleHTTPRequestHandler, directory=str(REPO_ROOT))
    httpd = HTTPServer(("127.0.0.1", port), handler)

    url = f"http://127.0.0.1:{port}/tools/judges_demo/index.html"
    print(f"judges_demo: serving {REPO_ROOT} at {url} — Ctrl-C to stop", flush=True)

    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\njudges_demo: stopped")


if __name__ == "__main__":
    run()

import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path


def run(args):
    root = Path(args.root).resolve()
    port = args.port

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    httpd = HTTPServer(("127.0.0.1", port), handler)

    url = f"http://127.0.0.1:{port}/"
    print(f"serve: {root} at {url} — Ctrl-C to stop", flush=True)

    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nserve: stopped")

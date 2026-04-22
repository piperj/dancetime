import threading
import webbrowser
from pathlib import Path

from schedule.calendar import refresh_calendar
from scrape.client import NDCAClient

from .server import ThreadingHTTPServer, make_handler


def run(args):
    data_dir = Path(args.data_dir)
    port = args.port

    print("calendar: refreshing competition list from NDCA...", flush=True)
    try:
        refresh_calendar(data_dir, NDCAClient())
        print("calendar: calendar.json updated", flush=True)
    except Exception as e:
        print(f"calendar: warning — could not refresh calendar: {e}", flush=True)

    handler = make_handler(data_dir)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)

    url = f"http://127.0.0.1:{port}/"
    print(f"calendar: serving at {url} — Ctrl-C to stop", flush=True)

    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\ncalendar: stopped")

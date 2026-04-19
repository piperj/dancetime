from pathlib import Path

from scrape.client import NDCAClient
from scrape.fetcher import fetch_all, fetch_calendar


def run(args):
    client = NDCAClient()
    fetch_all(args.cyi, Path(args.data_dir), args.force, client)
    fetch_calendar(Path(args.data_dir).parent, client)

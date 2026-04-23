import argparse
import sys

import scrape
import heats
import ranking
import publish
import schedule
import cal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dancetime",
        description="Dance competition data pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape", help="Download competition data from NDCA API")
    p_scrape.add_argument("--cyi", type=int, required=True, help="Competition Year ID")
    p_scrape.add_argument("--force", action="store_true", help="Re-download even if cached")
    p_scrape.add_argument("--data-dir", default="data/raw", help="Directory for raw ZIP cache")

    p_heats = sub.add_parser("heats", help="Generate heat schedule JSON")
    p_heats.add_argument("--cyi", type=int, required=True)
    p_heats.add_argument("--data-dir", default="data/raw")
    p_heats.add_argument("--out-dir", default="data")

    p_ranking = sub.add_parser("ranking", help="Generate ELO ranking JSON")
    p_ranking.add_argument("--cyi", type=int, default=None, help="(ignored; all competitions are processed in date order)")
    p_ranking.add_argument("--data-dir", default="data/raw")
    p_ranking.add_argument("--out-dir", default="data")
    p_ranking.add_argument("--iterations", type=int, default=100, help="(reserved for future use)")

    p_publish = sub.add_parser("publish", help="Copy static HTML and validate output")
    p_publish.add_argument("--out-dir", default="data")
    p_publish.add_argument("--deploy", action="store_true", help="Deploy via wrangler")

    p_schedule = sub.add_parser("schedule", help="Check active competition status")
    p_schedule.add_argument("--data-dir", default="data")

    p_cal = sub.add_parser("calendar", help="Local web UI to manage competition schedule")
    p_cal.add_argument("--data-dir", default="data")
    p_cal.add_argument("--port", type=int, default=7331)
    p_cal.add_argument("--no-browser", action="store_true")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "scrape": scrape.run,
        "heats": heats.run,
        "ranking": ranking.run,
        "publish": publish.run,
        "schedule": schedule.run,
        "calendar": cal.run,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()

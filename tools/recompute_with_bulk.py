"""One-off: fully recompute cumulative ELO in true chronological order across
BOTH the tracked-comp zips (data/raw/comp_*.zip) and every already-backfilled
bulk comp (data/bulk/{cyi}.tar.xz) — refetched live from NDCA's session feed,
since a bulk archive only stores the final computed ranking/elo_history, not
the raw placements needed to rerun EloCalculator.

Why this needs its own script rather than just rerunning `ranking`: Phase C's
stable-skip logic (ranking/__init__.py::run()) treats every already-ranked
tracked comp as untouchable — that's the whole point of "stable" comps — and
the regular pipeline has no notion of data/bulk/ at all. A plain `ranking`
rebuild would neither recompute tracked comps nor account for bulk history.
This script resets data/elo_ratings.json and every tracked comp's
data/ranking/{cyi}.json + data/elo_history/{cyi}.json from scratch, processing
every comp (tracked and bulk) together in true chronological order, so a
tracked comp's Ladder numbers finally reflect opponents pulled in from bulk
history.

Expected to run twice: once for this pilot's handful of bulk comps, and again
after the eventual full 25-month backfill (a wider run of
tools/backfill_history.py) — nothing here is pilot-specific, it just recomputes
whatever's in data/raw/ and data/bulk/ at the time it's run.
"""
import argparse
from pathlib import Path

from ranking import rank_dance_results, sorted_competitions
from ranking.bulk_store import write_bulk_archive
from ranking.elo_store import load_heats_competitors, save_ratings, write_history_for_cyi
from ranking.parser import parse_results
from ranking.studio_directory import load_studio_directory, merge_studio_directory
from ranking.writer import build_ranking_json, write_ranking_json
from schedule.calendar import load_calendar
from scrape.client import NDCAClient
from scrape.zip_store import load_json
from tools.backfill_history import _competition_info, fetch_session_dance_results


def _tracked_sources(data_dir: Path) -> list[dict]:
    return [
        {
            "cyi": cyi, "start_date": start_date, "kind": "tracked",
            "zip_path": zip_path, "competition_info": competition_info,
        }
        for cyi, zip_path, start_date, competition_info in sorted_competitions(data_dir)
    ]


def _bulk_sources(out_dir: Path, calendar: dict) -> list[dict]:
    by_cyi = {c["cyi"]: c for c in calendar.get("competitions", [])}
    sources = []
    for path in sorted((Path(out_dir) / "bulk").glob("*.tar.xz")):
        cyi = int(path.name.split(".")[0])
        comp = by_cyi.get(cyi)
        if comp is None:
            continue
        sources.append({"cyi": cyi, "start_date": comp.get("start_date", ""), "kind": "bulk", "comp": comp})
    return sources


def recompute(data_dir: Path, out_dir: Path, client: NDCAClient | None = None) -> None:
    client = client or NDCAClient()
    calendar = load_calendar(out_dir)

    sources = _tracked_sources(data_dir) + _bulk_sources(out_dir, calendar)
    sources.sort(key=lambda s: (s["start_date"], s["cyi"]))
    print(f"recompute: {len(sources)} comps in true chronological order "
          f"({sum(1 for s in sources if s['kind'] == 'tracked')} tracked, "
          f"{sum(1 for s in sources if s['kind'] == 'bulk')} bulk)")

    current_elo: dict[str, float] = {}
    comp_counts: dict[str, int] = {}
    last_cyi = 0
    studio_directory = load_studio_directory(out_dir)

    for source in sources:
        cyi = source["cyi"]
        if source["kind"] == "tracked":
            results_data = load_json(source["zip_path"], "results.json")
            dance_results = parse_results(results_data)
        else:
            results_data = None
            dance_results = fetch_session_dance_results(client, cyi)

        if not dance_results:
            continue

        final_ratings, initial_ratings, heat_history, contested = rank_dance_results(
            dance_results, current_elo
        )
        for c in contested:
            comp_counts[c] = comp_counts.get(c, 0) + 1
        current_elo = {**current_elo, **final_ratings}
        last_cyi = max(last_cyi, cyi)

        if source["kind"] == "tracked":
            competitor_studios = {}
            for comp_data in results_data.get("results", []):
                meta = comp_data.get("_metadata", {})
                name = meta.get("competitor_name", "")
                studio = meta.get("studio", "")
                if name and studio:
                    competitor_studios[name] = studio
            merge_studio_directory(out_dir, competitor_studios)

            ranking_json = build_ranking_json(
                cyi=cyi, competition_info=source["competition_info"],
                dance_results=dance_results, final_ratings=final_ratings,
                initial_ratings=initial_ratings, competitor_studios=competitor_studios,
            )
            write_history_for_cyi(cyi, heat_history, out_dir, load_heats_competitors(out_dir, cyi))
            path = write_ranking_json(ranking_json, out_dir)
            print(f"recompute: [tracked] wrote {path} ({source['start_date']})")
        else:
            competitor_studios = {
                name: studio_directory[name]
                for r in dance_results for name in r.competitors if name in studio_directory
            }
            ranking_json = build_ranking_json(
                cyi=cyi, competition_info=_competition_info(source["comp"]),
                dance_results=dance_results, final_ratings=final_ratings,
                initial_ratings=initial_ratings, competitor_studios=competitor_studios,
            )
            path = write_bulk_archive(cyi, ranking_json, heat_history, out_dir)
            print(f"recompute: [bulk] wrote {path} ({source['start_date']})")

    save_ratings(current_elo, comp_counts, last_cyi, out_dir)
    print(f"recompute: done — {len(current_elo)} competitors in the rebuilt cumulative pool")


def main():
    parser = argparse.ArgumentParser(
        description="One-off: recompute all tracked + bulk comps in true chronological order"
    )
    parser.add_argument("--data-dir", default="data/raw")
    parser.add_argument("--out-dir", default="data")
    args = parser.parse_args()
    recompute(Path(args.data_dir), Path(args.out_dir))


if __name__ == "__main__":
    main()

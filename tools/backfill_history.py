"""Pilot bulk backfill: for each competition series we already track (the
comps shown in the SPA's picker — IGB, Manhattan Dance, SF Open, City Lights
Open, California Star Ball, Hawaii Star Ball), ingest the one prior edition
(~1 year back) via NDCA's session feed, seeding the same cumulative
data/elo_ratings.json the regular `ranking` pipeline uses. This widens the
ELO pool with each tracked comp's own recent history — the comps its actual
opponents came from — rather than a blanket sweep of the whole NDCA calendar.

Scope, deliberately cut down for a first pilot (see the elo-refactor-phase-a
branch chat and /Users/thor/.claude/plans/wobbly-pondering-parnas.md Phase D):
- Only comps already present in data/calendar.json, not a fresh discovery
  crawl — selection is a lookup against that existing list, no new API calls
  beyond the session feed itself.
- Exactly one prior edition per tracked competition_id: the published,
  untracked calendar entry with the same competition_id whose start_date is
  the closest one before that series' earliest currently-tracked edition.
  (Series with no earlier published edition on record are skipped.)
- Output is `data/bulk/{cyi}.tar.xz` (ranking.json + elo_history.json bundled,
  lzma-compressed) — never `data/ranking/{cyi}.json` or `data/heats/{cyi}.json`,
  so bulk comps stay invisible to the SPA (which only reads the tracked-comp
  layout via index.json) while still widening the ELO pool.
- No heats-equivalent (per-heat roster) file is produced in this pilot —
  that's separate scope for offline analysis (analyze_competition.py), not
  needed to prove out session-feed ingestion + the wider ELO pool.
- Studio names are looked up from data/studio_directory.json (best-effort,
  fill-if-absent, populated by the regular `ranking` run from tracked comps)
  since the session feed itself carries no studio field.
"""
import argparse
import time
from collections import defaultdict
from pathlib import Path

from ranking import rank_dance_results
from ranking.bulk_store import bulk_archive_exists, write_bulk_archive
from ranking.elo_store import load_ratings_full, save_ratings
from ranking.session_parser import parse_session_results
from ranking.studio_directory import load_studio_directory
from ranking.writer import build_ranking_json
from scrape.client import NDCAClient
from schedule.calendar import load_calendar


def select_pilot_comps(calendar: dict, editions_back: int = 1) -> list[dict]:
    """One prior edition per already-tracked competition series, `editions_back`
    editions before that series' earliest currently-tracked start_date."""
    competitions = calendar.get("competitions", [])
    tracked = [c for c in competitions if c.get("tracked")]
    tracked_cyis = {c["cyi"] for c in tracked}

    by_id: dict = defaultdict(list)
    for c in competitions:
        by_id[c["competition_id"]].append(c)

    earliest_tracked_start: dict = {}
    for c in tracked:
        cid = c["competition_id"]
        if cid not in earliest_tracked_start or c["start_date"] < earliest_tracked_start[cid]:
            earliest_tracked_start[cid] = c["start_date"]

    pilot = []
    for cid, cutoff in earliest_tracked_start.items():
        prior_editions = sorted(
            (
                c for c in by_id[cid]
                if c["start_date"] < cutoff and c.get("published") and c["cyi"] not in tracked_cyis
            ),
            key=lambda c: c["start_date"],
        )
        if len(prior_editions) >= editions_back:
            pilot.append(prior_editions[-editions_back])

    return sorted(pilot, key=lambda c: (c.get("start_date", ""), c["cyi"]))


def _competition_info(comp: dict) -> dict:
    return {
        "Competition_Name": comp.get("name", ""),
        "Start_Date": comp.get("start_date", ""),
        "End_Date": comp.get("end_date", ""),
        "Location": comp.get("location", ""),
    }


def fetch_session_dance_results(client: NDCAClient, cyi: int) -> list:
    sessions = client.fetch_session_list(cyi)
    if not sessions:
        return []
    session_ids = [
        s["ID"]
        for ballroom in sessions.get("Ballrooms") or []
        for s in ballroom.get("Sessions") or []
    ]
    dance_results = []
    for sid in session_ids:
        items = client.fetch_session(cyi, sid, feed_type=2)
        if not items:
            continue
        dance_results.extend(parse_session_results(items, sid))
    return dance_results


def backfill(
    out_dir: Path, editions_back: int = 1, client: NDCAClient | None = None, sleep: float = 0.2
) -> None:
    client = client or NDCAClient()
    calendar = load_calendar(out_dir)
    pilot_comps = select_pilot_comps(calendar, editions_back)
    print(f"backfill: {len(pilot_comps)} pilot comps ({editions_back} edition(s) back per tracked series)")

    prior = load_ratings_full(out_dir)
    current_elo: dict[str, float] = {n: r["elo"] for n, r in prior["ratings"].items()}
    comp_counts: dict[str, int] = {n: r.get("num_comps", 1) for n, r in prior["ratings"].items()}
    last_cyi = prior.get("last_cyi") or 0

    studio_directory = load_studio_directory(out_dir)

    processed = skipped = empty = 0
    for comp in pilot_comps:
        cyi = comp["cyi"]
        if bulk_archive_exists(cyi, out_dir):
            skipped += 1
            continue

        dance_results = fetch_session_dance_results(client, cyi)
        if not dance_results:
            empty += 1
            continue

        final_ratings, initial_ratings, heat_history, contested = rank_dance_results(
            dance_results, current_elo
        )
        for c in contested:
            comp_counts[c] = comp_counts.get(c, 0) + 1
        current_elo = {**current_elo, **final_ratings}

        competitor_studios = {
            name: studio_directory[name]
            for r in dance_results
            for name in r.competitors
            if name in studio_directory
        }

        ranking_json = build_ranking_json(
            cyi=cyi,
            competition_info=_competition_info(comp),
            dance_results=dance_results,
            final_ratings=final_ratings,
            initial_ratings=initial_ratings,
            competitor_studios=competitor_studios,
        )
        write_bulk_archive(cyi, ranking_json, heat_history, out_dir)
        last_cyi = max(last_cyi, cyi)
        processed += 1
        print(
            f"backfill: {comp['name']} (cyi={cyi}) — {len(dance_results)} results, "
            f"{len(final_ratings)} competitors rated"
        )
        time.sleep(sleep)

    save_ratings(current_elo, comp_counts, last_cyi, out_dir)
    print(
        f"backfill: done — {processed} processed, {skipped} already bulked, "
        f"{empty} had no results yet"
    )


def main():
    parser = argparse.ArgumentParser(description="Pilot bulk-backfill of comps via NDCA's session feed")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument(
        "--editions-back", type=int, default=1,
        help="How many prior editions to backfill per already-tracked competition series",
    )
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds between comps (be polite to NDCA's API)")
    args = parser.parse_args()
    backfill(Path(args.out_dir), args.editions_back, sleep=args.sleep)


if __name__ == "__main__":
    main()

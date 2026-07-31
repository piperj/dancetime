"""Local-only data-consistency audit — not part of CI/GH Actions (this
machine's data/bulk/ isn't committed or available there). Run after
tools/backfill_history.py and/or tools/recompute_with_bulk.py to check the
cumulative state against its sources programmatically, rather than eyeballing
individual numbers.

Checks:
1. data/elo_ratings.json <-> per-comp ranking output (data/ranking/*.json +
   data/bulk/*.tar.xz): every rated competitor traces back to at least one
   comp's computed output, and vice versa.
2. data/elo_ratings.json <-> elo_history (data/elo_history/*.json +
   data/bulk/*.tar.xz): every rated competitor who ever had a real opponent
   (num_opponents > 0 in some comp's ranking output) has at least one
   heat-level history row backing their rating, and vice versa. Walkover-only
   competitors (never had an opponent, so their elo never moved from its
   skill-level seed) are excluded from the forward direction of this check —
   they're expected to have zero elo_history rows, not an orphan.
3. Chronological continuity: for every competitor with 2+ comps, their `elo`
   at the end of one comp must equal their `initial_elo` at the start of
   their next comp (by calendar start_date, across tracked and bulk comps
   together) — this is the exact invariant a chronological-ordering or
   double-counting bug (see thor.md session 2026-07-30's "near-miss") would
   silently break, so it's checked directly rather than inferred.
4. A named watch-list of real competitors (Helen Piper, Johan Piper, Yuriy
   Kuvshynov, Kristina Kuvshynov by default — Johan's own dance circle, easy
   to sanity-check by eye if this flags something) shows real elo movement
   over time. Anyone whose recorded elo never actually changes across their
   own heats is flagged — that's a sign of a plumbing bug (e.g. a rewind or
   chronological-ordering mistake), not a real result.
"""
import argparse
import json
from pathlib import Path

from ranking.bulk_store import read_bulk_archive
from ranking.elo_store import load_history, load_ratings_full
from schedule.calendar import load_calendar

DEFAULT_WATCHLIST = ["Helen Piper", "Johan Piper", "Yuriy Kuvshynov", "Kristina Kuvshynov"]


def _all_comp_cyis(out_dir: Path) -> tuple[set[int], set[int]]:
    ranking_dir = Path(out_dir) / "ranking"
    bulk_dir = Path(out_dir) / "bulk"
    tracked = {int(p.stem) for p in ranking_dir.glob("*.json")} if ranking_dir.exists() else set()
    bulk = {int(p.name.split(".")[0]) for p in bulk_dir.glob("*.tar.xz")} if bulk_dir.exists() else set()
    return tracked, bulk


def _couples_names(couples: list[dict]) -> set[str]:
    names = set()
    for c in couples:
        names.add(c["competitor"])
        if c.get("partner"):
            names.add(c["partner"])
    return names


def _ranking_competitors(out_dir: Path, tracked_cyis: set[int], bulk_cyis: set[int]) -> set[str]:
    names: set[str] = set()
    for cyi in tracked_cyis:
        data = json.loads((Path(out_dir) / "ranking" / f"{cyi}.json").read_text())
        names |= _couples_names(data.get("couples", []))
    for cyi in bulk_cyis:
        archive = read_bulk_archive(cyi, out_dir)
        names |= _couples_names((archive or {}).get("ranking", {}).get("couples", []))
    return names


def _ever_had_opponents(out_dir: Path, tracked_cyis: set[int], bulk_cyis: set[int]) -> set[str]:
    """Competitors whose ranking output shows num_opponents > 0 at least once.
    A rated competitor who only ever walked over (no other couple in their
    division) legitimately has zero elo_history rows — their elo never moved,
    so nothing was ever recorded — and must not be flagged as an orphan."""
    names: set[str] = set()

    def _scan(couples: list[dict]) -> None:
        for c in couples:
            if c.get("num_opponents", 0) > 0:
                names.add(c["competitor"])
                if c.get("partner"):
                    names.add(c["partner"])

    for cyi in tracked_cyis:
        data = json.loads((Path(out_dir) / "ranking" / f"{cyi}.json").read_text())
        _scan(data.get("couples", []))
    for cyi in bulk_cyis:
        archive = read_bulk_archive(cyi, out_dir)
        _scan((archive or {}).get("ranking", {}).get("couples", []))
    return names


def _history_rows_names(rows: list[dict]) -> set[str]:
    names = set()
    for row in rows:
        if row.get("competitor"):
            names.add(row["competitor"])
        if row.get("partner"):
            names.add(row["partner"])
    return names


def _history_competitors(out_dir: Path, tracked_cyis: set[int], bulk_cyis: set[int]) -> set[str]:
    names: set[str] = set()
    for cyi in tracked_cyis:
        names |= _history_rows_names(load_history(out_dir, cyi))
    for cyi in bulk_cyis:
        archive = read_bulk_archive(cyi, out_dir)
        names |= _history_rows_names((archive or {}).get("elo_history", []))
    return names


def _competitor_chronology(
    out_dir: Path, tracked_cyis: set[int], bulk_cyis: set[int], calendar: dict
) -> dict[str, list[tuple]]:
    """Per-competitor list of (start_date, cyi, elo_before_first_heat,
    elo_after_last_heat), one entry per comp they had at least one contested
    heat in, sorted chronologically. Comps missing a calendar start_date are
    skipped entirely — their position in the sequence can't be trusted.

    Built from elo_history (heat-level rows), NOT the ranking output's
    post-dedup `couples` list. dedup_couples collapses a person's own row in
    favor of their partner's whenever the partner wins the (-elo, name)
    tie-break — so for any comp where that happens, the person's own
    initial_elo/elo are simply absent from the couples JSON, even though they
    genuinely danced (and their elo genuinely moved) that comp. Comparing
    against couples rows alone produces false continuity breaks in exactly
    that situation; elo_history has one row per contested heat per person,
    entirely unaffected by dedup, so first/last row per comp gives the true
    elo_before/elo_after for that comp."""
    start_date_by_cyi = {c["cyi"]: c.get("start_date", "") for c in calendar.get("competitions", [])}
    per_comp: dict[str, dict[int, list]] = {}

    def _scan(cyi: int, rows: list[dict]) -> None:
        start_date = start_date_by_cyi.get(cyi, "")
        if not start_date:
            return
        for row in rows:
            name = row.get("competitor")
            if not name:
                continue
            bucket = per_comp.setdefault(name, {})
            if cyi not in bucket:
                bucket[cyi] = [row["elo_before"], row["elo_after"]]
            else:
                bucket[cyi][1] = row["elo_after"]

    for cyi in tracked_cyis:
        _scan(cyi, load_history(out_dir, cyi))
    for cyi in bulk_cyis:
        archive = read_bulk_archive(cyi, out_dir)
        _scan(cyi, (archive or {}).get("elo_history", []))

    trail: dict[str, list[tuple]] = {}
    for name, bucket in per_comp.items():
        entries = [(start_date_by_cyi[cyi], cyi, before, after) for cyi, (before, after) in bucket.items()]
        entries.sort(key=lambda t: (t[0], t[1]))
        trail[name] = entries
    return trail


def _check_continuity(ok: bool, trail: dict[str, list[tuple]], tolerance: float = 0.01) -> bool:
    breaks = 0
    checked = 0
    for name, entries in trail.items():
        for (date_a, cyi_a, _, elo_after_a), (date_b, cyi_b, elo_before_b, _) in zip(entries, entries[1:]):
            checked += 1
            if abs(elo_after_a - elo_before_b) > tolerance:
                breaks += 1
                ok = False
                print(
                    f"FAIL: {name}'s elo after cyi={cyi_a} ({date_a}) was {elo_after_a}, "
                    f"but initial_elo at cyi={cyi_b} ({date_b}) is {elo_before_b}"
                )
    if breaks == 0:
        print(f"OK: chronological continuity — {checked} comp-to-comp transitions checked, none broken")
    return ok


def _watchlist_trail(
    out_dir: Path, tracked_cyis: set[int], bulk_cyis: set[int], names: list[str], calendar: dict
) -> dict[str, list[tuple]]:
    """(cyi, elo_before, elo_after) per contested heat, sorted by calendar
    start_date — cyi is an opaque ID assigned whenever a comp was scraped, not
    a chronological one (e.g. cyi=373 is 2026-01-22, cyi=1049 is 2024-09-25),
    so sorting by raw cyi would show these people's trajectories out of order."""
    start_date_by_cyi = {c["cyi"]: c.get("start_date", "") for c in calendar.get("competitions", [])}
    trail: dict[str, list[tuple]] = {n: [] for n in names}
    for cyi in tracked_cyis:
        for row in load_history(out_dir, cyi):
            if row.get("competitor") in trail:
                trail[row["competitor"]].append((cyi, row["elo_before"], row["elo_after"]))
    for cyi in bulk_cyis:
        archive = read_bulk_archive(cyi, out_dir)
        for row in (archive or {}).get("elo_history", []):
            if row.get("competitor") in trail:
                trail[row["competitor"]].append((cyi, row["elo_before"], row["elo_after"]))
    for entries in trail.values():
        entries.sort(key=lambda t: (start_date_by_cyi.get(t[0], ""), t[0]))
    return trail


def _report_set_diff(ok: bool, label: str, ratings: set, other: set, forward_base: set | None = None) -> bool:
    """forward_base, if given, replaces `ratings` only for the ratings-side
    check (ratings - other) — used to exclude competitors who are legitimately
    expected to be absent from `other` (e.g. walkover-only competitors have no
    elo_history rows) without weakening the reverse direction."""
    missing_from_other = (forward_base if forward_base is not None else ratings) - other
    missing_from_ratings = other - ratings
    if missing_from_other:
        ok = False
        extra = f" (+{len(missing_from_other) - 10} more)" if len(missing_from_other) > 10 else ""
        print(f"FAIL: {len(missing_from_other)} rated competitors missing from {label}: "
              f"{sorted(missing_from_other)[:10]}{extra}")
    if missing_from_ratings:
        ok = False
        extra = f" (+{len(missing_from_ratings) - 10} more)" if len(missing_from_ratings) > 10 else ""
        print(f"FAIL: {len(missing_from_ratings)} competitors in {label} missing from elo_ratings.json: "
              f"{sorted(missing_from_ratings)[:10]}{extra}")
    if not missing_from_other and not missing_from_ratings:
        print(f"OK: elo_ratings.json <-> {label} — {len(ratings)} competitors, 1:1")
    return ok


def verify(out_dir: Path, watchlist: list[str] = DEFAULT_WATCHLIST) -> bool:
    out_dir = Path(out_dir)
    ok = True
    ratings = set(load_ratings_full(out_dir)["ratings"])
    tracked_cyis, bulk_cyis = _all_comp_cyis(out_dir)

    ok = _report_set_diff(ok, "ranking output", ratings, _ranking_competitors(out_dir, tracked_cyis, bulk_cyis))

    # Walkover-only competitors (never had an opponent, so their elo never
    # moved) are excluded from the ratings-side check only — they're expected
    # to have zero elo_history rows, not an orphan. The reverse direction
    # (every history-row name must still be a rated competitor) stays strict.
    ever_contested = _ever_had_opponents(out_dir, tracked_cyis, bulk_cyis)
    ok = _report_set_diff(
        ok, "elo_history", ratings, _history_competitors(out_dir, tracked_cyis, bulk_cyis),
        forward_base=ratings & ever_contested,
    )

    calendar = load_calendar(out_dir)
    chronology = _competitor_chronology(out_dir, tracked_cyis, bulk_cyis, calendar)
    ok = _check_continuity(ok, chronology)

    trail = _watchlist_trail(out_dir, tracked_cyis, bulk_cyis, watchlist, calendar)
    for name in watchlist:
        rows = trail.get(name, [])
        if not rows:
            print(f"WARN: {name} has no elo_history rows at all (never contested, or not yet ingested)")
            continue
        values = {v for _, before, after in rows for v in (before, after)}
        if len(values) <= 1:
            ok = False
            print(f"FAIL: {name}'s rating never changes across {len(rows)} heat(s) — stuck at {values}")
        else:
            print(
                f"OK: {name} — {len(rows)} heat(s) across {len({cyi for cyi, *_ in rows})} comp(s), "
                f"elo {rows[0][1]:.1f} (cyi {rows[0][0]}) -> {rows[-1][2]:.1f} (cyi {rows[-1][0]})"
            )

    return ok


def main():
    parser = argparse.ArgumentParser(description="Local-only data-consistency audit (not for CI)")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--watch", nargs="*", default=DEFAULT_WATCHLIST)
    args = parser.parse_args()
    ok = verify(Path(args.out_dir), args.watch)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

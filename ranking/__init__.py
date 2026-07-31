from datetime import datetime, timezone
from pathlib import Path

from scrape.zip_store import load_json
from ranking.parser import parse_results
from ranking.skill_rating import get_initial_ratings
from ranking.elo import EloCalculator
from ranking.elo_store import (
    compute_deltas, load_history, load_ratings_full, save_ratings, write_history_for_cyi,
)
from ranking.writer import build_ranking_json, write_ranking_json
from schedule.calendar import load_calendar, parse_date
from schedule.phases import comp_phase


def _sorted_competitions(data_dir: Path) -> list[tuple[int, Path, str, dict]]:
    comps = []
    for zip_path in data_dir.glob("comp_*.zip"):
        try:
            cyi = int(zip_path.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        info = load_json(zip_path, "competition_info.json")
        raw_date = info.get("Start_Date", "")
        try:
            start = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
        except ValueError:
            start = ""
        comps.append((cyi, zip_path, start, info))
    # Comps sharing a start_date (concurrent competitions) are broken by the zip's
    # own mtime — a proxy for scrape order, set once and rarely touched again —
    # then by cyi, so ordering is fully deterministic instead of depending on
    # glob()'s filesystem-dependent iteration order.
    return sorted(comps, key=lambda x: (x[2], x[1].stat().st_mtime, x[0]))


def _rewind_cyi(current_elo: dict, comp_counts: dict, out_dir: Path, cyi: int) -> None:
    """Undo a prior rank of `cyi`: roll competitors back to their elo_before-first-heat
    and decrement their comp_counts. Lets a re-rank produce the same result as the first."""
    entries = load_history(out_dir, cyi)
    if not entries:
        return
    first_before: dict[str, float] = {}
    for h in entries:
        c = h.get("competitor")
        if c and c not in first_before:
            first_before[c] = h.get("elo_before")
    for c, elo in first_before.items():
        if c in comp_counts:
            comp_counts[c] -= 1
            if comp_counts[c] <= 0:
                # This was their only contributing comp — drop them entirely rather
                # than leaving an orphaned rating with nothing behind it.
                comp_counts.pop(c, None)
                current_elo.pop(c, None)
                continue
        if elo is not None:
            current_elo[c] = elo


def _comp_phase_for(calendar: dict, cyi: int, today) -> str:
    """Phase of `cyi` per calendar.json's dates. Unknown CYIs/dates default to
    "live" so they're always (re)processed rather than silently skipped."""
    comp = next((c for c in calendar.get("competitions", []) if c.get("cyi") == cyi), None)
    if not comp:
        return "live"
    start = parse_date(comp.get("start_date", ""))
    end = parse_date(comp.get("end_date", ""))
    if start is None or end is None:
        return "live"
    return comp_phase(start, end, today)


def run(args):
    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)

    sorted_comps = _sorted_competitions(data_dir)
    if not sorted_comps:
        print("ranking: no competition zips found")
        return

    incremental = getattr(args, "cyi", None) is not None
    if incremental:
        sorted_comps = [c for c in sorted_comps if c[0] == args.cyi]
        if not sorted_comps:
            print(f"ranking: zip for CYI {args.cyi} not found in {data_dir}; skipping")
            return
        # Guard against re-ranking a not-yet-happened comp from empty results.
        # Without this, save_ratings would replace cumulative data with 0 competitors.
        zip_path = sorted_comps[0][1]
        if not parse_results(load_json(zip_path, "results.json")):
            print(f"ranking: CYI {args.cyi} has no results yet; preserving cumulative ratings")
            return

    # Seed the accumulator from disk. On an incremental run this lets comps not
    # present in data/raw/ this run survive (e.g. CI, where only the just-scraped
    # zip is present). On a full rebuild it lets already-ranked "stable" comps
    # (see _comp_phase_for below) be skipped below instead of reprocessed, since
    # their contribution is already folded into this state from a prior run —
    # "rebuild from scratch" now means "resume from the persisted cumulative
    # state, only reprocessing comps that are live or missing output."
    prior = load_ratings_full(out_dir)
    current_elo: dict[str, float] = {n: r["elo"] for n, r in prior["ratings"].items()}
    comp_counts: dict[str, int] = {n: r.get("num_comps", 1) for n, r in prior["ratings"].items()}
    prior_last_cyi = prior.get("last_cyi") or 0

    last_cyi = max(prior_last_cyi, sorted_comps[-1][0])

    calendar = load_calendar(out_dir)
    today = datetime.now(timezone.utc).date()

    for cyi, zip_path, start_date, competition_info in sorted_comps:
        # Stable comps (results finished changing) are ranked once and never
        # reprocessed — their existing output files are trusted as-is, and their
        # contribution is already reflected in the seeded accumulator above.
        ranking_path = out_dir / f"ranking_{cyi}.json"
        if (
            _comp_phase_for(calendar, cyi, today) != "live"
            and ranking_path.exists()
            and load_history(out_dir, cyi)
        ):
            continue

        # Roll back a prior rank of this CYI (if any) so re-ranking it — whether
        # because it has new results, or because it's being reprocessed after
        # losing its cached output — produces the same result as the first rank.
        _rewind_cyi(current_elo, comp_counts, out_dir, cyi)

        results_data = load_json(zip_path, "results.json")
        dance_results = parse_results(results_data)

        if not dance_results:
            continue

        initial_ratings = get_initial_ratings(dance_results, current_elo)

        calc = EloCalculator()
        calc.initialize(initial_ratings)
        heat_history = []
        contested_competitors: set = set()
        for result in dance_results:
            changes = calc.process_heat(result)
            for competitor, (elo_before, elo_after) in changes.items():
                heat_history.append({
                    "event_name": result.event_name,
                    "round_name": result.round_name,
                    "dance_name": result.dance_name,
                    "competitor": competitor,
                    "partner": result.partners.get(competitor, ""),
                    "elo_before": round(elo_before, 2),
                    "elo_after": round(elo_after, 2),
                })
                contested_competitors.add(competitor)

        # comp_counts must only credit competitors whose elo actually moved here:
        # _rewind_cyi can only undo what's recorded in heat_history, so crediting
        # someone whose only heats were uncontested/walkovers would double-count
        # them on every re-rank of a still-in-progress comp (nothing to rewind).
        for c in contested_competitors:
            comp_counts[c] = comp_counts.get(c, 0) + 1

        final_ratings = calc.ratings
        write_history_for_cyi(cyi, heat_history, out_dir)
        current_elo = {**current_elo, **final_ratings}

        competitor_studios = {}
        for comp_data in results_data.get("results", []):
            meta = comp_data.get("_metadata", {})
            name = meta.get("competitor_name", "")
            studio = meta.get("studio", "")
            if name and studio:
                competitor_studios[name] = studio

        elo_deltas = compute_deltas(final_ratings, initial_ratings)

        data = build_ranking_json(
            cyi=cyi,
            competition_info=competition_info,
            dance_results=dance_results,
            final_ratings=final_ratings,
            initial_ratings=initial_ratings,
            competitor_studios=competitor_studios,
            elo_deltas=elo_deltas,
        )
        path = write_ranking_json(data, out_dir)
        print(f"ranking: wrote {path} ({start_date})")

    ratings_path = save_ratings(current_elo, comp_counts, last_cyi, out_dir)
    print(f"ranking: wrote {ratings_path} ({len(current_elo)} competitors)")

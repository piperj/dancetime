from ranking.models import DanceResult


_BUCKETS: list[tuple[list[str], float]] = [
    (["professional", "rising star"],                      +250),
    (["championship", "pre-champ", "prechamp", "novice"], +150),
    (["gold", "pre-novice"],                               +75),
    (["silver"],                                              0),
    (["bronze", "newcomer"],                               -100),
]


def _classify(event_name: str) -> float | None:
    # Take the lowest matching offset: "Championship Closed Bronze" classifies as
    # bronze (−100), not championship (+150) — "Championship" is the NDCA event
    # format; the actual skill level is the separate word in the name.
    n = event_name.lower()
    matches = [offset for keywords, offset in _BUCKETS if any(k in n for k in keywords)]
    return min(matches) if matches else None


def _best_offsets(results: list[DanceResult]) -> dict[str, float]:
    best: dict[str, float] = {}
    for r in results:
        offset = _classify(r.event_name)
        if offset is None:
            continue
        for c in r.competitors:
            if c not in best or offset > best[c]:
                best[c] = offset
    return best


def get_initial_ratings(
    results: list[DanceResult],
    prior_ratings: dict[str, float],
    base: float = 1500.0,
) -> dict[str, float]:
    offsets = _best_offsets(results)
    competitors = {c for r in results for c in r.competitors}
    return {
        c: prior_ratings[c] if c in prior_ratings else base + offsets.get(c, 0.0)
        for c in competitors
    }

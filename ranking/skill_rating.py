from ranking.models import DanceResult


_BUCKETS: list[tuple[list[str], float]] = [
    (["professional", "rising star"],                      +250),
    (["championship", "pre-champ", "prechamp", "novice"], +150),
    (["gold"],                                              +75),
    (["silver"],                                              0),
    (["bronze", "newcomer"],                               -100),
]


def _classify(event_name: str) -> float | None:
    n = event_name.lower()
    for keywords, offset in _BUCKETS:
        if any(k in n for k in keywords):
            return offset
    return None


def _best_offset(results: list[DanceResult], competitor: str) -> float:
    best: float | None = None
    for r in results:
        if competitor not in r.competitors:
            continue
        offset = _classify(r.event_name)
        if offset is not None and (best is None or offset > best):
            best = offset
    return best if best is not None else 0.0


def get_initial_ratings(
    results: list[DanceResult],
    prior_ratings: dict[str, float],
    base: float = 1500.0,
) -> dict[str, float]:
    competitors = {c for r in results for c in r.competitors}
    return {
        c: prior_ratings[c] if c in prior_ratings else base + _best_offset(results, c)
        for c in competitors
    }

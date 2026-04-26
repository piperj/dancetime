import math

from ranking.models import DanceResult


class EloCalculator:
    def __init__(self, k_factor: float = 32.0, partner_weight: float = 0.3):
        self.k_factor = k_factor
        self.partner_weight = partner_weight
        self._ratings: dict[str, float] = {}

    def initialize(self, ratings: dict[str, float]) -> None:
        self._ratings = dict(ratings)

    @property
    def ratings(self) -> dict[str, float]:
        return dict(self._ratings)

    def get_rating(self, competitor: str) -> float:
        return self._ratings.get(competitor, 1500.0)

    def _couple_rating_with_partner(self, competitor: str, partner: str | None) -> float:
        r_comp = self.get_rating(competitor)
        if partner:
            r_partner = self.get_rating(partner)
            # Blend in partner's rating so that an unrated newcomer dancing with a
            # strong partner doesn't look like an easy target to opponents.
            return (1 - self.partner_weight) * r_comp + self.partner_weight * r_partner
        return r_comp

    def _build_units(
        self, competitors: list[str], result: DanceResult
    ) -> list[tuple[list[str], int, float]]:
        seen: set[str] = set()
        units = []
        for c in competitors:
            if c in seen:
                continue
            partner = result.partners.get(c)
            if partner and partner in result.placements:
                members = [c, partner]
                seen.update(members)
                # Partners share one rating so they're treated as a unit in pairwise
                # comparisons — the couple competes together, not against each other.
                rating = self._couple_rating_with_partner(c, partner)
            else:
                members = [c]
                seen.add(c)
                rating = self.get_rating(c)
            units.append((members, result.placements[c], rating))
        return units

    def process_heat(self, result: DanceResult) -> dict[str, tuple[float, float]]:
        if not result.is_contested():
            return {}

        competitors = [c for c in result.competitors if c in result.placements]
        units = self._build_units(competitors, result)
        if len(units) < 2:
            # Only one couple entered — no opponent to measure against, so no update.
            # Without this guard the two partners would be compared against each other,
            # producing rating drift from a heat where nothing was actually decided.
            return {}

        all_members = [c for unit in units for c in unit[0]]
        before = {c: self.get_rating(c) for c in all_members}
        deltas: dict[str, float] = {c: 0.0 for c in all_members}

        for i, (members_a, place_a, ra) in enumerate(units):
            for members_b, place_b, rb in units[i + 1:]:
                expected_a = 1 / (1 + math.pow(10, (rb - ra) / 400))
                expected_b = 1 - expected_a

                if place_a < place_b:
                    actual_a, actual_b = 1.0, 0.0
                elif place_a > place_b:
                    actual_a, actual_b = 0.0, 1.0
                else:
                    actual_a, actual_b = 0.5, 0.5

                delta_a = self.k_factor * (actual_a - expected_a)
                delta_b = self.k_factor * (actual_b - expected_b)
                # Both partners absorb the full couple delta so they stay in sync;
                # averaging per opponent (below) keeps large fields from amplifying gains.
                for c in members_a:
                    deltas[c] += delta_a
                for c in members_b:
                    deltas[c] += delta_b

        # Divide by opponents faced so a 10-couple heat doesn't move ratings 9× as much
        # as a head-to-head — each pairwise result carries equal weight regardless of field size.
        n = len(units) - 1
        for c in all_members:
            self._ratings[c] = self.get_rating(c) + deltas[c] / max(n, 1)

        return {c: (before[c], self.get_rating(c)) for c in all_members
                if self.get_rating(c) != before[c]}

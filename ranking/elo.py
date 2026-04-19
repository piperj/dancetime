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

    def _couple_rating(self, competitor: str) -> float:
        partner = None
        r_comp = self.get_rating(competitor)
        # Partner weighting requires knowing who the partner is — callers pass it in
        return r_comp

    def _couple_rating_with_partner(self, competitor: str, partner: str | None) -> float:
        r_comp = self.get_rating(competitor)
        if partner:
            r_partner = self.get_rating(partner)
            return (1 - self.partner_weight) * r_comp + self.partner_weight * r_partner
        return r_comp

    def process_heat(self, result: DanceResult) -> None:
        if not result.is_contested():
            return

        competitors = [c for c in result.competitors if c in result.placements]
        if len(competitors) < 2:
            return

        couple_ratings = {
            c: self._couple_rating_with_partner(c, result.partners.get(c))
            for c in competitors
        }

        deltas: dict[str, float] = {c: 0.0 for c in competitors}

        for i, a in enumerate(competitors):
            for b in competitors[i + 1:]:
                place_a = result.placements[a]
                place_b = result.placements[b]

                ra = couple_ratings[a]
                rb = couple_ratings[b]
                expected_a = 1 / (1 + math.pow(10, (rb - ra) / 400))
                expected_b = 1 - expected_a

                if place_a < place_b:
                    actual_a, actual_b = 1.0, 0.0
                elif place_a > place_b:
                    actual_a, actual_b = 0.0, 1.0
                else:
                    actual_a, actual_b = 0.5, 0.5

                deltas[a] += self.k_factor * (actual_a - expected_a)
                deltas[b] += self.k_factor * (actual_b - expected_b)

        n = len(competitors) - 1
        for c in competitors:
            self._ratings[c] = self.get_rating(c) + deltas[c] / max(n, 1)

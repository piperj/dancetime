import math

from ranking.models import DanceResult

# Rating scale for both the expected-score formula and the partner-share
# logistic, so they stay calibrated as ratings drift.
ELO_SCALE: float = 400.0

# Minimum share for the stronger partner (maximum for the weaker).
# Shares are bounded to [PARTNER_WEIGHT_BASE, 1 − PARTNER_WEIGHT_BASE].
# Set to 0.50 for an equal 50/50 split (disables adaptive weighting).
PARTNER_WEIGHT_BASE: float = 0.20

# Maximum rating change per heat (per couple, split between partners by share).
# At 50/50 split each partner moves by K/2 — set to 64 so that equals the old
# per-partner K=32 from the fixed-weight scheme.
K_FACTOR: float = 64.0


class EloCalculator:
    def __init__(self):
        # name → current rating, e.g. {"Johan": 1400.0, "Kristina": 1303.0}
        self._ratings: dict[str, float] = {}

    def initialize(self, ratings: dict[str, float]) -> None:
        self._ratings = dict(ratings)

    @property
    def ratings(self) -> dict[str, float]:
        return dict(self._ratings)

    def get_rating(self, competitor: str) -> float:
        # Unrated newcomers start at 1500.
        return self._ratings.get(competitor, 1500.0)

    def _compute_shares(self, r_comp: float, r_partner: float) -> tuple[float, float]:
        """Return (w_comp, w_partner) biased toward the weaker partner; sum to 1.

        The logistic is the standard ELO expected-score formula applied between
        the two partners instead of between opponents:
          logistic > 0.5 when partner is weaker (r_partner < r_comp)

        Multiplying by (1 - 2×base) and adding base rescales [0,1] → [base, 1-base],
        guaranteeing the stronger partner always keeps at least PARTNER_WEIGHT_BASE
        regardless of the rating gap.

        Setting PARTNER_WEIGHT_BASE = 0.50 collapses the formula to 0.50 always.

        Example: Johan=1400, Kristina=1303
          logistic   = 1/(1 + 10^((1303-1400)/400)) = 0.582
          w_kristina = 0.582 × 0.60 + 0.20 = 0.549  (55%)
          w_johan    = 1 - 0.549             = 0.451  (45%)
        """
        logistic = 1.0 / (1.0 + math.pow(10, (r_partner - r_comp) / ELO_SCALE))
        w_partner = logistic * (1.0 - 2.0 * PARTNER_WEIGHT_BASE) + PARTNER_WEIGHT_BASE
        return 1.0 - w_partner, w_partner

    def _build_units(
        self, competitors: list[str], result: DanceResult
    ) -> list[tuple[list[str], int, float, list[float]]]:
        """Group competitors into couple units for pairwise comparison.

        `competitors` is a flat list of all names in the heat, e.g.:
          ["Johan", "Kristina", "Jennifer", "Ivan"]

        `result.partners` maps every competitor to their partner:
          {"Johan": "Kristina", "Kristina": "Johan",
           "Jennifer": "Ivan",  "Ivan": "Jennifer"}

        Returns one unit per couple:
          (members, placement, couple_rating, per-member shares)

        Example output for the heat above:
          [
            (["Johan", "Kristina"], 1, 1348.0, [0.451, 0.549]),
            (["Jennifer", "Ivan"],  2, 1412.0, [0.523, 0.477]),
          ]

        `seen` is a running guard: when Johan is processed his partner Kristina
        is immediately added to `seen`, so she is skipped when reached in the loop.
        This prevents duplicate units without a separate pre-pass.
        """
        seen: set[str] = set()
        units = []
        for c in competitors:
            if c in seen:
                continue
            partner = result.partners.get(c)
            if partner and partner in result.placements:
                members = [c, partner]
                seen.update(members)
                r_c = self.get_rating(c)
                r_p = self.get_rating(partner)
                w_c, w_p = self._compute_shares(r_c, r_p)
                # Blended couple rating: pulled toward the weaker partner.
                rating = w_c * r_c + w_p * r_p
                shares = [w_c, w_p]
            else:
                # Solo competitor (no partner in this heat).
                # Share 0.5 caps gain at K/2 = 32, consistent with a coupled dancer.
                members = [c]
                seen.add(c)
                rating = self.get_rating(c)
                shares = [0.5]
            units.append((members, result.placements[c], rating, shares))
        return units

    def process_heat(self, result: DanceResult) -> dict[str, tuple[float, float]]:
        """Run ELO for one dance and return {name: (rating_before, rating_after)}.

        Only competitors whose rating changed are included in the return value.
        Returns {} for uncontested heats or heats with only one couple.

        Algorithm:
          1. Build couple units (each unit = one "player" in the ELO match).
          2. Round-robin: compare every pair of units.
             For each pair, compute expected score from blended ratings,
             determine actual outcome from placements, calculate delta.
          3. Split delta across each couple's members by their shares.
          4. Divide accumulated deltas by (N-1) opponents so a large field
             counts the same as a head-to-head.
        """
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

        for i, (members_a, place_a, ra, shares_a) in enumerate(units):
            for members_b, place_b, rb, shares_b in units[i + 1:]:
                expected_a = 1.0 / (1.0 + math.pow(10, (rb - ra) / ELO_SCALE))
                expected_b = 1.0 - expected_a

                if place_a < place_b:
                    actual_a, actual_b = 1.0, 0.0
                elif place_a > place_b:
                    actual_a, actual_b = 0.0, 1.0
                else:
                    actual_a, actual_b = 0.5, 0.5

                delta_a = K_FACTOR * (actual_a - expected_a)
                delta_b = K_FACTOR * (actual_b - expected_b)

                # Split by share: weaker partner absorbs more of the delta.
                for c, share in zip(members_a, shares_a):
                    deltas[c] += delta_a * share
                for c, share in zip(members_b, shares_b):
                    deltas[c] += delta_b * share

        # Divide by opponents faced so a 10-couple heat doesn't move ratings 9× as much
        # as a head-to-head — each pairwise result carries equal weight regardless of field size.
        n = len(units) - 1
        after: dict[str, float] = {}
        for c in all_members:
            after[c] = self.get_rating(c) + deltas[c] / max(n, 1)
            self._ratings[c] = after[c]

        return {c: (before[c], after[c]) for c in all_members if after[c] != before[c]}

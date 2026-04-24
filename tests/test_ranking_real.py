"""Regression tests using City Lights Open 2026 (CYI 373) real data."""
import json
from pathlib import Path

import pytest

from ranking.writer import dedup_couples
from ranking.parser import parse_results
from scrape.zip_store import load_json

RANKING_FILE = Path(__file__).parent.parent / "data" / "ranking_373.json"


def _pair_key(c: dict) -> tuple:
    a, b = c["competitor"], c.get("partner") or ""
    return (a, b) if a < b else (b, a)


def _all_individuals(couples: list[dict]) -> set[str]:
    names: set[str] = set()
    for c in couples:
        names.add(c["competitor"])
        if c.get("partner"):
            names.add(c["partner"])
    return names


@pytest.fixture(scope="module")
def raw_leaderboards():
    return json.loads(RANKING_FILE.read_text())["leaderboards"]


@pytest.fixture(scope="module")
def deduped_leaderboards(raw_leaderboards):
    return {label: dedup_couples(lb["couples"]) for label, lb in raw_leaderboards.items()}


class TestDedupOnCityLightsData:
    def test_no_duplicate_pairs_after_dedup(self, deduped_leaderboards):
        for label, couples in deduped_leaderboards.items():
            keys = [_pair_key(c) for c in couples]
            assert len(keys) == len(set(keys)), (
                f"Leaderboard {label}: duplicate canonical pair after dedup"
            )

    def test_no_individuals_lost_after_dedup(self, raw_leaderboards, deduped_leaderboards):
        for label in raw_leaderboards:
            before = _all_individuals(raw_leaderboards[label]["couples"])
            after = _all_individuals(deduped_leaderboards[label])
            assert before == after, (
                f"Leaderboard {label}: individuals changed — "
                f"lost={before - after}, gained={after - before}"
            )

    def test_written_file_has_no_mirror_pairs(self, raw_leaderboards):
        # The writer calls dedup_couples() before writing, so the file must already
        # be clean — no couple should appear as both (A, B) and (B, A).
        for label, lb in raw_leaderboards.items():
            keys = [_pair_key(c) for c in lb["couples"]]
            assert len(keys) == len(set(keys)), (
                f"Leaderboard {label}: mirror pair found in written file"
            )

    def test_known_pair_appears_exactly_once(self, raw_leaderboards):
        # Grisha Radiush & Agniia Sivkovych must appear exactly once in the file.
        lb_a = raw_leaderboards["A"]["couples"]
        matches = [
            c for c in lb_a
            if c["competitor"] in ("Agniia Sivkovych", "Grisha Radiush")
            and c.get("partner") in ("Agniia Sivkovych", "Grisha Radiush")
        ]
        assert len(matches) == 1

    def test_dedup_is_idempotent(self, raw_leaderboards):
        for label, lb in raw_leaderboards.items():
            once = dedup_couples(lb["couples"])
            twice = dedup_couples(once)
            assert len(once) == len(twice), (
                f"Leaderboard {label}: dedup is not idempotent"
            )

    def test_small_leaderboards_have_one_pair(self, raw_leaderboards):
        # Non-A leaderboards in CYI 373 each contain exactly one couple.
        for label, lb in raw_leaderboards.items():
            if label == "A":
                continue
            assert len(lb["couples"]) == 1, (
                f"Leaderboard {label}: expected 1 pair, got {len(lb['couples'])}"
            )


ZIP_FILE = Path(__file__).parent.parent / "data" / "raw" / "comp_373.zip"


@pytest.fixture(scope="module")
def parsed_results_373():
    if not ZIP_FILE.exists():
        pytest.skip(f"raw data not available: {ZIP_FILE}")
    results_data = load_json(ZIP_FILE, "results.json")
    return parse_results(results_data)


class TestHeat628SemiFinalPlacements:
    """Heat 628 — Adult Amateur Open A Int'l Latin Semi-Final, 11 couples.

    Chrystal Chen & Oscar Adrian Rodriguez placed 7th.
    Lawrence Yen & Ying-chieh Chi placed 11th (Contested — tie result in NDCA data).
    The contested entry uses Result: ["TIE", "TIE", "11"]; the parser must take the
    last element, not the first, or Lawrence's placement is silently dropped, costing
    Chrystal & Oscar the ELO credit for finishing above them.
    """

    def _find_semifinal(self, results):
        for r in results:
            if (
                "Latin" in r.event_name
                and "Open" in r.event_name
                and "Semi" in r.round_name
                and "Chrystal Chen" in r.competitors
            ):
                return r
        return None

    def test_chrystal_chen_placed_7th(self, parsed_results_373):
        r = self._find_semifinal(parsed_results_373)
        assert r is not None, "Semi-final result for Chrystal Chen not found"
        assert r.placements.get("Chrystal Chen") == 7

    def test_oscar_rodriguez_placed_7th(self, parsed_results_373):
        r = self._find_semifinal(parsed_results_373)
        assert r is not None
        assert r.placements.get("Oscar Adrian Rodriguez") == 7

    def test_last_place_couple_placement(self, parsed_results_373):
        # Lawrence Yen & Ying-chieh Chi finished last overall (11th per Circuit.Place),
        # but the ranking parser works per-dance using judge Marks: in Cha Cha they
        # scored 10th (0 judge marks out of 9). The ELO credit depends on having a
        # concrete placement, not the exact value.
        r = self._find_semifinal(parsed_results_373)
        assert r is not None
        assert r.placements.get("Lawrence Yen") == 10

    def test_chrystal_beats_contested_couple_in_elo(self, parsed_results_373):
        from ranking.elo import EloCalculator
        r = self._find_semifinal(parsed_results_373)
        assert r is not None
        calc = EloCalculator()
        calc.initialize({c: 1500.0 for c in r.competitors})
        calc.process_heat(r)
        assert calc.get_rating("Chrystal Chen") > calc.get_rating("Lawrence Yen")

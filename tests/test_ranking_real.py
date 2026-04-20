"""Regression tests for dedup_couples() using City Lights Open 2026 (CYI 373)."""
import json
from pathlib import Path

import pytest

from ranking.writer import dedup_couples

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

    def test_mirror_entries_are_removed(self, raw_leaderboards, deduped_leaderboards):
        for label in raw_leaderboards:
            original = raw_leaderboards[label]["couples"]
            deduped = deduped_leaderboards[label]
            assert len(deduped) < len(original), (
                f"Leaderboard {label}: expected dedup to reduce entry count "
                f"(original={len(original)}, deduped={len(deduped)})"
            )

    def test_leaderboard_A_has_no_duplicate_pairs(self, deduped_leaderboards):
        couples = deduped_leaderboards["A"]
        keys = [_pair_key(c) for c in couples]
        assert len(keys) == len(set(keys))

    def test_known_mirror_pair_appears_exactly_once(self, raw_leaderboards, deduped_leaderboards):
        # Agniia Sivkovych & Grisha Radiush appear as two mirror entries in the raw data
        lb_a_raw = raw_leaderboards["A"]["couples"]
        raw_matches = [
            c for c in lb_a_raw
            if c["competitor"] in ("Agniia Sivkovych", "Grisha Radiush")
            and c.get("partner") in ("Agniia Sivkovych", "Grisha Radiush")
        ]
        assert len(raw_matches) == 2, "Precondition: both mirror entries must exist in raw data"

        deduped_matches = [
            c for c in deduped_leaderboards["A"]
            if c["competitor"] in ("Agniia Sivkovych", "Grisha Radiush")
            and c.get("partner") in ("Agniia Sivkovych", "Grisha Radiush")
        ]
        assert len(deduped_matches) == 1

    def test_dedup_is_idempotent(self, raw_leaderboards):
        for label, lb in raw_leaderboards.items():
            once = dedup_couples(lb["couples"])
            twice = dedup_couples(once)
            assert len(once) == len(twice), (
                f"Leaderboard {label}: dedup is not idempotent"
            )

    def test_small_leaderboards_each_reduce_to_one_pair(self, deduped_leaderboards):
        # All non-A leaderboards in CYI 373 have exactly 2 entries (one mirror pair)
        for label, couples in deduped_leaderboards.items():
            if label == "A":
                continue
            assert len(couples) == 1, (
                f"Leaderboard {label}: expected 1 unique pair, got {len(couples)}"
            )

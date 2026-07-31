import json

from ranking.bulk_store import write_bulk_archive
from ranking.elo_store import write_history_for_cyi
from ranking.writer import write_ranking_json
from tools.verify_consistency import verify


def _write_tracked(out_dir, cyi, competitor, partner, elo, history_rows, initial_elo=1500.0):
    write_ranking_json(
        {
            "meta": {"cyi": cyi},
            "couples": [{"competitor": competitor, "partner": partner, "elo": elo,
                         "initial_elo": initial_elo, "heats_processed": 1, "num_opponents": 1, "rank": 1}],
        },
        out_dir,
    )
    # load_history() resolves name indices against data/heats/{cyi}.json's own
    # "competitors" list (not whatever list was passed at write time) — needs
    # to exist on disk for the round-trip to resolve names instead of "".
    heats_dir = out_dir / "heats"
    heats_dir.mkdir(parents=True, exist_ok=True)
    (heats_dir / f"{cyi}.json").write_text(json.dumps({"competitors": [competitor, partner]}))
    write_history_for_cyi(cyi, history_rows, out_dir, [competitor, partner])


def _write_ratings(out_dir, ratings: dict):
    (out_dir / "elo_ratings.json").write_text(json.dumps({
        "last_cyi": 999,
        "ratings": {name: {"elo": elo, "num_comps": 1, "last_cyi": 999} for name, elo in ratings.items()},
    }))


class TestConsistentData:
    def test_fully_consistent_data_passes(self, tmp_path, capsys):
        _write_tracked(tmp_path, 1, "Alice Adams", "Bob Baker", 1520.0, [
            {"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
             "competitor": "Alice Adams", "partner": "Bob Baker", "elo_before": 1500.0, "elo_after": 1520.0},
        ])
        _write_ratings(tmp_path, {"Alice Adams": 1520.0, "Bob Baker": 1520.0})

        assert verify(tmp_path, watchlist=[]) is True
        out = capsys.readouterr().out
        assert "FAIL" not in out


class TestWalkoverOnly:
    def test_walkover_only_competitor_is_not_flagged(self, tmp_path, capsys):
        # num_opponents=0: this couple only ever walked over, so their elo
        # never moved and they legitimately have no elo_history rows.
        write_ranking_json(
            {
                "meta": {"cyi": 1},
                "couples": [{"competitor": "Alice Adams", "partner": "Bob Baker", "elo": 1500.0,
                             "initial_elo": 1500.0, "heats_processed": 3, "num_opponents": 0, "rank": 1}],
            },
            tmp_path,
        )
        write_history_for_cyi(1, [], tmp_path, ["Alice Adams", "Bob Baker"])
        _write_ratings(tmp_path, {"Alice Adams": 1500.0, "Bob Baker": 1500.0})

        assert verify(tmp_path, watchlist=[]) is True
        out = capsys.readouterr().out
        assert "FAIL" not in out

    def test_contested_competitor_still_missing_history_is_flagged(self, tmp_path, capsys):
        # num_opponents=1 but no elo_history row backing it — a real orphan,
        # unlike the walkover case above.
        write_ranking_json(
            {
                "meta": {"cyi": 1},
                "couples": [{"competitor": "Alice Adams", "partner": "Bob Baker", "elo": 1520.0,
                             "initial_elo": 1500.0, "heats_processed": 3, "num_opponents": 1, "rank": 1}],
            },
            tmp_path,
        )
        write_history_for_cyi(1, [], tmp_path, ["Alice Adams", "Bob Baker"])
        _write_ratings(tmp_path, {"Alice Adams": 1520.0, "Bob Baker": 1520.0})

        assert verify(tmp_path, watchlist=[]) is False
        out = capsys.readouterr().out
        assert "Alice Adams" in out


class TestOrphanDetection:
    def test_rated_competitor_missing_from_ranking_output_fails(self, tmp_path, capsys):
        _write_tracked(tmp_path, 1, "Alice Adams", "Bob Baker", 1520.0, [
            {"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
             "competitor": "Alice Adams", "partner": "Bob Baker", "elo_before": 1500.0, "elo_after": 1520.0},
        ])
        # Ratings claims a third person who never shows up in any ranking output.
        _write_ratings(tmp_path, {"Alice Adams": 1520.0, "Bob Baker": 1520.0, "Ghost Person": 1500.0})

        assert verify(tmp_path, watchlist=[]) is False
        out = capsys.readouterr().out
        assert "Ghost Person" in out
        assert "FAIL" in out

    def test_competitor_in_history_missing_from_ratings_fails(self, tmp_path, capsys):
        _write_tracked(tmp_path, 1, "Alice Adams", "Bob Baker", 1520.0, [
            {"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
             "competitor": "Alice Adams", "partner": "Bob Baker", "elo_before": 1500.0, "elo_after": 1520.0},
            {"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
             "competitor": "Bob Baker", "partner": "Alice Adams", "elo_before": 1500.0, "elo_after": 1480.0},
        ])
        # Ratings is missing Bob entirely even though he has history rows.
        _write_ratings(tmp_path, {"Alice Adams": 1520.0})

        assert verify(tmp_path, watchlist=[]) is False
        out = capsys.readouterr().out
        assert "Bob Baker" in out


class TestBulkComps:
    def test_bulk_archive_included_in_consistency_check(self, tmp_path, capsys):
        write_bulk_archive(
            200,
            {"meta": {"cyi": 200}, "couples": [
                {"competitor": "Carol Chen", "partner": "Dan Diaz", "elo": 1510.0,
                 "initial_elo": 1500.0, "heats_processed": 1, "num_opponents": 1, "rank": 1},
            ]},
            [{"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
              "competitor": "Carol Chen", "partner": "Dan Diaz", "elo_before": 1500.0, "elo_after": 1510.0}],
            tmp_path,
        )
        _write_ratings(tmp_path, {"Carol Chen": 1510.0, "Dan Diaz": 1510.0})

        assert verify(tmp_path, watchlist=[]) is True
        assert "FAIL" not in capsys.readouterr().out


class TestWatchlist:
    def test_static_rating_is_flagged(self, tmp_path, capsys):
        _write_tracked(tmp_path, 1, "Helen Piper", "Yuriy Kuvshynov", 1500.0, [
            {"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
             "competitor": "Helen Piper", "partner": "Yuriy Kuvshynov",
             "elo_before": 1500.0, "elo_after": 1500.0},
        ])
        _write_ratings(tmp_path, {"Helen Piper": 1500.0, "Yuriy Kuvshynov": 1500.0})

        assert verify(tmp_path, watchlist=["Helen Piper"]) is False
        out = capsys.readouterr().out
        assert "never changes" in out

    def test_real_movement_is_not_flagged(self, tmp_path, capsys):
        _write_tracked(tmp_path, 1, "Helen Piper", "Yuriy Kuvshynov", 1520.0, [
            {"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
             "competitor": "Helen Piper", "partner": "Yuriy Kuvshynov",
             "elo_before": 1500.0, "elo_after": 1520.0},
        ])
        _write_ratings(tmp_path, {"Helen Piper": 1520.0, "Yuriy Kuvshynov": 1520.0})

        assert verify(tmp_path, watchlist=["Helen Piper"]) is True
        out = capsys.readouterr().out
        assert "OK: Helen Piper" in out

    def test_absent_watchlist_competitor_warns_but_does_not_fail(self, tmp_path, capsys):
        _write_tracked(tmp_path, 1, "Alice Adams", "Bob Baker", 1520.0, [
            {"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
             "competitor": "Alice Adams", "partner": "Bob Baker", "elo_before": 1500.0, "elo_after": 1520.0},
        ])
        _write_ratings(tmp_path, {"Alice Adams": 1520.0, "Bob Baker": 1520.0})

        assert verify(tmp_path, watchlist=["Nonexistent Person"]) is True
        out = capsys.readouterr().out
        assert "WARN: Nonexistent Person" in out


def _write_tracked_comp(out_dir, cyi, competitor, partner, elo_before, elo_after):
    """Continuity fixture: a tracked comp with one contested heat, consistent
    across ranking output (couples row) and elo_history — the continuity
    check itself reads elo_history, but ranking output must exist too since
    that's what makes a cyi count as "tracked" at all (_all_comp_cyis)."""
    write_ranking_json(
        {
            "meta": {"cyi": cyi},
            "couples": [{"competitor": competitor, "partner": partner, "elo": elo_after,
                         "initial_elo": elo_before, "heats_processed": 1, "num_opponents": 1, "rank": 1}],
        },
        out_dir,
    )
    heats_dir = out_dir / "heats"
    heats_dir.mkdir(parents=True, exist_ok=True)
    (heats_dir / f"{cyi}.json").write_text(json.dumps({"competitors": [competitor, partner]}))
    write_history_for_cyi(
        cyi,
        [{"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
          "competitor": competitor, "partner": partner, "elo_before": elo_before, "elo_after": elo_after}],
        out_dir, [competitor, partner],
    )


def _write_calendar(out_dir, entries: dict):
    (out_dir / "calendar.json").write_text(json.dumps({
        "competitions": [{"cyi": cyi, "start_date": date} for cyi, date in entries.items()],
    }))


class TestChronologicalContinuity:
    def test_continuous_chain_across_tracked_comps_passes(self, tmp_path, capsys):
        _write_tracked_comp(tmp_path, 1, "Alice Adams", "Bob Baker", 1500.0, 1520.0)
        _write_tracked_comp(tmp_path, 2, "Alice Adams", "Bob Baker", 1520.0, 1540.0)
        _write_calendar(tmp_path, {1: "2024-01-01", 2: "2024-06-01"})
        _write_ratings(tmp_path, {"Alice Adams": 1540.0, "Bob Baker": 1540.0})

        assert verify(tmp_path, watchlist=[]) is True
        out = capsys.readouterr().out
        assert "FAIL" not in out
        assert "continuity" in out

    def test_broken_chain_is_flagged(self, tmp_path, capsys):
        _write_tracked_comp(tmp_path, 1, "Alice Adams", "Bob Baker", 1500.0, 1520.0)
        _write_tracked_comp(tmp_path, 2, "Alice Adams", "Bob Baker", 1600.0, 1640.0)
        _write_calendar(tmp_path, {1: "2024-01-01", 2: "2024-06-01"})
        _write_ratings(tmp_path, {"Alice Adams": 1640.0, "Bob Baker": 1640.0})

        assert verify(tmp_path, watchlist=[]) is False
        out = capsys.readouterr().out
        assert "Alice Adams" in out
        assert "cyi=1" in out and "cyi=2" in out

    def test_chain_spans_tracked_and_bulk_comps(self, tmp_path, capsys):
        _write_tracked_comp(tmp_path, 1, "Carol Chen", "Dan Diaz", 1500.0, 1480.0)
        write_bulk_archive(
            2,
            {"meta": {"cyi": 2}, "couples": [
                {"competitor": "Carol Chen", "partner": "Dan Diaz", "elo": 1510.0,
                 "initial_elo": 1480.0, "heats_processed": 1, "num_opponents": 1, "rank": 1},
            ]},
            [{"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
              "competitor": "Carol Chen", "partner": "Dan Diaz", "elo_before": 1480.0, "elo_after": 1510.0}],
            tmp_path,
        )
        _write_calendar(tmp_path, {1: "2024-01-01", 2: "2024-06-01"})
        _write_ratings(tmp_path, {"Carol Chen": 1510.0, "Dan Diaz": 1510.0})

        assert verify(tmp_path, watchlist=[]) is True
        assert "FAIL" not in capsys.readouterr().out

    def test_bulk_to_tracked_break_is_flagged(self, tmp_path, capsys):
        write_bulk_archive(
            1,
            {"meta": {"cyi": 1}, "couples": [
                {"competitor": "Carol Chen", "partner": "Dan Diaz", "elo": 1510.0,
                 "initial_elo": 1500.0, "heats_processed": 1, "num_opponents": 1, "rank": 1},
            ]},
            [{"event_name": "E", "round_name": "Final", "dance_name": "Final (Combined)",
              "competitor": "Carol Chen", "partner": "Dan Diaz", "elo_before": 1500.0, "elo_after": 1510.0}],
            tmp_path,
        )
        _write_tracked_comp(tmp_path, 2, "Carol Chen", "Dan Diaz", 1500.0, 1550.0)
        _write_calendar(tmp_path, {1: "2024-01-01", 2: "2024-06-01"})
        _write_ratings(tmp_path, {"Carol Chen": 1550.0, "Dan Diaz": 1550.0})

        assert verify(tmp_path, watchlist=[]) is False
        out = capsys.readouterr().out
        assert "Carol Chen" in out

    def test_comp_missing_from_calendar_is_skipped_not_a_false_positive(self, tmp_path, capsys):
        _write_tracked_comp(tmp_path, 1, "Alice Adams", "Bob Baker", 1500.0, 1520.0)
        _write_tracked_comp(tmp_path, 2, "Alice Adams", "Bob Baker", 1999.0, 1999.0)
        _write_calendar(tmp_path, {1: "2024-01-01"})
        _write_ratings(tmp_path, {"Alice Adams": 1999.0, "Bob Baker": 1999.0})

        assert verify(tmp_path, watchlist=[]) is True
        assert "FAIL" not in capsys.readouterr().out

    def test_multi_heat_same_comp_uses_first_before_and_last_after(self, tmp_path, capsys):
        # Alice dances two heats (different partners) within comp 1 — her
        # comp-level elo_before must be the FIRST heat's elo_before and her
        # elo_after must be the LAST heat's elo_after, not any heat in between.
        write_ranking_json(
            {
                "meta": {"cyi": 1},
                "couples": [
                    {"competitor": "Alice Adams", "partner": "Bob Baker", "elo": 1520.0,
                     "initial_elo": 1500.0, "heats_processed": 1, "num_opponents": 1, "rank": 1},
                    {"competitor": "Alice Adams", "partner": "Zoe Zimmer", "elo": 1520.0,
                     "initial_elo": 1500.0, "heats_processed": 1, "num_opponents": 1, "rank": 2},
                ],
            },
            tmp_path,
        )
        heats_dir = tmp_path / "heats"
        heats_dir.mkdir(parents=True, exist_ok=True)
        (heats_dir / "1.json").write_text(json.dumps({"competitors": ["Alice Adams", "Bob Baker", "Zoe Zimmer"]}))
        write_history_for_cyi(
            1,
            [
                {"event_name": "E1", "round_name": "Final", "dance_name": "Final (Combined)",
                 "competitor": "Alice Adams", "partner": "Bob Baker", "elo_before": 1500.0, "elo_after": 1510.0},
                {"event_name": "E2", "round_name": "Final", "dance_name": "Final (Combined)",
                 "competitor": "Alice Adams", "partner": "Zoe Zimmer", "elo_before": 1510.0, "elo_after": 1520.0},
            ],
            tmp_path, ["Alice Adams", "Bob Baker", "Zoe Zimmer"],
        )
        # Comp 2's initial elo correctly matches comp 1's LAST heat (1520.0).
        _write_tracked_comp(tmp_path, 2, "Alice Adams", "Bob Baker", 1520.0, 1530.0)
        _write_calendar(tmp_path, {1: "2024-01-01", 2: "2024-06-01"})
        _write_ratings(tmp_path, {"Alice Adams": 1530.0, "Bob Baker": 1530.0, "Zoe Zimmer": 1520.0})

        assert verify(tmp_path, watchlist=[]) is True
        assert "FAIL" not in capsys.readouterr().out

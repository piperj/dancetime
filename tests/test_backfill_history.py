import json

from tools.backfill_history import select_pilot_comps


def _comp(cyi, competition_id, start_date, tracked=False, published=True):
    return {
        "cyi": cyi,
        "competition_id": competition_id,
        "name": f"Comp {cyi}",
        "location": "Nowhere, XX",
        "start_date": start_date,
        "end_date": start_date,
        "published": published,
        **({"tracked": True} if tracked else {}),
    }


class TestSelectPilotComps:
    def test_picks_prior_edition_of_tracked_series(self):
        calendar = {
            "competitions": [
                _comp(1, 11, "2025-01-23"),  # prior edition, untracked
                _comp(2, 11, "2026-01-22", tracked=True),  # currently tracked
            ]
        }
        result = select_pilot_comps(calendar)
        assert [c["cyi"] for c in result] == [1]

    def test_skips_series_with_no_earlier_edition(self):
        calendar = {"competitions": [_comp(2, 11, "2026-01-22", tracked=True)]}
        assert select_pilot_comps(calendar) == []

    def test_excludes_already_tracked_prior_editions(self):
        # Both a 2025 and 2026 edition are already tracked (e.g. IGB) — the
        # "one year back" slot is already covered, nothing to backfill.
        calendar = {
            "competitions": [
                _comp(1, 35, "2025-07-24", tracked=True),
                _comp(2, 35, "2026-07-23", tracked=True),
            ]
        }
        assert select_pilot_comps(calendar) == []

    def test_excludes_unpublished_prior_editions(self):
        calendar = {
            "competitions": [
                _comp(1, 11, "2025-01-23", published=False),
                _comp(2, 11, "2026-01-22", tracked=True),
            ]
        }
        assert select_pilot_comps(calendar) == []

    def test_picks_closest_prior_edition_not_the_earliest(self):
        calendar = {
            "competitions": [
                _comp(1, 11, "2023-01-25"),
                _comp(2, 11, "2025-01-23"),  # closest to the tracked cutoff
                _comp(3, 11, "2026-01-22", tracked=True),
            ]
        }
        result = select_pilot_comps(calendar)
        assert [c["cyi"] for c in result] == [2]

    def test_editions_back_two_reaches_further(self):
        calendar = {
            "competitions": [
                _comp(1, 11, "2023-01-25"),
                _comp(2, 11, "2025-01-23"),
                _comp(3, 11, "2026-01-22", tracked=True),
            ]
        }
        result = select_pilot_comps(calendar, editions_back=2)
        assert [c["cyi"] for c in result] == [1]

    def test_independent_series_are_each_considered(self):
        calendar = {
            "competitions": [
                _comp(1, 11, "2025-01-23"),
                _comp(2, 11, "2026-01-22", tracked=True),
                _comp(3, 58, "2025-07-02"),
                _comp(4, 58, "2026-07-01", tracked=True),
            ]
        }
        result = select_pilot_comps(calendar)
        assert {c["cyi"] for c in result} == {1, 3}


class _FakeClient:
    """Serves one comp with a single session containing one contested heat."""

    def fetch_session_list(self, cyi):
        return {"Ballrooms": [{"ID": 1, "Sessions": [{"ID": 1, "Name": "Session 1"}]}]}

    def fetch_session(self, cyi, session, ballroom=1, feed_type=2):
        return [
            {
                "Type": "Heat",
                "Title": "Heat 1",
                "Date_Time": "1/1/2026 8:00 AM",
                "Floors": [
                    {
                        "Rounds": [
                            {
                                "ID": 10,
                                "Event_ID": 20,
                                "Name": "L-A3 Amer. Cha Cha",
                                "Round": "Final",
                                "Entries": [
                                    {
                                        "Placement": "1",
                                        "Competitors": {
                                            "Participants": [
                                                {"Name": ["Alice", "Adams"]},
                                                {"Name": ["Bob", "Baker"]},
                                            ]
                                        },
                                    },
                                    {
                                        "Placement": "2",
                                        "Competitors": {
                                            "Participants": [
                                                {"Name": ["Carol", "Chen"]},
                                                {"Name": ["Dan", "Diaz"]},
                                            ]
                                        },
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ]


class TestBackfillIntegration:
    def test_writes_bulk_archive_and_updates_ratings(self, tmp_path):
        from ranking.bulk_store import read_bulk_archive
        from ranking.elo_store import load_ratings_full
        from tools.backfill_history import backfill

        calendar = {
            "competitions": [
                _comp(555, 11, "2025-01-23"),
                _comp(556, 11, "2026-01-22", tracked=True),
            ]
        }
        (tmp_path / "calendar.json").write_text(json.dumps(calendar))

        backfill(tmp_path, client=_FakeClient(), sleep=0)

        archive = read_bulk_archive(555, tmp_path)
        assert archive is not None
        # dedup_couples collapses each couple's two mirrored rows into one, so
        # names show up split across "competitor" and "partner" fields.
        competitors = {
            name
            for row in archive["ranking"]["couples"]
            for name in (row["competitor"], row.get("partner"))
            if name
        }
        assert competitors == {"Alice Adams", "Bob Baker", "Carol Chen", "Dan Diaz"}
        assert len(archive["elo_history"]) > 0

        ratings = load_ratings_full(tmp_path)
        assert "Alice Adams" in ratings["ratings"]

        # Never writes into the tracked-comp (SPA-visible) layout.
        assert not (tmp_path / "ranking" / "555.json").exists()
        assert not (tmp_path / "heats" / "555.json").exists()

    def test_skips_comp_already_bulked(self, tmp_path):
        from ranking.bulk_store import write_bulk_archive
        from tools.backfill_history import backfill

        calendar = {
            "competitions": [
                _comp(555, 11, "2025-01-23"),
                _comp(556, 11, "2026-01-22", tracked=True),
            ]
        }
        (tmp_path / "calendar.json").write_text(json.dumps(calendar))
        write_bulk_archive(555, {"meta": {}, "couples": []}, [], tmp_path)
        mtime_before = (tmp_path / "bulk" / "555.tar.xz").stat().st_mtime

        client = _FakeClient()
        client.fetch_session_list = lambda cyi: (_ for _ in ()).throw(AssertionError("should not fetch"))
        backfill(tmp_path, client=client, sleep=0)

        assert (tmp_path / "bulk" / "555.tar.xz").stat().st_mtime == mtime_before

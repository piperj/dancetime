from ranking.bulk_store import bulk_archive_exists, read_bulk_archive, write_bulk_archive


class TestBulkStore:
    def test_round_trip(self, tmp_path):
        ranking_json = {"meta": {"cyi": 42}, "couples": [{"competitor": "Alice Adams"}]}
        elo_history_rows = [{"event_name": "Event", "competitor": "Alice Adams", "elo_before": 1500.0}]

        write_bulk_archive(42, ranking_json, elo_history_rows, tmp_path)
        result = read_bulk_archive(42, tmp_path)

        assert result["ranking"] == ranking_json
        assert result["elo_history"] == elo_history_rows

    def test_missing_archive_returns_none(self, tmp_path):
        assert read_bulk_archive(999, tmp_path) is None

    def test_exists_flag(self, tmp_path):
        assert not bulk_archive_exists(7, tmp_path)
        write_bulk_archive(7, {"meta": {}}, [], tmp_path)
        assert bulk_archive_exists(7, tmp_path)

    def test_writes_to_bulk_subdir_as_tar_xz(self, tmp_path):
        path = write_bulk_archive(3, {"meta": {}}, [], tmp_path)
        assert path == tmp_path / "bulk" / "3.tar.xz"
        assert path.exists()

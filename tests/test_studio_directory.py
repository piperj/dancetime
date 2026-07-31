from ranking.studio_directory import load_studio_directory, lookup_studio, merge_studio_directory


class TestStudioDirectory:
    def test_load_missing_returns_empty(self, tmp_path):
        assert load_studio_directory(tmp_path) == {}

    def test_merge_writes_new_entries(self, tmp_path):
        merge_studio_directory(tmp_path, {"Alice Adams": "Star Studio"})
        assert load_studio_directory(tmp_path) == {"Alice Adams": "Star Studio"}

    def test_merge_is_sticky_never_overwrites(self, tmp_path):
        merge_studio_directory(tmp_path, {"Alice Adams": "Star Studio"})
        merge_studio_directory(tmp_path, {"Alice Adams": "Different Studio"})
        assert load_studio_directory(tmp_path)["Alice Adams"] == "Star Studio"

    def test_merge_fills_in_new_names_alongside_existing(self, tmp_path):
        merge_studio_directory(tmp_path, {"Alice Adams": "Star Studio"})
        merge_studio_directory(tmp_path, {"Bob Baker": "Other Studio"})
        directory = load_studio_directory(tmp_path)
        assert directory == {"Alice Adams": "Star Studio", "Bob Baker": "Other Studio"}

    def test_merge_skips_empty_name_or_studio(self, tmp_path):
        merge_studio_directory(tmp_path, {"": "Star Studio", "Alice Adams": ""})
        assert load_studio_directory(tmp_path) == {}

    def test_merge_no_op_does_not_create_file(self, tmp_path):
        merge_studio_directory(tmp_path, {})
        assert not (tmp_path / "studio_directory.json").exists()

    def test_lookup_studio(self):
        directory = {"Alice Adams": "Star Studio"}
        assert lookup_studio(directory, "Alice Adams") == "Star Studio"
        assert lookup_studio(directory, "Nobody") == ""

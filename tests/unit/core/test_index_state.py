from pathlib import Path

from codegraphcontext.core import index_state


class FakeGraphBuilder:
    parser_languages = {".py": "python"}

    def _load_cgcignore_spec(self, path):
        return None, Path(path).resolve()

    def _discover_supported_files(self, path, supported_extensions, spec, ignore_root, ignore_dirs, job_id=None):
        root = Path(path).resolve()
        return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in supported_extensions)


def test_save_and_check_index_state_fresh(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hello')\n", encoding="utf-8")
    builder = FakeGraphBuilder()

    snapshot = index_state.save_index_state(builder, repo)
    freshness = index_state.check_index_freshness(builder, repo)

    assert snapshot["file_count"] == 1
    assert freshness["status"] == "fresh"
    assert freshness["is_fresh"] is True


def test_check_index_state_detects_modified_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "main.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    builder = FakeGraphBuilder()

    index_state.save_index_state(builder, repo)
    target.write_text("print('changed')\n", encoding="utf-8")

    freshness = index_state.check_index_freshness(builder, repo)

    assert freshness["status"] == "stale"
    assert freshness["changed_files_count"] == 1
    assert freshness["can_refresh_incrementally"] is True
    assert freshness["modified_files_count"] == 1
    assert freshness["modified_files"] == ["main.py"]
    assert "main.py" in freshness["modified_files_preview"]


def test_remove_index_state_deletes_snapshot(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hello')\n", encoding="utf-8")
    builder = FakeGraphBuilder()

    index_state.save_index_state(builder, repo)
    index_state.remove_index_state(repo)

    freshness = index_state.check_index_freshness(builder, repo)
    assert freshness["status"] == "no_snapshot"

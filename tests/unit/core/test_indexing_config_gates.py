import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from codegraphcontext.core.jobs import JobManager
from codegraphcontext.tools.indexing.pipeline import run_tree_sitter_index_async
from codegraphcontext.tools.indexing.scip_pipeline import run_scip_index_async


def run_with_index_loop(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def _file_data(source_file: Path, repo_path: Path) -> dict:
    return {
        "path": str(source_file),
        "repo_path": str(repo_path),
        "lang": "python",
        "functions": [],
        "classes": [],
        "variables": [],
        "imports": [],
        "function_calls": [{"name": "called", "line_number": 1}],
        "function_calls_scip": [{"symbol": "sample/called().", "line_number": 1}],
    }


async def _direct_to_thread(func, *args, **kwargs):
    return func(*args, **kwargs)


def test_tree_sitter_index_respects_disabled_calls_and_inheritance(tmp_path: Path):
    source_file = tmp_path / "sample.py"
    source_file.write_text("def called():\n    return 1\n", encoding="utf-8")
    writer = MagicMock()

    with patch.dict(
        "os.environ",
        {"INDEX_CALLS": "false", "INDEX_INHERITANCE": "false"},
        clear=False,
    ), patch(
        "codegraphcontext.tools.indexing.pipeline.build_inheritance_and_csharp_files"
    ) as inheritance_builder, patch(
        "codegraphcontext.tools.indexing.pipeline.build_function_call_groups"
    ) as call_builder, patch(
        "codegraphcontext.tools.indexing.pipeline.asyncio.to_thread",
        side_effect=_direct_to_thread,
    ):
        run_with_index_loop(
            run_tree_sitter_index_async(
                path=tmp_path,
                is_dependency=False,
                job_id=None,
                cgcignore_path=None,
                writer=writer,
                job_manager=JobManager(),
                parsers={".py": "python"},
                get_parser=lambda _suffix: None,
                parse_file=lambda _repo, _file, _is_dep: _file_data(source_file, tmp_path),
                add_minimal_file_node=MagicMock(),
            )
        )

    inheritance_builder.assert_not_called()
    call_builder.assert_not_called()
    writer.write_inheritance_links.assert_not_called()
    writer.write_function_call_groups.assert_not_called()


def test_tree_sitter_index_runs_calls_and_inheritance_by_default(tmp_path: Path):
    source_file = tmp_path / "sample.py"
    source_file.write_text("def called():\n    return 1\n", encoding="utf-8")
    writer = MagicMock()

    with patch(
        "codegraphcontext.tools.indexing.pipeline.build_inheritance_and_csharp_files",
        return_value=([{"child": "Child"}], []),
    ) as inheritance_builder, patch(
        "codegraphcontext.tools.indexing.pipeline.build_function_call_groups",
        return_value=([{"caller": "caller"}], [], [], []),
    ) as call_builder, patch(
        "codegraphcontext.tools.indexing.pipeline.asyncio.to_thread",
        side_effect=_direct_to_thread,
    ):
        run_with_index_loop(
            run_tree_sitter_index_async(
                path=tmp_path,
                is_dependency=False,
                job_id=None,
                cgcignore_path=None,
                writer=writer,
                job_manager=JobManager(),
                parsers={".py": "python"},
                get_parser=lambda _suffix: None,
                parse_file=lambda _repo, _file, _is_dep: _file_data(source_file, tmp_path),
                add_minimal_file_node=MagicMock(),
            )
        )

    inheritance_builder.assert_called_once()
    call_builder.assert_called_once()
    writer.write_inheritance_links.assert_called_once()
    writer.write_function_call_groups.assert_called_once()


def test_scip_index_respects_disabled_calls_and_inheritance(tmp_path: Path):
    source_file = tmp_path / "sample.py"
    source_file.write_text("def called():\n    return 1\n", encoding="utf-8")
    writer = MagicMock()
    scip_mod = SimpleNamespace(
        ScipIndexer=MagicMock(return_value=MagicMock(run=MagicMock(return_value=tmp_path / "index.scip"))),
        ScipIndexParser=MagicMock(
            return_value=MagicMock(parse=MagicMock(return_value={"files": {str(source_file): _file_data(source_file, tmp_path)}}))
        ),
    )

    with patch.dict(
        "os.environ",
        {"INDEX_CALLS": "false", "INDEX_INHERITANCE": "false"},
        clear=False,
    ), patch(
        "codegraphcontext.tools.indexing.scip_pipeline.build_inheritance_and_csharp_files"
    ) as inheritance_builder:
        run_with_index_loop(
            run_scip_index_async(
                path=tmp_path,
                is_dependency=False,
                job_id=None,
                lang="python",
                writer=writer,
                job_manager=JobManager(),
                parsers_keys={".py"},
                get_parser=lambda _suffix: None,
                scip_indexer_mod=scip_mod,
            )
        )

    inheritance_builder.assert_not_called()
    writer.write_inheritance_links.assert_not_called()
    writer.write_scip_call_edges.assert_not_called()

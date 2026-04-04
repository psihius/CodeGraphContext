from pathlib import Path
import threading
import time
from unittest.mock import MagicMock, patch

from codegraphcontext.core.jobs import JobManager, JobStatus
from codegraphcontext.tools.handlers import indexing_handlers, management_handlers, watcher_handlers


def test_reindex_repository_starts_background_job_for_indexed_repo(tmp_path):
    graph_builder = MagicMock()
    graph_builder.estimate_processing_time.return_value = (42, 4.2)
    job_manager = JobManager()
    loop = MagicMock()

    indexed_repo = (tmp_path / "project").resolve()
    indexed_repo.mkdir()

    def _capture_schedule(coro, _loop):
        coro.close()
        return MagicMock()

    with patch(
        "codegraphcontext.tools.handlers.indexing_handlers.asyncio.run_coroutine_threadsafe",
        side_effect=_capture_schedule,
    ) as mock_schedule:
        result = indexing_handlers.reindex_repository(
            graph_builder,
            job_manager,
            loop,
            lambda: {"repositories": [{"path": str(indexed_repo)}]},
            path=str(indexed_repo),
        )

    assert result["success"] is True
    assert result["status"] == "started"
    assert result["repository_previously_indexed"] is True
    assert "job_id" in result
    assert mock_schedule.called

    job = job_manager.get_job(result["job_id"])
    assert job is not None
    assert job.operation == "reindex"
    assert job.phase == "queued"


def test_reindex_repository_reuses_active_job(tmp_path):
    graph_builder = MagicMock()
    graph_builder.estimate_processing_time.return_value = (10, 1.0)
    job_manager = JobManager()
    loop = MagicMock()

    repo_path = (tmp_path / "project").resolve()
    repo_path.mkdir()
    active_path = str(repo_path)
    active_job_id = job_manager.create_job(active_path, operation="index")
    job_manager.update_job(active_job_id, status=JobStatus.RUNNING, phase="indexing files")

    result = indexing_handlers.reindex_repository(
        graph_builder,
        job_manager,
        loop,
        lambda: {"repositories": [{"path": active_path}]},
        path=active_path,
    )

    assert result["success"] is True
    assert result["status"] == "job_already_running"
    assert result["job_id"] == active_job_id
    assert result["job"]["operation"] == "index"


def test_check_job_status_returns_agent_friendly_status_message():
    job_manager = JobManager()
    job_id = job_manager.create_job("/tmp/project", operation="reindex")
    job_manager.update_job(
        job_id,
        status=JobStatus.RUNNING,
        phase="removing existing index",
        current_file="/tmp/project",
    )

    result = management_handlers.check_job_status(job_manager, job_id=job_id)

    assert result["success"] is True
    assert result["job"]["operation"] == "reindex"
    assert result["job"]["is_active"] is True
    assert result["job"]["recommended_poll_interval_seconds"] == 2
    assert "Re-index running" in result["job"]["status_message"]


def test_check_index_freshness_returns_recommendation():
    graph_builder = MagicMock()
    graph_builder.get_index_freshness.return_value = {
        "status": "stale",
        "can_refresh_incrementally": True,
        "changed_files_count": 3,
    }

    result = management_handlers.check_index_freshness(graph_builder, path="/tmp/project")

    assert result["success"] is True
    assert result["recommended_action"] == "incremental_reconcile"
    assert result["recommended_tool"] == "watch_directory"
    assert result["requires_user_attention"] is False


def test_wait_for_job_returns_terminal_status():
    job_manager = JobManager()
    job_id = job_manager.create_job("/tmp/project", operation="reindex")
    job_manager.update_job(job_id, status=JobStatus.RUNNING, phase="indexing files")

    def complete_job():
        time.sleep(0.05)
        job_manager.update_job(job_id, status=JobStatus.COMPLETED)

    worker = threading.Thread(target=complete_job)
    worker.start()
    result = management_handlers.wait_for_job(
        job_manager,
        job_id=job_id,
        timeout_seconds=1,
        poll_interval_seconds=0.01,
    )
    worker.join()

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["wait_completed"] is True
    assert result["job"]["status"] == "completed"


def test_wait_for_job_times_out_with_latest_snapshot():
    job_manager = JobManager()
    job_id = job_manager.create_job("/tmp/project", operation="reindex")
    job_manager.update_job(job_id, status=JobStatus.RUNNING, phase="indexing files")

    result = management_handlers.wait_for_job(
        job_manager,
        job_id=job_id,
        timeout_seconds=0.05,
        poll_interval_seconds=0.01,
    )

    assert result["success"] is True
    assert result["status"] == "timeout"
    assert result["wait_completed"] is False
    assert result["job"]["status"] == "running"


def test_watch_directory_blocks_when_index_snapshot_is_stale(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()

    graph_builder = MagicMock()
    graph_builder.get_index_freshness.return_value = {
        "status": "stale",
        "reason": "repository files changed since the last indexed snapshot",
        "changed_files_count": 3,
    }

    code_watcher = MagicMock()
    code_watcher.graph_builder = graph_builder
    code_watcher.watched_paths = set()

    result = watcher_handlers.watch_directory(
        code_watcher,
        lambda: {"repositories": [{"path": str(repo.resolve())}]},
        MagicMock(),
        path=str(repo),
    )

    assert result["success"] is False
    assert result["status"] == "stale_index"
    assert result["startup_action"] == "watch_blocked"
    assert result["index_validation"] == "stale_requires_full_reindex"
    assert result["recommended_next_tool"] == "reindex_repository"
    assert "reindex_repository" in result["next_step"]
    code_watcher.watch_directory.assert_not_called()


def test_watch_directory_reconciles_small_offline_changes(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()

    graph_builder = MagicMock()
    graph_builder.get_index_freshness.return_value = {
        "status": "stale",
        "can_refresh_incrementally": True,
        "changed_files_count": 2,
    }
    graph_builder.reconcile_repository_files.return_value = {
        "success": True,
        "status": "incremental_refresh_completed",
        "updated_files": 2,
    }

    code_watcher = MagicMock()
    code_watcher.graph_builder = graph_builder
    code_watcher.watched_paths = set()

    result = watcher_handlers.watch_directory(
        code_watcher,
        lambda: {"repositories": [{"path": str(repo.resolve())}]},
        MagicMock(),
        path=str(repo),
    )

    assert result["success"] is True
    assert result["status"] == "watching_after_incremental_refresh"
    assert result["startup_action"] == "incremental_reconcile_then_watch"
    assert result["index_validation"] == "stale_reconciled"
    assert result["recommended_next_tool"] == "none"
    graph_builder.reconcile_repository_files.assert_called_once()
    code_watcher.watch_directory.assert_called_once()

# src/codegraphcontext/tools/handlers/watcher_handlers.py
from typing import Any, Dict

from ...utils.debug_log import error_logger
from ...utils.repo_path import any_repo_matches_path


def _watch_response(
    *,
    success: bool,
    status: str,
    message: str,
    startup_action: str,
    index_validation: str,
    recommended_next_action: str,
    recommended_next_tool: str,
    freshness: Dict[str, Any] | None = None,
    reconcile_result: Dict[str, Any] | None = None,
    job_id: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "success": success,
        "status": status,
        "message": message,
        "startup_action": startup_action,
        "index_validation": index_validation,
        "recommended_next_action": recommended_next_action,
        "recommended_next_tool": recommended_next_tool,
    }
    if freshness is not None:
        payload["freshness"] = freshness
    if reconcile_result is not None:
        payload["reconcile_result"] = reconcile_result
    if job_id is not None:
        payload["job_id"] = job_id
    return payload


def list_watched_paths(code_watcher, **args) -> Dict[str, Any]:
    """Tool to list all currently watched directory paths."""
    try:
        paths = code_watcher.list_watched_paths()
        return {"success": True, "watched_paths": paths}
    except Exception as e:
        return {"error": f"Failed to list watched paths: {str(e)}"}

def unwatch_directory(code_watcher, **args) -> Dict[str, Any]:
    """Tool to stop watching a directory."""
    path = args.get("path")
    if not path:
        return {"error": "Path is a required argument."}
    return code_watcher.unwatch_directory(path)

# watch_directory is complex as it depends on other tools and handlers
# We will keep it in server.py or implement it here passing all dependencies.
# Let's implement it here as a pure function accepting dependencies.
# Dependencies: code_watcher, list_repositories_func, add_code_func

def watch_directory(code_watcher, list_repositories_func, add_code_func, **args) -> Dict[str, Any]:
    """
    Tool implementation to start watching a directory for changes.
    It checks if the path exists, if it's already watched, or if it needs indexing.
    """
    path = args.get("path")
    from pathlib import Path

    if not path:
        return {"error": "Path is a required argument."}

    path_obj = Path(path).resolve()
    path_str = str(path_obj)

    # 1. Validate the path
    if not path_obj.is_dir():
        return {
            "success": True,
            "status": "path_not_found",
            "message": f"Path '{path_str}' does not exist or is not a directory."
        }
    try:
        # Check if already watching
        if path_str in code_watcher.watched_paths:
            return _watch_response(
                success=True,
                status="already_watching",
                message=f"Already watching directory: {path_str}",
                startup_action="none",
                index_validation="not_checked",
                recommended_next_action="continue",
                recommended_next_tool="none",
            )

        # 2. Check if the repository is already indexed
        indexed_repos_result = list_repositories_func()
        indexed_repos = indexed_repos_result.get("repositories", [])
        is_already_indexed = any_repo_matches_path(indexed_repos, path_obj)

        # 3. Decide whether to perform an initial scan
        if is_already_indexed:
            freshness = code_watcher.graph_builder.get_index_freshness(path_obj)
            if freshness.get("status") == "fresh":
                code_watcher.watch_directory(path_str, perform_initial_scan=False)
                return _watch_response(
                    success=True,
                    status="watching_fresh_index",
                    message=f"Path '{path_str}' is already indexed and matches the last saved snapshot. Now watching for live changes.",
                    startup_action="watch_started",
                    index_validation="fresh",
                    recommended_next_action="continue",
                    recommended_next_tool="none",
                    freshness=freshness,
                )

            if freshness.get("status") == "no_snapshot":
                code_watcher.watch_directory(path_str, perform_initial_scan=False)
                return _watch_response(
                    success=True,
                    status="watching_unverified_index",
                    message=f"Path '{path_str}' is already indexed, but no saved freshness snapshot was found. Started watching without forcing a rebuild.",
                    startup_action="watch_started",
                    index_validation="unverified",
                    recommended_next_action="continue_or_reindex_if_user_wants_strict_validation",
                    recommended_next_tool="reindex_repository",
                    freshness=freshness,
                )

            if freshness.get("can_refresh_incrementally"):
                reconcile_result = code_watcher.graph_builder.reconcile_repository_files(path_obj, freshness)
                if reconcile_result.get("success"):
                    code_watcher.watch_directory(path_str, perform_initial_scan=False)
                    return _watch_response(
                        success=True,
                        status="watching_after_incremental_refresh",
                        message=f"Path '{path_str}' had a small number of offline changes. Reconciled the index and started watching for live changes.",
                        startup_action="incremental_reconcile_then_watch",
                        index_validation="stale_reconciled",
                        recommended_next_action="continue",
                        recommended_next_tool="none",
                        freshness=freshness,
                        reconcile_result=reconcile_result,
                    )

            # If the indexed state is stale, stop and let the caller decide how to refresh safely.
            payload = _watch_response(
                success=False,
                status="stale_index",
                message=f"Path '{path_str}' has changed since the last saved index snapshot. Refresh the index before starting watch mode.",
                startup_action="watch_blocked",
                index_validation="stale_requires_full_reindex",
                recommended_next_action="reindex_then_watch",
                recommended_next_tool="reindex_repository",
                freshness=freshness,
            )
            payload["next_step"] = "Call 'reindex_repository' for this path, then call 'watch_directory' again."
            return payload
        else:
            # If not indexed, perform the scan AND start the watcher
            scan_job_result = add_code_func(path=path_str, is_dependency=False)

            if "error" in scan_job_result:
                return scan_job_result
            
            code_watcher.watch_directory(path_str, perform_initial_scan=True)
            
            payload = _watch_response(
                success=True,
                status="initial_index_started_and_watching",
                message=f"Path '{path_str}' was not indexed. Started initial scan and now watching for live changes.",
                startup_action="initial_index_then_watch",
                index_validation="not_indexed",
                recommended_next_action="monitor_initial_index_job",
                recommended_next_tool="check_job_status",
                job_id=scan_job_result.get("job_id"),
            )
            payload["details"] = "Use check_job_status to monitor the initial scan."
            return payload
        
    except Exception as e:
        error_logger(f"Failed to start watching directory {path}: {e}")
        return {"error": f"Failed to start watching directory: {str(e)}"}

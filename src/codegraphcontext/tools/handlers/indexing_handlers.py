# src/codegraphcontext/tools/handlers/indexing_handlers.py
from typing import Any, Dict, List
from pathlib import Path
import asyncio
import os
from datetime import datetime
from ...utils.debug_log import debug_log
from ...core.jobs import JobStatus
from ...utils.repo_path import repo_record_matches_path
from ..package_resolver import get_local_package_path


def _get_allowed_roots() -> List[Path]:
    """
    Return the list of allowed root directories for indexing.

    By default only the current working directory is allowed.  Additional
    roots can be specified via the ``CGC_ALLOWED_ROOTS`` environment
    variable (colon-separated on Unix, semicolon-separated on Windows).
    """
    roots: List[Path] = [Path.cwd().resolve()]

    env_roots = os.environ.get("CGC_ALLOWED_ROOTS", "")
    if env_roots:
        separator = ";" if os.name == "nt" else ":"
        for entry in env_roots.split(separator):
            entry = entry.strip()
            if entry:
                roots.append(Path(entry).resolve())

    return roots


def _is_path_allowed(path: Path) -> bool:
    """Check whether *path* falls under one of the allowed root directories."""
    resolved = path.resolve()
    for root in _get_allowed_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _format_duration_human(estimated_time: float) -> str:
    if estimated_time >= 60:
        return f"{int(estimated_time // 60)}m {int(estimated_time % 60)}s"
    return f"{int(estimated_time)}s"


def _active_job_snapshot(job) -> Dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "operation": getattr(job, "operation", "index"),
        "phase": job.phase,
        "path": job.path,
        "progress_percentage": round(job.progress_percentage, 2),
    }


async def _reindex_repository_job(
    graph_builder,
    job_manager,
    path_obj: Path,
    is_dependency: bool,
    job_id: str,
    repo_exists: bool,
):
    """Delete the existing repository graph slice and rebuild it."""
    try:
        job_manager.update_job(
            job_id,
            status=JobStatus.RUNNING,
            current_file=str(path_obj),
            result={
                "requested_action": "reindex",
                "repository_previously_indexed": repo_exists,
            },
        )

        if repo_exists:
            graph_builder._set_job_phase(
                job_id,
                "removing existing index",
                total=1,
                completed=0,
                current_file=str(path_obj),
            )
            await graph_builder._yield_to_progress_ui(job_id)

            deleted = await asyncio.to_thread(
                graph_builder.delete_repository_from_graph,
                str(path_obj),
            )

            graph_builder._set_job_phase(
                job_id,
                "removing existing index",
                total=1,
                completed=1 if deleted else 0,
                current_file=str(path_obj),
            )
            await graph_builder._yield_to_progress_ui(job_id)
        else:
            graph_builder._set_job_phase(
                job_id,
                "repository not indexed; starting initial index",
                total=1,
                completed=1,
                current_file=str(path_obj),
            )
            await graph_builder._yield_to_progress_ui(job_id)

        graph_builder._set_job_phase(
            job_id,
            "estimating reindex workload",
            total=0,
            completed=0,
            current_file=str(path_obj),
        )
        total_files, estimated_time = graph_builder.estimate_processing_time(path_obj) or (0, 0.0)
        job_manager.update_job(
            job_id,
            total_files=total_files or 0,
            estimated_duration=estimated_time or 0.0,
        )
        await graph_builder._yield_to_progress_ui(job_id)

        await graph_builder.build_graph_from_path_async(
            path_obj,
            is_dependency=is_dependency,
            job_id=job_id,
        )

        job = job_manager.get_job(job_id)
        if job and job.status == JobStatus.COMPLETED:
            result = dict(job.result or {})
            result.update({
                "requested_action": "reindex",
                "repository_previously_indexed": repo_exists,
                "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            job_manager.update_job(job_id, result=result)

    except Exception as e:
        debug_log(f"Re-index background job failed for {path_obj}: {str(e)}")
        job_manager.update_job(
            job_id,
            status=JobStatus.FAILED,
            end_time=datetime.now(),
            errors=[str(e)],
        )

def add_code_to_graph(graph_builder, job_manager, loop, list_repos_func, **args) -> Dict[str, Any]:
    """
    Tool implementation to index a directory of code.
    Runs indexing asynchronously via a background job.
    """
    path = args.get("path")
    is_dependency = args.get("is_dependency", False)
    
    try:
        path_obj = Path(path).resolve()

        # --- Path-traversal guard ---------------------------------------------------
        if not _is_path_allowed(path_obj):
            return {
                "error": (
                    f"Path '{path}' is outside the allowed roots. "
                    "Only subdirectories of the current working directory (or paths "
                    "listed in the CGC_ALLOWED_ROOTS environment variable) can be indexed."
                )
            }
        # -----------------------------------------------------------------------------

        if not path_obj.exists():
            return {
                "success": True,
                "status": "path_not_found",
                "message": f"Path '{path}' does not exist."
            }

        # Prevent re-indexing the same repository.
        indexed_repos = list_repos_func().get("repositories", [])
        for repo in indexed_repos:
            if repo_record_matches_path(repo, path_obj):
                return {
                    "success": False,
                    "message": f"Repository '{path}' is already indexed."
                }
        
        # Estimate time and create a job for the user to track.
        total_files, estimated_time = graph_builder.estimate_processing_time(path_obj)
        active_job = job_manager.find_active_job_by_path(str(path_obj))
        if active_job:
            return {
                "success": True,
                "status": "job_already_running",
                "job_id": active_job.job_id,
                "message": f"A job is already running for '{path_obj}'.",
                "job": _active_job_snapshot(active_job),
                "instructions": f"Use 'check_job_status' with job_id '{active_job.job_id}' to monitor progress"
            }

        job_id = job_manager.create_job(str(path_obj), is_dependency, operation="index")
        job_manager.update_job(job_id, total_files=total_files, estimated_duration=estimated_time)
        
        # Create the coroutine for the background task and schedule it on the main event loop.
        coro = graph_builder.build_graph_from_path_async(
            path_obj, is_dependency, job_id
        )
        asyncio.run_coroutine_threadsafe(coro, loop)
        
        debug_log(f"Started background job {job_id} for path: {str(path_obj)}, is_dependency: {is_dependency}")
        
        return {
            "success": True, "job_id": job_id,
            "message": f"Background processing started for {str(path_obj)}",
            "estimated_files": total_files,
            "estimated_duration_seconds": round(estimated_time, 2),
            "estimated_duration_human": _format_duration_human(estimated_time),
            "instructions": f"Use 'check_job_status' with job_id '{job_id}' to monitor progress"
        }
    
    except Exception as e:
        debug_log(f"Error creating background job: {str(e)}")
        return {"error": f"Failed to start background processing: {str(e)}"}

def add_package_to_graph(graph_builder, job_manager, loop, list_repos_func, **args) -> Dict[str, Any]:
    """Tool to add a package to the graph by auto-discovering its location"""
    package_name = args.get("package_name")
    language = args.get("language")
    is_dependency = args.get("is_dependency", True)

    if not language:
        return {"error": "The 'language' parameter is required."}

    try:
        # Check if the package is already indexed
        indexed_repos = list_repos_func().get("repositories", [])
        for repo in indexed_repos:
            if repo.get("is_dependency") and (repo.get("name") == package_name or repo.get("name") == f"{package_name}.py"):
                return {
                    "success": False,
                    "message": f"Package '{package_name}' is already indexed."
                }

        package_path = get_local_package_path(package_name, language)
        
        if not package_path:
            return {"error": f"Could not find package '{package_name}' for language '{language}'. Make sure it's installed."}
        
        if not os.path.exists(package_path):
            return {"error": f"Package path '{package_path}' does not exist"}
        
        path_obj = Path(package_path)
        
        total_files, estimated_time = graph_builder.estimate_processing_time(path_obj)
        
        active_job = job_manager.find_active_job_by_path(package_path)
        if active_job:
            return {
                "success": True,
                "status": "job_already_running",
                "job_id": active_job.job_id,
                "message": f"A job is already running for package '{package_name}'.",
                "job": _active_job_snapshot(active_job),
                "instructions": f"Use 'check_job_status' with job_id '{active_job.job_id}' to monitor progress"
            }

        job_id = job_manager.create_job(package_path, is_dependency, operation="package_index")
        
        job_manager.update_job(job_id, total_files=total_files, estimated_duration=estimated_time)
        
        coro = graph_builder.build_graph_from_path_async(
            path_obj, is_dependency, job_id
        )
        asyncio.run_coroutine_threadsafe(coro, loop)
        
        debug_log(f"Started background job {job_id} for package: {package_name} at {package_path}, is_dependency: {is_dependency}")
        
        return {
            "success": True, "job_id": job_id, "package_name": package_name,
            "discovered_path": package_path,
            "message": f"Background processing started for package '{package_name}'",
            "estimated_files": total_files,
            "estimated_duration_seconds": round(estimated_time, 2),
            "estimated_duration_human": _format_duration_human(estimated_time),
            "instructions": f"Use 'check_job_status' with job_id '{job_id}' to monitor progress"
        }
    
    except Exception as e:
        debug_log(f"Error creating background job for package {package_name}: {str(e)}")
        return {"error": f"Failed to start background processing for package '{package_name}': {str(e)}"}


def reindex_repository(graph_builder, job_manager, loop, list_repos_func, **args) -> Dict[str, Any]:
    """
    Refresh an indexed repository by deleting its current graph slice and
    rebuilding it as a background job.
    """
    path = args.get("path")
    create_if_missing = args.get("create_if_missing", True)
    is_dependency = args.get("is_dependency", False)

    try:
        path_obj = Path(path).resolve()

        if not path_obj.exists():
            return {
                "success": True,
                "status": "path_not_found",
                "message": f"Path '{path}' does not exist."
            }

        active_job = job_manager.find_active_job_by_path(str(path_obj))
        if active_job:
            return {
                "success": True,
                "status": "job_already_running",
                "job_id": active_job.job_id,
                "message": f"A job is already running for '{path_obj}'. Reusing that job instead of starting another.",
                "job": _active_job_snapshot(active_job),
                "instructions": f"Use 'check_job_status' with job_id '{active_job.job_id}' to monitor progress"
            }

        indexed_repos = list_repos_func().get("repositories", [])
        repo_exists = any(repo_record_matches_path(repo, path_obj) for repo in indexed_repos)

        if not repo_exists and not _is_path_allowed(path_obj):
            return {
                "error": (
                    f"Path '{path}' is outside the allowed roots. "
                    "Only subdirectories of the current working directory (or paths "
                    "listed in the CGC_ALLOWED_ROOTS environment variable) can be indexed."
                )
            }

        if not repo_exists and not create_if_missing:
            return {
                "success": False,
                "status": "not_indexed",
                "message": f"Repository '{path}' is not indexed yet. Set create_if_missing=true or use 'add_code_to_graph' first."
            }

        total_files, estimated_time = graph_builder.estimate_processing_time(path_obj) or (0, 0.0)
        job_id = job_manager.create_job(str(path_obj), is_dependency, operation="reindex")
        job_manager.update_job(
            job_id,
            total_files=total_files or 0,
            estimated_duration=estimated_time or 0.0,
            phase="queued",
            current_file=str(path_obj),
            result={
                "requested_action": "reindex",
                "repository_previously_indexed": repo_exists,
            },
        )

        coro = _reindex_repository_job(
            graph_builder,
            job_manager,
            path_obj,
            is_dependency,
            job_id,
            repo_exists,
        )
        asyncio.run_coroutine_threadsafe(coro, loop)

        action_message = "Re-indexing queued" if repo_exists else "Initial indexing queued"
        return {
            "success": True,
            "status": "started",
            "job_id": job_id,
            "message": f"{action_message} for {str(path_obj)}",
            "repository_previously_indexed": repo_exists,
            "estimated_files": total_files,
            "estimated_duration_seconds": round(estimated_time, 2),
            "estimated_duration_human": _format_duration_human(estimated_time),
            "next_step": "Poll check_job_status until the job reaches completed or failed.",
            "instructions": f"Use 'check_job_status' with job_id '{job_id}' to monitor progress"
        }

    except Exception as e:
        debug_log(f"Error creating re-index job: {str(e)}")
        return {"error": f"Failed to start re-indexing: {str(e)}"}

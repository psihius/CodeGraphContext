import hashlib
import json
import subprocess
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path
from typing import Any, Dict, Optional

from codegraphcontext.cli.config_manager import get_config_value
from codegraphcontext.utils.debug_log import warning_logger


INDEX_STATE_VERSION = 1
INDEX_STATE_DIRNAME = ".codegraphcontext"
INDEX_STATE_FILENAME = "index_state.json"
INCREMENTAL_CHANGE_COUNT_THRESHOLD = 50
INCREMENTAL_CHANGE_RATIO_THRESHOLD = 0.10
CONFIG_FINGERPRINT_KEYS = [
    "INDEX_SOURCE",
    "INDEX_CALLS",
    "INDEX_INHERITANCE",
    "INDEX_VARIABLES",
    "IGNORE_DIRS",
    "IGNORE_HIDDEN_FILES",
    "IGNORE_TEST_FILES",
    "MAX_DEPTH",
    "MAX_FILE_SIZE_MB",
    "SCIP_INDEXER",
    "SCIP_LANGUAGES",
]


def _get_cgc_version() -> str:
    try:
        return pkg_version("codegraphcontext")
    except PackageNotFoundError:
        return "0.0.0-dev"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_repo_path(path: Path) -> Path:
    resolved = path.resolve()
    return resolved if resolved.is_dir() else resolved.parent


def _index_state_path(repo_path: Path) -> Path:
    repo_root = _normalize_repo_path(repo_path)
    return repo_root / INDEX_STATE_DIRNAME / INDEX_STATE_FILENAME


def _load_ignore_contents(ignore_root: Path) -> Dict[str, str]:
    contents: Dict[str, str] = {}
    for filename in (".cgcignore", ".cgcignore.local"):
        ignore_path = ignore_root / filename
        if ignore_path.exists():
            contents[filename] = ignore_path.read_text(encoding="utf-8")
    return contents


def _config_snapshot(graph_builder, repo_path: Path) -> Dict[str, Any]:
    from codegraphcontext.core.cgcignore import build_ignore_spec
    from codegraphcontext.tools.indexing.constants import DEFAULT_IGNORE_PATTERNS

    ignore_root = _normalize_repo_path(repo_path)
    _spec, resolved_ignore = build_ignore_spec(
        ignore_root=ignore_root,
        default_patterns=DEFAULT_IGNORE_PATTERNS,
    )
    if resolved_ignore:
        ignore_root = resolved_ignore.parent
    ignore_contents = _load_ignore_contents(ignore_root)
    config_values = {key: get_config_value(key) for key in CONFIG_FINGERPRINT_KEYS}
    supported_extensions = getattr(graph_builder, "parsers", None) or getattr(
        graph_builder, "parser_languages", {}
    )
    snapshot = {
        "config_values": config_values,
        "ignore_root": str(ignore_root.resolve()),
        "ignore_files": {name: _sha256_text(content) for name, content in ignore_contents.items()},
        "supported_extensions": sorted(supported_extensions.keys()),
        "state_version": INDEX_STATE_VERSION,
        "cgc_version": _get_cgc_version(),
    }
    snapshot["fingerprint"] = _sha256_text(json.dumps(snapshot, sort_keys=True))
    return snapshot


def _git_state(repo_path: Path) -> Dict[str, Any]:
    repo_root = _normalize_repo_path(repo_path)

    try:
        top_level = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        head = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status_output = subprocess.check_output(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=normal"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return {
            "available": True,
            "repo_root": top_level,
            "head": head,
            "is_dirty": bool(status_output.strip()),
            "status_digest": _sha256_text(status_output),
        }
    except Exception:
        return {"available": False}


def _discover_supported_files(graph_builder, repo_path: Path) -> list[Path]:
    from codegraphcontext.tools.indexing.discovery import discover_files_to_index

    path_obj = _normalize_repo_path(repo_path)
    supported_extensions = getattr(graph_builder, "parsers", None) or getattr(
        graph_builder, "parser_languages", {}
    )
    files, _ignore_root = discover_files_to_index(
        path_obj,
        supported_extensions=set(supported_extensions.keys()),
    )
    return files


def _build_manifest(graph_builder, repo_path: Path) -> Dict[str, Dict[str, int]]:
    repo_root = _normalize_repo_path(repo_path)
    manifest: Dict[str, Dict[str, int]] = {}
    for file_path in _discover_supported_files(graph_builder, repo_root):
        stat_result = file_path.stat()
        rel_path = file_path.resolve().relative_to(repo_root).as_posix()
        manifest[rel_path] = {
            "size": stat_result.st_size,
            "mtime_ns": stat_result.st_mtime_ns,
        }
    return manifest


def load_index_state(repo_path: Path) -> Optional[Dict[str, Any]]:
    state_path = _index_state_path(repo_path)
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        warning_logger(f"Failed to read index state from {state_path}: {exc}")
        return None


def save_index_state(graph_builder, repo_path: Path) -> Dict[str, Any]:
    repo_root = _normalize_repo_path(repo_path)
    state_path = _index_state_path(repo_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "state_version": INDEX_STATE_VERSION,
        "repo_path": str(repo_root),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": _config_snapshot(graph_builder, repo_root),
        "git": _git_state(repo_root),
        "files": _build_manifest(graph_builder, repo_root),
    }
    snapshot["file_count"] = len(snapshot["files"])

    state_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return snapshot


def remove_index_state(repo_path: Path) -> None:
    state_path = _index_state_path(repo_path)
    if state_path.exists():
        state_path.unlink()


def check_index_freshness(graph_builder, repo_path: Path) -> Dict[str, Any]:
    repo_root = _normalize_repo_path(repo_path)
    previous = load_index_state(repo_root)
    if not previous:
        return {
            "status": "no_snapshot",
            "is_fresh": False,
            "requires_refresh": False,
            "message": "No persisted index snapshot was found for this repository.",
            "repo_path": str(repo_root),
        }

    current_config = _config_snapshot(graph_builder, repo_root)
    previous_config = previous.get("config", {})
    if current_config.get("fingerprint") != previous_config.get("fingerprint"):
        return {
            "status": "stale",
            "is_fresh": False,
            "requires_refresh": True,
            "requires_full_reindex": True,
            "can_refresh_incrementally": False,
            "reason": "index configuration changed since the last successful index",
            "repo_path": str(repo_root),
            "changed_files_count": 0,
            "total_files": previous.get("file_count", 0),
        }

    current_git = _git_state(repo_root)
    previous_git = previous.get("git", {})
    if current_git.get("available") and previous_git.get("available"):
        if (
            current_git.get("head") == previous_git.get("head")
            and current_git.get("status_digest") == previous_git.get("status_digest")
        ):
            return {
                "status": "fresh",
                "is_fresh": True,
                "requires_refresh": False,
                "message": "Git state matches the last indexed snapshot.",
                "repo_path": str(repo_root),
                "changed_files_count": 0,
                "total_files": previous.get("file_count", 0),
            }

    previous_files = previous.get("files", {})
    current_files = _build_manifest(graph_builder, repo_root)

    previous_keys = set(previous_files)
    current_keys = set(current_files)

    added_files = sorted(current_keys - previous_keys)
    deleted_files = sorted(previous_keys - current_keys)
    modified_files = sorted(
        path
        for path in previous_keys & current_keys
        if previous_files.get(path) != current_files.get(path)
    )

    changed_count = len(added_files) + len(deleted_files) + len(modified_files)
    total_files = len(current_files)

    if changed_count == 0:
        return {
            "status": "fresh",
            "is_fresh": True,
            "requires_refresh": False,
            "message": "File metadata matches the last indexed snapshot.",
            "repo_path": str(repo_root),
            "changed_files_count": 0,
            "total_files": total_files,
        }

    change_ratio = (changed_count / total_files) if total_files else 1.0
    requires_full_reindex = (
        changed_count > INCREMENTAL_CHANGE_COUNT_THRESHOLD
        or (total_files >= 20 and change_ratio > INCREMENTAL_CHANGE_RATIO_THRESHOLD)
    )

    preview_limit = 25
    can_refresh_incrementally = not requires_full_reindex
    return {
        "status": "stale",
        "is_fresh": False,
        "requires_refresh": True,
        "requires_full_reindex": requires_full_reindex,
        "can_refresh_incrementally": can_refresh_incrementally,
        "reason": "repository files changed since the last indexed snapshot",
        "repo_path": str(repo_root),
        "changed_files_count": changed_count,
        "total_files": total_files,
        "added_files_count": len(added_files),
        "deleted_files_count": len(deleted_files),
        "modified_files_count": len(modified_files),
        "added_files": added_files if can_refresh_incrementally else [],
        "deleted_files": deleted_files if can_refresh_incrementally else [],
        "modified_files": modified_files if can_refresh_incrementally else [],
        "added_files_preview": added_files[:preview_limit],
        "deleted_files_preview": deleted_files[:preview_limit],
        "modified_files_preview": modified_files[:preview_limit],
    }

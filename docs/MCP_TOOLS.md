# MCP Tools Reference

This document describes the Model Context Protocol (MCP) tools exposed by CodeGraphContext **0.4.11**. The server registers the full catalog defined in `src/codegraphcontext/tool_definitions.py` (same tools the CLI graph operations rely on). In v0.4.11, MCP `tools/list` returns **21** tool definitions—the subsections below enumerate each one.

## Tool categories

1. [Context management](#context-management)
2. [Indexing & management](#indexing--management)
3. [Code search](#code-search)
4. [Analysis & quality](#analysis--quality)
5. [Bundle management](#bundle-management)
6. [Monitoring](#monitoring)
7. [Job control](#job-control)
8. [Advanced querying](#advanced-querying)

---

## Context management

### `discover_codegraph_contexts`

Scan child directories for `.codegraphcontext/` folders that contain an indexed database—useful when the IDE opens a parent directory that has no graph, but sub-projects do.

- **Args:** `path` (string, optional), `max_depth` (integer, default `1`)
- **Returns:** List of discovered contexts with paths and metadata

### `switch_context`

Point the MCP session at a different `.codegraphcontext` database (repository root or `.codegraphcontext/` directory).

- **Args:** `context_path` (string, required), `save` (boolean, default `true` — persist mapping for future sessions)
- **Returns:** Status, resolved database type, and paths

---

## Indexing & management

### `add_code_to_graph`

One-time scan of a local folder to add code to the graph (libraries, dependencies, or projects not under active watch).

- **Args:** `path` (string), `is_dependency` (boolean)
- **Returns:** Job ID

### `reindex_repository`
Refresh an indexed repository by deleting its existing graph slice and rebuilding it in the background. If desired, it can also fall back to a first-time index when the repository is not indexed yet.
- **Args**: `path` (string), `create_if_missing` (boolean), `is_dependency` (boolean)
- **Returns**: Job ID and job-tracking instructions

### `add_package_to_graph`

Add an external package by resolving its install location.

- **Args:** `package_name` (string), `language` (string), `is_dependency` (boolean)
- **Returns:** Job ID
- **Supported languages:** python, javascript, typescript, java, c, go, ruby, php, cpp

### `list_indexed_repositories`

List repositories currently in the graph.

- **Args:** None
- **Returns:** Paths and metadata for each indexed repo

### `check_index_freshness`
Check whether a repository has changed since the last successful index snapshot. Useful after restarting the MCP server to decide whether a re-index is actually needed.
- **Args**: `path` (string)
- **Returns**: Fresh/stale status, change counts, whether incremental reconciliation is possible, and normalized recommendation fields like `recommended_action` / `recommended_tool`

### `delete_repository`

Remove a repository from the graph.

- **Args:** `repo_path` (string)
- **Returns:** Success message

### `check_job_status`
Check the status of a background job (indexing, scanning).
- **Args**: `job_id` (string)
- **Returns**: Job status (running, completed, failed), phase/progress, and a status message suitable for relaying to the user

### `wait_for_job`
Wait for a background job to reach a terminal state and return the final job snapshot. Useful for MCP clients that want a single blocking call instead of manual polling.
- **Args**: `job_id` (string), `timeout_seconds` (number), `poll_interval_seconds` (number)
- **Returns**: Final job state, or a timeout response with the latest known job snapshot

### `get_repository_stats`

Counts of files, functions, classes, and modules for one repo or the whole database.

- **Args:** `repo_path` (string, optional)
- **Returns:** Statistics object

---

## Code search

### `find_code`

Keyword search over indexed symbols and content.

- **Args:** `query` (string), `fuzzy_search` (boolean), `edit_distance` (number), `repo_path` (string, optional)
- **Returns:** Matches with path, line, and snippet context

---

## Analysis & quality

### `analyze_code_relationships`

Callers, callees, imports, hierarchy, and other relationship queries.

- **Args:** `query_type` (enum), `target` (string), `context` (string, optional file path), `repo_path` (string, optional)
- **Returns:** Structured relationship results

### `find_dead_code`

Potentially unused functions across the indexed codebase.

- **Args:** `exclude_decorated_with` (list of strings), `repo_path` (string, optional)
- **Returns:** Candidate dead symbols

### `calculate_cyclomatic_complexity`

Complexity for a single function.

- **Args:** `function_name` (string), `path` (string, optional), `repo_path` (string, optional)
- **Returns:** Complexity score

### `find_most_complex_functions`

Rank functions by cyclomatic complexity.

- **Args:** `limit` (integer), `repo_path` (string, optional)
- **Returns:** Ordered list of functions

---

## Bundle management

### `load_bundle`

Load a `.cgc` bundle (local file or registry download).

- **Args:** `bundle_name` (string), `clear_existing` (boolean)
- **Returns:** Load status and stats

### `search_registry_bundles`

Search the public bundle registry.

- **Args:** `query` (string, optional), `unique_only` (boolean)
- **Returns:** Matching bundles and metadata

---

## Monitoring

### `watch_directory`

Continuously monitor a directory for changes and keep the graph updated.
- **Args**: `path` (string)
- **Returns**: Structured startup status including normalized fields such as `startup_action`, `index_validation`, and `recommended_next_tool`

Common `watch_directory` outcomes:
- `watching_fresh_index`: existing index matched the saved snapshot, watcher started immediately
- `watching_after_incremental_refresh`: small offline changes were reconciled, then watcher started
- `watching_unverified_index`: existing index was present but no saved snapshot existed
- `initial_index_started_and_watching`: first-time index was started, watcher attached
- `stale_index`: watcher refused to start because the repo needs a full re-index first

### `list_watched_paths`

List active watch roots.

- **Args:** None
- **Returns:** Paths under watch

### `unwatch_directory`

Stop watching a directory.

- **Args:** `path` (string)
- **Returns:** Success message

---

## Job control

### `list_jobs`

List background jobs (indexing, scans, etc.).

- **Args:** None
- **Returns:** Job list with status

### `check_job_status`

Poll a single job.

- **Args:** `job_id` (string)
- **Returns:** Status and progress

---

## Advanced querying

### `execute_cypher_query`

Read-only Cypher against the active backend (same graph model across FalkorDB, KuzuDB, Neo4j).

- **Args:** `cypher_query` (string)
- **Returns:** Tabular query results

### `visualize_graph_query`

Build a Neo4j Browser URL for visual exploration of a query (where Neo4j Browser applies).

- **Args:** `cypher_query` (string)
- **Returns:** URL string

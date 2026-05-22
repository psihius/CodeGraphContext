# Rebase Tracker: cgc/index-progress-and-speed onto main

Started: 2026-05-21
Branch: `cgc/index-progress-and-speed`
Base target: `main` (`cf61e024` at start)
Backup branch observed: `copy/index-progress-and-speed` (`5899408a`)
Original branch tip: `5899408a`
Merge base: `e642ca9cab4ba3f32c76d3666a56a0192e9d9ab1`

## Goals

- Rebase this branch onto current `main`.
- Preserve the branch's performance improvements where they still add value.
- Prefer upstream implementations when `main` has already solved the same issue in a compatible or better way.
- Preserve parity/correctness fixes from the branch, especially hidden-file handling, exact call-linking parity, local `.cgcignore` overlays, tree-sitter fallback behavior, MCP reindex/freshness workflows, and configurable batching.
- Keep decisions recorded so conflict resolution can be resumed or audited.

## Initial Risk Map

- `src/codegraphcontext/tools/graph_builder.py`: highest-risk overlap. Branch keeps many optimizations in this file; `main` refactored indexing into `src/codegraphcontext/tools/indexing/`.
- `src/codegraphcontext/tools/indexing/*`: introduced by `main`; branch changes may need to be ported into these modules rather than retained in `graph_builder.py`.
- `src/codegraphcontext/core/database_kuzu.py`: both sides changed batching, connection behavior, schema/parity details, and performance.
- `src/codegraphcontext/core/database_falkordb.py`: both sides changed constraints/performance/closing behavior.
- `src/codegraphcontext/cli/*`: both sides changed setup/config/indexing CLI behavior.
- `src/codegraphcontext/tools/handlers/*`: overlap around indexing, management, watcher, freshness/reindex workflows.
- `src/codegraphcontext/utils/tree_sitter_manager.py`: branch adds graceful missing grammar handling; main has parser/language additions.
- Tests: branch adds focused parity/performance tests; main adds large golden/parity fixtures and parser tests.

## Branch Commits To Replay

- [x] `a8d4c0b1` Improve indexing progress visibility - skipped during rebase; superseded by `main`'s indexing-module refactor and job progress handling. Revisit later only if phase-level progress from the fork is still missing.
- [x] `361446e8` Reduce indexing write-path overhead - skipped; old monolithic write-path optimization is superseded by `main`'s `GraphWriter` batching/refactor.
- [x] `c92bc61d` Add fast indexing knobs and Kuzu cache - skipped as a replay unit; old `graph_builder.py` fast paths and Kuzu cache conflict with newer `main` pipeline/Kuzu compatibility. `INDEX_CALLS` was ported post-rebase into the current Tree-sitter and SCIP pipelines.
- [x] `a097122e` Optimize discovery and skip empty linking passes - skipped as a replay unit; old discovery/linking optimizations target pre-refactor `graph_builder.py`. `INDEX_INHERITANCE` was ported post-rebase into the current Tree-sitter and SCIP pipelines.
- [x] `44ebc3cd` Preserve shell config overrides in CLI - applied as `6b61e6b7`.
- [x] `a6d9bf1b` Batch graph writes and call linking - skipped; old monolithic batching/call-linking conflicts with `main`'s writer/resolution split.
- [x] `32e5e675` Speed up repository deletion by path scope - skipped; upstream already includes scoped/batched repository deletion fixes.
- [x] `a2482560` Normalize batched array properties for Kuzu - skipped as old-location implementation; port needed in `GraphWriter` normalization.
- [x] `53a764cf` Batch file ingest and dedupe fresh edges - skipped; old `graph_builder.py` batching overlaps `main` writer/pipeline.
- [x] `033b8871` Restore parity-sensitive indexing paths - skipped as old `graph_builder.py` implementation; parity behavior must be reviewed against `main` pipeline/discovery.
- [x] `4ab3e913` Restore exact indexing parity - skipped as old-location implementation; final parity needs explicit validation.
- [x] `281d41a9` Cache repeated call-linking branch selection - skipped; old call-linking optimization must be evaluated in `resolution/calls.py`/`GraphWriter`.
- [x] `a92d0d24` Batch safe CALLS cache hits - skipped; old CALLS batching path moved to `GraphWriter`.
- [x] `ba66d31a` Batch exact call writes across files - skipped; old exact-call write batching maps to current `GraphWriter`.
- [x] `f87317f9` Batch imports by final edge state - skipped; import batching belongs in current `GraphWriter`.
- [x] `7599b602` Cache repeated call target resolution - skipped; review against current `resolution/calls.py`.
- [x] `c7141e7d` Avoid re-probing cached call branches - skipped; old call branch probe optimization belongs in current resolution/writer modules.
- [x] `f2b5ae6e` Checkpoint parity-safe indexing fixes and profiling - skipped as mixed old-architecture checkpoint; later focused commits cover portable behavior.
- [x] `17e817de` Add configurable write batch size and fix safe run params - partially applied as `79b0e82c`; config/validation kept, old graph-builder code dropped. `WRITE_BATCH_SIZE` was ported post-rebase as the current Tree-sitter pipeline's file scheduling batch window.
- [x] `128385c7` Add local cgcignore overlays - ported as `9bf51c51` into `core/cgcignore.py`, plus `.gitignore` and core tests.
- [x] `f92b497a` Expose end-to-end indexing timings - ported post-rebase into the current context-aware CLI helper flow.
- [x] `d207c9ca` Persist FalkorDB on graceful close - applied as `f231f190`.
- [x] `12a8847d` Fix exact CALLS class target fallback parity - skipped; current `resolution/calls.py` is class-aware, validate after rebase.
- [x] `d54d60af` Fix leftover rebase conflict marker - skipped; old cleanup no longer applies.
- [x] `92119fa7` Restore discovery compatibility helper - skipped; current discovery module supersedes helper.
- [x] `171fc088` Restore parity for hidden files and class calls - partially applied as `cef18f46`; kept hidden-file default, dropped old graph-builder changes.
- [x] `60f27f37` Document golden sample workflow - applied as `98c523a4`.
- [x] `6fc29f98` Add MCP index freshness and reindex workflows - applied as `4368d734`, with freshness ported onto current indexing facade and discovery APIs.
- [x] `6f307d60` Handle missing tree-sitter grammars gracefully - applied as `6b226af6`, adapted to current `get_parser` and pre-scan registry.
- [x] `e13bfc92` Improve FalkorDB indexing performance - partially applied as `5af118ca`; kept config/PHP parser pieces, dropped old graph-builder batching.
- [x] `5899408a` Add configurable node write chunking - applied as `6b4e1627`, ported to `GraphWriter`.

## Procedure

1. Confirm clean worktree and backup branch.
2. Enable local `rerere`.
3. Start `git rebase main`.
4. For each conflict:
   - Inspect upstream version, branch version, and surrounding architecture.
   - Decide whether to keep branch code, accept main code, or port branch behavior into main's newer module layout.
   - Record the decision below before continuing.
5. After rebase completes:
   - Search for conflict markers.
   - Run targeted tests around graph builder/indexing, database Kuzu/Falkor, tree-sitter fallback, MCP reindex/freshness, and CLI config.
   - Run broader tests if time and environment allow.

## Conflict Decisions

- `a8d4c0b1`: skipped. The commit applies progress hooks to the old monolithic `graph_builder.py`; `main` now routes Tree-sitter indexing through `tools/indexing/pipeline.py` and graph writes through `tools/indexing/persistence/writer.py`. Keeping the old implementation would undo the upstream refactor.
- `361446e8`: skipped. The commit only changes old `graph_builder.py` persistence internals; the equivalent responsibility moved to `tools/indexing/persistence/writer.py` on `main`.
- `c92bc61d`: skipped. The Kuzu translation cache conflicts with `main`'s newer compatibility rewrites, and the graph-builder changes target the pre-refactor monolith. Possible follow-up: port `INDEX_CALLS` into `tools/indexing/pipeline.py` if disabling CALLS remains desired.
- `a097122e`: skipped. Old discovery/linking skip paths are superseded by `tools/indexing/discovery.py` and `tools/indexing/pipeline.py`. Possible follow-up: port `INDEX_INHERITANCE` into the new pipeline together with `INDEX_CALLS`.
- `44ebc3cd`: kept `main`'s expanded credential loader and added the branch regression test for preserving arbitrary existing shell env variables. Commit created during rebase: `6b61e6b7`.
- `a6d9bf1b`: skipped. It rewrites old graph persistence and call linking inside `graph_builder.py`; `main` implements those responsibilities in `tools/indexing/persistence/writer.py` and `tools/indexing/resolution/calls.py`.
- `32e5e675`: skipped. Upstream history includes repository deletion fixes (`b837e50a`, `96335bba`, `da782274`) and current `main` delegates deletion through `GraphWriter`.
- `a2482560`: skipped. Behavior is still relevant, but implementation belongs in `tools/indexing/persistence/writer.py` now. Current writer normalizes list-typed columns, but it should be reviewed for dict entries like `{"name": "arg"}` and empty-list handling.
- `53a764cf`: skipped. Old file-ingest batching and relationship dedupe map to `GraphWriter`/pipeline responsibilities on `main`.
- `033b8871`: skipped. Parity-sensitive path behavior is important, but this commit applies it in the old monolith. Review against `tools/indexing/discovery.py` and `tools/indexing/pipeline.py` after replay.
- `4ab3e913`: skipped. Exact indexing parity behavior remains a validation target, but this old graph-builder patch cannot be replayed directly over upstream's refactor.
- `281d41a9`: skipped. Repeated call-linking branch selection is now split between `tools/indexing/resolution/calls.py` and `GraphWriter.write_function_call_groups`.
- `a92d0d24`: skipped. Safe CALLS cache-hit batching should be compared with current `GraphWriter.write_function_call_groups`.
- `ba66d31a`: skipped. Exact call writes are handled by `GraphWriter.write_function_call_groups` on `main`.
- `f87317f9`: skipped. Import edge batching should be reviewed in current `GraphWriter` import persistence code.
- `7599b602`: skipped. Repeated call target resolution caching belongs in `tools/indexing/resolution/calls.py` after the upstream split.
- `c7141e7d`: skipped. Avoiding repeated call branch probes should be reviewed in current call resolution/write code rather than old `graph_builder.py`.
- `f2b5ae6e`: skipped. It mostly patches old `graph_builder.py`; its server change removes `asyncio.to_thread`, which is not desirable against current `main`. Tree-sitter behavior is deferred to the later focused grammar fallback commit.
- `17e817de`: kept config keys and `WRITE_BATCH_SIZE` validation, dropped old `graph_builder.py` changes. Commit created during rebase: `79b0e82c`. Post-rebase fix wires `WRITE_BATCH_SIZE` into the current Tree-sitter pipeline as the file scheduling batch window; old file-write flush batching does not directly apply after upstream moved persistence into `GraphWriter`.
- `128385c7`: ported `.cgcignore.local` overlay support into `core/cgcignore.py` instead of old `graph_builder.py`. This benefits both indexing discovery and watcher paths because both call `build_ignore_spec`. Commit created during rebase: `9bf51c51`.
- `f92b497a`: initially skipped during rebase because the old patch conflicted with current context-aware CLI helpers. Post-rebase fix reintroduced `CommandTimingTracker` around `index_helper`/`reindex_helper` while preserving context and `cgcignore_path`.
- `d207c9ca`: applied cleanly as `f231f190`.
- `12a8847d`: skipped. Old exact CALLS cache implementation no longer exists; current class targets are grouped in `tools/indexing/resolution/calls.py`.
- `d54d60af`: skipped. It only cleaned up an old conflict marker in pre-refactor `graph_builder.py`.
- `92119fa7`: skipped. Compatibility helper targeted old `graph_builder.py`; discovery is now in `tools/indexing/discovery.py`.
- `171fc088`: kept `IGNORE_HIDDEN_FILES=false` default because parity depends on indexing hidden files unless explicitly disabled. Dropped old graph-builder class-linking changes; current `GraphWriter` uses `class_context_line` when available. Commit created during rebase: `cef18f46`.
- `60f27f37`: applied, keeping both the existing `CGC_SKIP_REINDEX` note and the golden-samples workflow. Commit created during rebase: `98c523a4`.
- `6fc29f98`: applied as `4368d734`. Important integration choices: kept path-traversal guard in indexing handlers, adapted index-state discovery to current `tools/indexing/discovery.py`, added freshness wrappers on current `GraphBuilder`, and made offline reconcile return a reindex-required response instead of using removed monolithic relink internals.
- `6f307d60`: applied as `6b226af6`. Ported unavailable parser caching to `GraphBuilder.get_parser`, made `pre_scan_for_imports` skip unavailable parsers, and adjusted fallback tests to current APIs.
- `e13bfc92`: applied as `5af118ca`. Kept `IGNORE_DIRS` merge/default updates and PHP parser improvements. Dropped old `graph_builder.py` Falkor batching because persistence now lives in `GraphWriter`.
- `5899408a`: applied as `6b4e1627`. Ported `CGC_NODE_WRITE_CHUNK_SIZE` / `CGC_FALKORDB_NODE_WRITE_CHUNK_SIZE` behavior to `tools/indexing/persistence/writer.py`.

## Post-Rebase Fixes

- Ported `INDEX_CALLS=false` and `INDEX_INHERITANCE=false` into `tools/indexing/pipeline.py` and `tools/indexing/scip_pipeline.py` so the config gates still disable expensive relationship-linking phases after the upstream indexing split.
- Ported `WRITE_BATCH_SIZE` into `tools/indexing/pipeline.py` as the Tree-sitter file scheduling batch size. The old branch used it for monolithic pending write flushes; upstream no longer has that file-batch writer path, so the preserved behavior is bounded indexing batches rather than resurrecting the old persistence layer.
- Ported CLI command timing summaries into current context-aware `index_helper` and `reindex_helper` flows, including process-exit timing summaries.
- Tightened `.cgcignore` parent lookup so non-git indexed roots do not inherit unrelated parent `.cgcignore` files. Valid git worktree parent lookup still works.
- Added phase metadata to `JobInfo` for MCP reindex/job-progress responses.
- Adjusted MCP routing tests to use the explicit event-loop lifecycle used by `cgc mcp start`; production `handle_tool_call` still uses `asyncio.to_thread`.
- Excluded `.codegraphcontext` metadata from index-state file discovery so persisted freshness manifests do not make themselves stale.

## Validation Log

- `python -m compileall -q src/codegraphcontext` - passed.
- `PYTHONPATH=src pytest tests/unit/core/test_cgcignore_core.py tests/unit/core/test_index_state.py tests/unit/core/test_jobs.py tests/unit/core/test_mcp_reindex_handlers.py tests/unit/core/test_tree_sitter_fallback.py tests/unit/core/test_indexing_config_gates.py tests/unit/cli/test_index_exit_codes.py tests/unit/parsers/test_php_parser.py -q` - passed: 35 tests.
- `timeout 60s env PYTHONPATH=src pytest tests/integration/mcp/test_mcp_server.py tests/integration/cli/test_cli_commands.py -vv -s -o faulthandler_timeout=10` - passed: 20 tests, 1 existing `datetime.utcnow()` deprecation warning in report generation.
- `rg -n '^<<<<<<<|^>>>>>>>' .` - no conflict markers found.
- `git diff --check` - passed.
- Notes from post-rebase fixes:
  - `.cgcignore` parent lookup now only treats valid git metadata markers as repository roots, avoiding accidental `/tmp/.git` escape during non-git indexing/tests.
  - `JobInfo` now carries phase metadata required by reindex/freshness MCP progress reporting.
  - MCP routing tests now match production's explicit loop lifecycle, avoiding `asyncio.run()` default-executor shutdown hangs without adding mock-aware production behavior.
  - Index-state discovery excludes `.codegraphcontext` metadata files so freshness snapshots do not become stale because of their own persisted manifest.

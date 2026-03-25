# 🧪 CodeGraphContext Testing Strategy

This document serves as the single source of truth for testing **CodeGraphContext**. It consolidates usage instructions, architectural philosophy, and future roadmap items.

---

## 🚀 Quick Start: Running Tests

We provide a helper script `tests/run_tests.sh` to simplify test execution.

| Suite | Command | Use Case |
| :--- | :--- | :--- |
| **All Tests** | `./tests/run_tests.sh all` | Full CI/CD verification (includes E2E). |
| **Fast Tests** | `./tests/run_tests.sh fast` | **Recommended for local dev.** Runs Unit + Integration. |
| **Unit Tests** | `./tests/run_tests.sh unit` | Focus on individual components (parsers, database logic). |
| **User Journeys** | `./tests/run_tests.sh e2e` | Validate full end-to-end user workflows. |

---

## 🏗️ Test Architecture

The test suite follows the **Testing Pyramid** principle, ensuring a balanced mix of speed and confidence.

### 1. `tests/unit/` (Bottom Layer)
*   **Speed:** Very Fast (< 100ms)
*   **Scope:** Isolated classes and functions.
*   **Mocking:** Heavy mocking of external dependencies (Neo4j, FileSystem).
*   **Content:**
    *   `core/`: `DatabaseManager`, `JobManager`, `FileWatcher`.
    *   `parsers/`: Output verification for `TreeSitterParser` (Python, JS, etc.).
    *   `tools/`: `GraphBuilder` logic, `CodeFinder` query generation.

### 2. `tests/integration/` (Middle Layer)
*   **Speed:** Fast (~1s)
*   **Scope:** Interaction between 2+ components.
*   **Mocking:** Partial (e.g., mock the database connection but run the real `GraphBuilder` logic).
*   **Content:**
    *   `cli/`: Typer command execution, argument parsing, error handling.
    *   `mcp/`: Server routing, tool call validation, JSON protocol adherence.

### 3. `tests/e2e/` (Top Layer)
*   **Speed:** Slow (> 10s)
*   **Scope:** Full system as seen by the user.
*   **Mocking:** Minimal/None (uses real file interactions, simulated sub-processes).
*   **Content:**
    *   `test_user_journeys.py`: "User initializes repo", "User queries function callers", "User exports bundle".

### 4. `tests/perf/` (Side Quest)
*   **Scope:** Benchmarks for large codebase indexing and complex query latency.

---

## ✅ What We Test

### 1. User Workflows & Journeys
We simulate real-world usage to ensure the product solves user problems.
*   **First-time Setup:** Initialization -> Indexing -> Verifying output.
*   **Daily Dev:** Watching for file changes -> Auto-updating graph.
*   **Code Search:** Finding functions by name, argument, or decorator.

### 2. CLI Functionality
Every command in `cgc --help` is tested.
*   `index`: Argument validation, force flags.
*   `find/analyze`: Query construction and output formatting.
*   `mcp`: Server startup and tool exposure.

### 3. Language Support (Parsers)
We verify that our Tree-sitter parsers correctly extract:
*   **Structure:** Classes, Functions, Modules.
*   **Relationships:** Calls, Inheritance, Imports, Dependencies.
*   **Languages Covered:** Python, JavaScript/TypeScript, Java, C++, Go, Rust, Ruby, PHP, Dart, Perl, and more.

---

## 🧷 Golden Samples For Parity

Use golden samples for any change that can alter the indexed graph shape or
database-visible answers:
*   File discovery and ignore handling
*   Call resolution and inheritance linking
*   Import creation
*   Backend-specific write behavior

### Artifact Layout

Keep local golden samples outside the repo under:

```bash
CGC_GOLDEN_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/cgc-compare/golden-samples"
```

Use this naming convention:
*   Baseline from `main`: `<repo>-main-<backend>/`
*   Current branch candidate: `<repo>-current-<backend>/`
*   Portable export when supported by the backend/runtime: `<repo>-main-<backend>.cgc`
*   Logs and timings: `$CGC_GOLDEN_ROOT/logs/`

For backend-native snapshots:
*   **KuzuDB:** preserve `.codegraphcontext/kuzudb`
*   **FalkorDB Lite:** preserve `.codegraphcontext/falkordb.db`
*   **Neo4j:** preserve the container bind-mounted `data/` and `logs/` directories

### Rules That Matter

1.  Build goldens from a clean detached worktree of `CodeGraphContext` `main`.
2.  Index a disposable target worktree, not your live repo checkout.
3.  Use an isolated `HOME` per sample so local config does not leak into the run.
4.  If the target repo relies on local ignore overlays not understood by `main`
    (for example, a `.cgcignore.local` file), copy or merge those rules into the
    disposable target worktree before indexing. Do not mutate the live repo.
5.  For FalkorDB Lite, use a short Unix socket path under `/tmp`. `redislite`
    fails once the socket path exceeds the Unix-domain limit (roughly 108
    characters), which is easy to hit under deep cache directories.

### FalkorDB Golden Example

Run this from the detached `CodeGraphContext` `main` worktree:

```bash
export CGC_GOLDEN_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/cgc-compare/golden-samples"
export SAMPLE_ROOT="$CGC_GOLDEN_ROOT/mago-main-falkordb"
export TARGET_REPO="/tmp/cgc-golden-targets/mago-current"
export FALKORDB_SOCKET_PATH="/tmp/cgc-mago-main-falkordb.sock"
export PYTHONPATH=src
export HOME="$SAMPLE_ROOT"
export DEFAULT_DATABASE=falkordb
export FALKORDB_PATH="$SAMPLE_ROOT/.codegraphcontext/falkordb.db"

python cgc_entry.py index "$TARGET_REPO" --force
python cgc_entry.py bundle export "$SAMPLE_ROOT/mago-main-falkordb.cgc" --repo "$TARGET_REPO" --no-stats
rm -f "$FALKORDB_SOCKET_PATH"
```

### Neo4j Golden Example

Start a dedicated Neo4j container with bind mounts under the sample root, then
run the same detached `main` worktree against it:

```bash
export CGC_GOLDEN_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/cgc-compare/golden-samples"
export SAMPLE_ROOT="$CGC_GOLDEN_ROOT/mago-main-neo4j"
export TARGET_REPO="/tmp/cgc-golden-targets/mago-current"

mkdir -p "$SAMPLE_ROOT/data" "$SAMPLE_ROOT/logs"
docker run -d --name cgc-neo4j-golden-mago-main \
  -p 7691:7687 -p 7481:7474 \
  -e NEO4J_AUTH=neo4j/codegraph123 \
  -v "$SAMPLE_ROOT/data:/data" \
  -v "$SAMPLE_ROOT/logs:/logs" \
  neo4j:5.15.0

export PYTHONPATH=src
export HOME="$SAMPLE_ROOT"
export DEFAULT_DATABASE=neo4j
export NEO4J_URI=bolt://localhost:7691
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=codegraph123
export NEO4J_DATABASE=neo4j

python cgc_entry.py index "$TARGET_REPO" --force
docker stop cgc-neo4j-golden-mago-main
```

If `cgc bundle export` succeeds on your Neo4j runtime, keep the `.cgc` file as
well. On the locally validated `main` baseline used for this work, the native
Neo4j snapshot was valid but bundle export failed during schema JSON
serialization because Neo4j returned a `DateTime` object.

### Comparing Against Goldens

For KuzuDB exact graph parity, compare the preserved baseline and candidate DBs
with:

```bash
python "${XDG_CACHE_HOME:-$HOME/.cache}/cgc-compare/compare_cgc_graphs.py" \
  --baseline-db "$CGC_GOLDEN_ROOT/<repo>-main-kuzudb/.codegraphcontext/kuzudb" \
  --optimized-db "$CGC_GOLDEN_ROOT/<repo>-current-kuzudb/.codegraphcontext/kuzudb" \
  --report-json "$CGC_GOLDEN_ROOT/reports/<repo>.json" \
  --report-md "$CGC_GOLDEN_ROOT/reports/<repo>.md"
```

At minimum, keep the backend-native snapshot. Also keep a `.cgc` export when
that export path succeeds for the backend and runtime you are validating.

---

## 🛠️ How to Add Tests

### Adding a New Language Parser
1.  Create `tests/unit/parsers/test_<lang>_parser.py`.
2.  Use the `get_tree_sitter_manager()` singleton.
3.  Feed it a sample code string.
4.  Assert the structure of the returned definition dict.

### Adding a New CLI Command
1.  Create/Edit `tests/integration/cli/test_cli_commands.py`.
2.  Mock the underlying service (e.g., `GraphBuilder` or `CodeFinder`).
3.  Use `CliRunner` from `typer.testing` to invoke the command.
4.  Assert `result.exit_code == 0` and check `result.stdout`.

### Adding a Regression Test
1.  Identify the bug workflow.
2.  Create a test case in `tests/e2e/test_user_journeys.py` that reproduces it.
3.  Fix the bug and verify the test passes.

---

## 🔮 Future Roadmap (Ideas)

These ideas are consolidated from the legacy `IDEAL_TEST_PLAN.md`.

### 1. Advanced Performance Benchmarks
*   **Idea**: Test indexing on > 100k LoC repositories (e.g., use an archived version of React or Django as a fixture).
*   **Metric**: Indexing time per 1000 lines, Memory usage peak.

### 2. Mutation Testing
*   **Idea**: Use a tool like `mutmut` to introduce random bugs in the code and verify the test suite catches them.

### 3. Snapshot Testing for Parsers
*   **Idea**: Instead of asserting specific keys, verify the entire JSON output of a parser against a stored "snapshot". This makes updating parser tests much faster when schema changes.

### 4. Testcontainers Integration
*   **Idea**: In E2E tests, spin up a real Docker container for Neo4j/FalkorDB to guarantee 100% accurate database behavior, removing all mocks.

### 5. Multi-Repo Analysis Workflows
*   **Idea**: E2E tests simulating a user querying calls *across* two different repositories (microservices scenario).

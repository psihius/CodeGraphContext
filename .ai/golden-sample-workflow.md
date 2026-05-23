# Golden Sample Workflow

This is a living protocol for rebuilding and comparing golden sample graphs
while rebasing the optimization branch onto upstream `main`.

The upstream-facing goal is to make this workflow reproducible enough that it
can become a documented parity/performance validation process, not a one-off
local script.

## Current Run Context

- CGC optimized branch: `cgc/index-progress-and-speed`
- CGC optimized commit: `94c37bb1`
- CGC main worktree: `/home/psihius/projects/CodeGraphContext-main-base`
- CGC main commit: `cf61e024`
- sample repository: `/home/psihius/projects/mago`
- sample repository commit: `0b4c61675bf41f04e21957467f99703e5482649d`
- disposable sample checkout:
  `/tmp/cgc-golden-targets/mago-current`
- golden output root:
  `/home/psihius/.cache/cgc-compare/golden-samples`
- database backend for this pass: `kuzudb`
- Python used for both branches:
  `/home/psihius/.local/share/pipx/venvs/codegraphcontext/bin/python`

## Required Rule: Disposable Target Ignore Files

The sample repository can have local ignore overlays that are not tracked by
Git. For `mago`, both of these files exist in the live repository and are
ignored through `.git/info/exclude`:

- `.cgcignore`
- `.cgcignore.local`

Because older `main` may not support `.cgcignore.local`, the disposable target
must contain one effective `.cgcignore` file with both sources concatenated:

1. the live repository `.cgcignore`
2. a marker comment
3. the live repository `.cgcignore.local`

This must be verified before indexing either branch:

```bash
sed -n '1,260p' /tmp/cgc-golden-targets/mago-current/.cgcignore
git -C ../mago check-ignore -v .cgcignore .cgcignore.local || true
find /tmp/cgc-golden-targets/mago-current -maxdepth 2 \
  \( -name '.cgcignore' -o -name '.cgcignore.local' -o -name '.gitignore' \) \
  -print
```

The disposable target should not rely on `.cgcignore.local` being present,
because this pass intentionally compares latest `main` against the optimized
branch and both branches must see the same effective input set.

## Invalidated Baseline

The first `mago-main-latest-kuzudb` baseline built during this session is
invalid.

Cause:

- the disposable target contained only the `.cgcignore.local` patterns
- the base `.cgcignore` patterns from `../mago` were missing
- `git status` did not show the problem because `.cgcignore` is ignored by the
  sample repository's `.git/info/exclude`

Observed consequence:

- main baseline indexing took `5092.94s` wall time
- sampled RSS exceeded 35GB
- resulting Kuzu DB was about `267M`

Decision:

- discard that baseline
- rebuild with the corrected effective `.cgcignore`
- record max RSS via `/usr/bin/time -v` for all rebuilds

## Corrected Main Baseline Command

```bash
set -euo pipefail
CGC_GOLDEN_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/cgc-compare/golden-samples"
SAMPLE_ROOT="$CGC_GOLDEN_ROOT/mago-main-latest-kuzudb"
TARGET_REPO="/tmp/cgc-golden-targets/mago-current"
LOG_DIR="$CGC_GOLDEN_ROOT/logs"
PY=/home/psihius/.local/share/pipx/venvs/codegraphcontext/bin/python

rm -rf "$SAMPLE_ROOT"
mkdir -p "$SAMPLE_ROOT" "$LOG_DIR"
cd /home/psihius/projects/CodeGraphContext-main-base

/usr/bin/time -v env \
  PYTHONPATH=src \
  HOME="$SAMPLE_ROOT" \
  DEFAULT_DATABASE=kuzudb \
  CGC_RUNTIME_DB_PATH="$SAMPLE_ROOT/.codegraphcontext/global/db/kuzudb" \
  "$PY" cgc_entry.py index "$TARGET_REPO" --force \
  > "$LOG_DIR/mago-main-latest-kuzudb-index.log" 2>&1

cp "$LOG_DIR/mago-main-latest-kuzudb-index.log" "$SAMPLE_ROOT/index.log"
```

Corrected main baseline result:

- status: completed successfully
- app-reported indexing time: `759.39 seconds`
- `/usr/bin/time -v` wall time: `12:52.41`
- max RSS: `10347644 KB`
- swaps: `0`
- Kuzu DB size: `147M`
- unresolved call relationships skipped: `43453`

Interpretation:

- the earlier 35GB-plus RSS sample was from an invalid input set
- with the effective `mago` ignore rules restored, latest `main` still uses
  about 10GB RSS on this sample
- the corrected baseline is valid for comparison with the optimized branch

## Optimized Branch Command

Run only after the corrected main baseline completes successfully:

```bash
set -euo pipefail
CGC_GOLDEN_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/cgc-compare/golden-samples"
SAMPLE_ROOT="$CGC_GOLDEN_ROOT/mago-current-latest-kuzudb"
TARGET_REPO="/tmp/cgc-golden-targets/mago-current"
LOG_DIR="$CGC_GOLDEN_ROOT/logs"
PY=/home/psihius/.local/share/pipx/venvs/codegraphcontext/bin/python

rm -rf "$SAMPLE_ROOT"
mkdir -p "$SAMPLE_ROOT" "$LOG_DIR"
cd /home/psihius/projects/CodeGraphContext

/usr/bin/time -v env \
  PYTHONPATH=src \
  HOME="$SAMPLE_ROOT" \
  DEFAULT_DATABASE=kuzudb \
  CGC_RUNTIME_DB_PATH="$SAMPLE_ROOT/.codegraphcontext/global/db/kuzudb" \
  "$PY" cgc_entry.py index "$TARGET_REPO" --force \
  > "$LOG_DIR/mago-current-latest-kuzudb-index.log" 2>&1

cp "$LOG_DIR/mago-current-latest-kuzudb-index.log" "$SAMPLE_ROOT/index.log"
```

## Monitoring Commands

Use these while long indexes are running:

```bash
pgrep -af 'cgc_entry.py index /tmp/cgc-golden-targets/mago-current --force'
free -h
du -sh \
  ~/.cache/cgc-compare/golden-samples/mago-main-latest-kuzudb/.codegraphcontext/global/db/kuzudb \
  ~/.cache/cgc-compare/golden-samples/mago-main-latest-kuzudb/.codegraphcontext/global/db/kuzudb.wal \
  2>/dev/null || true
stat -c '%y %s %n' \
  ~/.cache/cgc-compare/golden-samples/mago-main-latest-kuzudb/.codegraphcontext/global/db/kuzudb \
  ~/.cache/cgc-compare/golden-samples/mago-main-latest-kuzudb/.codegraphcontext/global/db/kuzudb.wal \
  2>/dev/null || true
```

For the optimized branch, replace `mago-main-latest-kuzudb` with
`mago-current-latest-kuzudb`.

Important monitoring policy:

- database or WAL growth means the job is probably still making progress
- `/usr/bin/time -v` max RSS is more reliable than occasional `ps` samples
- memory over 30GB on this sample is a serious signal to investigate, not just
  an acceptable cost of golden generation

## Compare Command

```bash
mkdir -p ~/.cache/cgc-compare/golden-samples/reports

/home/psihius/.local/share/pipx/venvs/codegraphcontext/bin/python \
  ~/.cache/cgc-compare/compare_cgc_graphs.py \
  --baseline-db ~/.cache/cgc-compare/golden-samples/mago-main-latest-kuzudb/.codegraphcontext/global/db/kuzudb \
  --optimized-db ~/.cache/cgc-compare/golden-samples/mago-current-latest-kuzudb/.codegraphcontext/global/db/kuzudb \
  --report-json ~/.cache/cgc-compare/golden-samples/reports/mago-main-latest-vs-current-latest-kuzudb.json \
  --report-md ~/.cache/cgc-compare/golden-samples/reports/mago-main-latest-vs-current-latest-kuzudb.md
```

Expected acceptance criteria:

- `Exact match: True`
- `Mismatch groups: 0`
- compare report is saved under `golden-samples/reports`
- both index logs include `/usr/bin/time -v` resource usage

## Corrected Optimized Branch Result

- status: completed successfully
- app-reported indexing time: `677.14 seconds`
- command total: `686.37s`
- process total: `687.16s`
- `/usr/bin/time -v` wall time: `11:28.69`
- max RSS: `10320476 KB`
- swaps: `0`
- Kuzu DB size: `148M`
- unresolved call relationships skipped: `43453`

Performance comparison against corrected latest `main`:

- app-reported graph build: `759.39s` main vs `677.14s` optimized
- wall time: `12:52.41` main vs `11:28.69` optimized
- max RSS: `10347644 KB` main vs `10320476 KB` optimized

## Corrected Compare Result

Report files:

- `/home/psihius/.cache/cgc-compare/golden-samples/reports/mago-main-latest-vs-current-latest-kuzudb.md`
- `/home/psihius/.cache/cgc-compare/golden-samples/reports/mago-main-latest-vs-current-latest-kuzudb.json`

Result:

- `Exact match: False`
- mismatch groups: `4`

Mismatch summary:

- `node:Module`
  - counts match: `1919` vs `1919`
  - rows differ: `297` only in each side
- `node:Variable`
  - main count: `812`
  - optimized count: `220`
  - main-only rows: `592`
- `rel:CONTAINS:File->Variable`
  - main count: `812`
  - optimized count: `220`
  - main-only rows: `592`
- `rel:IMPORTS:File->Module`
  - counts match: `15149` vs `15149`
  - rows differ: `84` only in each side

Initial interpretation:

- this is no longer an ignore-file artifact; both branches used the same
  corrected disposable target
- unresolved-call counts match exactly, so the current drift appears isolated
  to module/import identity details and PHP variable extraction
- the variable drift includes main-only PHP variables from
  `scripts/update-sponsors-docs.php`
- further investigation is required before this optimized branch can be treated
  as parity-clean against latest `main`

## Mismatch Triage

### PHP Variable Drift

Cause:

- the optimized branch changed `src/codegraphcontext/tools/languages/php.py`
- latest `main` captures every `(variable_name)` node
- the optimized branch captures only:
  - property elements
  - simple parameters
  - assignment left-hand variables

Example changed behavior:

- latest `main` captures read-use variables such as `$sponsor` in
  `scripts/update-sponsors-docs.php`
- the optimized branch intentionally omits those read-use variables

Relevant branch test:

- `tests/unit/parsers/test_php_parser.py`
- test name: `test_php_variables_only_capture_declaration_like_sites`

Action taken:

- reverted the optimized branch back to latest-main style broad
  `(variable_name)` capture
- updated `tests/unit/parsers/test_php_parser.py` so the test now asserts
  broad variable capture instead of declaration-like capture only
- latest compare after the fix shows `node:Variable` and
  `rel:CONTAINS:File->Variable` match exactly again

### Import And Module Drift

Observed shape:

- `IMPORTS` counts match exactly
- `Module` counts match exactly
- mismatches are row identity/property mismatches, not broad missing files

Strong example:

- source file:
  `crates/linter/src/rule/redundancy/no_iterator_to_array_in_foreach.rs`
- it imports `indoc::indoc` twice:
  - line `1`
  - line `124`
- latest `main` materialized the `File -> Module(indoc)` relationship with
  line `1`
- optimized branch materialized the same relationship with line `124`

Confirmed cause:

- the writer uses `MERGE (f)-[r:IMPORTS]->(m)` where `m` is keyed only by
  `Module.name`
- duplicate imports from the same file to the same module collapse into one
  relationship
- whichever duplicate row writes last wins the relationship properties
- `Module.full_import_name` is also first-writer-sensitive because `Module` is
  keyed only by `name`
- write scheduling changes can alter which property row survives, but this is
  only exposing an existing graph-model nondeterminism

Actions taken:

- removed the branch's repository-level file scheduling batch from
  `src/codegraphcontext/tools/indexing/pipeline.py`
- removed the now unsafe `WRITE_BATCH_SIZE` config surface
- reverted PHP variable extraction drift
- added per-file import-row deduplication to both:
  - `src/codegraphcontext/tools/indexing/persistence/writer.py`
  - `src/codegraphcontext/tools/graph_builder.py`
- changed duplicate `IMPORTS` relationship property writes to keep existing
  relationship properties instead of overwriting them
- verified the duplicate-import behavior on a tiny one-file Kuzu sample:
  duplicate `use indoc::indoc;` rows now leave the relationship at the first
  parser capture line

Interpretation:

- this drift is an order-sensitive materialization problem, not a discovery
  problem
- the graph model currently cannot represent duplicate imports from the same
  file to the same module without losing one row's properties
- exact parity against a single latest-main baseline can fail even when counts
  and source inputs match, because latest `main` also stores arbitrary
  representative import/module properties for collisions

Potential fixes to evaluate:

- make import relationship identity include enough data to preserve duplicate
  imports, if the graph schema should represent them
- otherwise deduplicate imports deterministically before writing, choosing a
  documented canonical row such as the lowest line number
- make `Module.full_import_name` deterministic for duplicate `Module.name`
  collisions, or remove it from exact parity if the property is only an
  arbitrary representative
- preserve latest-main async/write ordering only as a temporary compatibility
  measure; it does not solve the underlying nondeterminism

Latest post-fix compare:

- optimized app-reported indexing time: `665.99 seconds`
- optimized wall time: `11:17.45`
- optimized max RSS: `10387660 KB`
- `node:Variable`: exact
- `rel:CONTAINS:File->Variable`: exact
- remaining mismatch groups: `2`
  - `node:Module`
  - `rel:IMPORTS:File->Module`

Important conclusion:

- the branch-specific PHP graph break is fixed
- the remaining mismatch is a real graph consistency issue in import/module
  materialization that latest `main` also has; the branch's optimization work
  makes it visible because timing changes alter which arbitrary row wins
- upstream protocol should treat this as a schema/writer correctness issue, not
  as an optimization-only issue

## Deterministic Import Canonicalization

Decision:

- the branch should fix the import/module nondeterminism instead of preserving
  latest `main`'s arbitrary winner behavior

Implemented rule:

- `Module.full_import_name` is canonicalized to the module identity (`name`)
- source import statements remain on `IMPORTS.full_import_name`
- duplicate collapsed `File -> Module` import rows use a deterministic
  representative:
  1. lowest positive `line_number`
  2. `full_import_name`
  3. `imported_name`
  4. `alias`

Validated locally:

- tiny one-file Kuzu repro with duplicate `use indoc::indoc;`
- result:
  - `Module.full_import_name`: `indoc`
  - `IMPORTS.full_import_name`: `use indoc::indoc;`
  - `IMPORTS.line_number`: `1`

Expected compare impact against latest `main`:

- `node:Module` now intentionally differs for all module rows because latest
  `main` stores arbitrary import statements on `Module.full_import_name`
- `rel:IMPORTS:File->Module` differs where latest `main` stored a
  non-canonical duplicate import row
- this should be presented upstream as an intentional graph correctness fix
  that requires rebuilding golden baselines under the new deterministic rule

Branch-vs-branch determinism proof:

- first deterministic branch sample:
  `/home/psihius/.cache/cgc-compare/golden-samples/mago-current-latest-kuzudb`
- repeat deterministic branch sample:
  `/home/psihius/.cache/cgc-compare/golden-samples/mago-current-repeat-kuzudb`
- repeat build timing:
  - app-reported indexing time: `707.58 seconds`
  - wall time: `12:00.58`
  - max RSS: `10412944 KB`
- compare report:
  `/home/psihius/.cache/cgc-compare/golden-samples/reports/mago-current-latest-vs-repeat-kuzudb.md`
- result:
  - `Exact match: True`
  - mismatch groups: `0`

This confirms the branch now produces a stable Kuzu graph for the `mago`
sample under repeated builds with the same inputs.

## Upstream Protocol Notes To Preserve

- Golden samples must record both the CGC commit and the sample repository
  commit.
- Sample ignore inputs must be part of the artifact metadata; local ignore
  overlays are easy to miss.
- When comparing a branch that supports `.cgcignore.local` against one that
  does not, create a disposable target with a branch-neutral effective
  `.cgcignore`.
- Long-running golden jobs should be monitored through datastore growth and
  max RSS, not just terminal output.
- A baseline with incorrect file discovery inputs is invalid even if the index
  completes and the graph compare later passes.

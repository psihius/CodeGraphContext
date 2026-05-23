# CodeGraphContext Optimization Notes

This folder tracks the local optimization work on top of `main`, the parity
requirements that now gate further changes, and the next optimization steps.

Files:

- `parity-guardrails.md`
  What must remain stable, what drift is acceptable or not, and how parity is
  verified before changes are considered safe.
- `changes-against-main.md`
  Summary of the commit stack on `cgc/index-progress-and-speed` relative to
  `main`, including what was kept, what had to be rolled back for parity, and
  what remains relevant for a PR.
- `status.md`
  Current measured results, validated test state, and the parity proof on
  `mago`.
- `optimization-plan.md`
  Next optimization targets and how they should be validated.
- `golden-sample-workflow.md`
  Living protocol and tracker for rebuilding golden sample graphs from latest
  `main`, comparing them against the optimization branch, and preserving
  upstream-ready workflow decisions.

Current branch:

- `cgc/index-progress-and-speed`
- verified parity commit: `c7af25c`

Primary external artifact:

- parity report: `/home/psihius/.cache/cgc-compare/reports/mago-base-vs-optimized.md`

Current optimization policy:

- optimize the single-process pipeline before attempting parallelism
- keep discovery, ordering, and final graph writes deterministic
- only parallelize stages that are proven independent after single-process
  hotspots have been reduced

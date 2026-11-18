# Development

Use Python 3.13 and a project-local uv environment. NVC is required for simulator
tests. From the source checkout:

```console
uv sync --locked --group docs
uv run pytest -q
uv run pyrefly check
uv run ruff format --check .
uv run ruff check .
uv run --locked --group docs sphinx-build -M html docs docs/_build -n -W --keep-going
uv run --locked --group docs sphinx-build -M doctest docs docs/_build -n -W --keep-going
```

Open `docs/_build/html/index.html` to preview the site. Sphinx runs the numeric
doctests. `tests/test_simulation.py` runs the cocotb examples as well as the
stream regressions.

The simulator regression uses VHDL-2008 and both values of
`COCOTB_TRUST_INERTIAL_WRITES`. It includes full-rate spacing, backpressure,
records, scalar payloads, optional signals, meta-values, reset monitoring,
and cancellation. The tested baseline is Python 3.13.5, cocotb 2.1.0,
and NVC 1.21.1 on Linux.

`tests/test_distribution.py` builds an sdist and a wheel from it, checks their
contents, installs only declared runtime dependencies in a fresh environment,
and runs the packaged vector/record example under NVC in both write modes.

## Reliability and coverage

```console
uv run python tests/run_reliability.py
uv run python tests/run_reliability.py --seeds 73 2028 --rounds 240
uv run python tests/run_reliability.py --mutations
uv run python tests/run_coverage.py
uv run python tests/run_numeric_mutations.py
```

Ordinary regression uses seeds `73`, `2028`, and `65537`, with 24 lifecycle
rounds per seed in each write mode. Independent wire peers check acceptance,
ordering, stalled signals, and repeated recovery.

The extended reliability run defaults to seeds `0..7` and 120 lifecycle rounds
in each mode. Failures include the seed and recent traffic history.
Mutation checks use temporary faulty copies, leaving the working library
unchanged. A successful run writes `reliability-results.json`.
Do not disable assertions with `-O` or `PYTHONOPTIMIZE`.

Coverage combines Python and cocotb branch data into `coverage.json` and
`htmlcov/` for review. Use uncovered paths to guide investigation; executing
every branch does not establish that its assertions detect wrong results.

Numeric tests compare bits, widths, ranges, and warnings against an independent
NVC `numeric_std` oracle, with C intrinsics enabled and disabled. Expected
Python exceptions are classified before evaluating a case; an unexpected
exception fails the test. A separate error oracle requires compilation to
succeed and the intended runtime diagnostic to follow. Both use bounded
subprocess timeouts.

All binary arithmetic and ordinary comparisons are also checked for every
pair of literal-bit operands at widths one through five, including mixed
widths. Python integer mathematics and explicit modulo encoding supply the
expected results. Other tests check 521-bit conversion patterns, distinct
null-array bounds, and cocotb resolver settings in fresh interpreters.

`run_numeric_mutations.py` checks eleven selected faults in temporary copies.
Each selected test must pass against an unmodified copy first. Mutant runs
must execute the same test cases and fail at the intended assertion during
the test call. Collection errors, fixture failures, unrelated exceptions,
skips, and timeouts fail the harness. Successful runs write
`numeric-mutation-results.json`; they do not modify the working package.
These probes test specific assertions and do not measure all possible faults.

## Releases and hosting

The repository's `RELEASING.md` describes Trusted Publishing setup and recovery.
Pushing a `v*` tag publishes to production PyPI after validation, version-match
checks, and any GitHub environment approvals. Manual runs support both indices.
Do not move a published tag or attempt to replace uploaded release files.

The documentation workflow builds pull requests targeting `master` and deploys
only `master` to GitHub Pages. The site follows the current development branch.
Set the GitHub Pages source to GitHub Actions.

`ARCHITECTURE.md` describes the implementation, and `AGENTS.md` records
development and writing requirements. These files and `RELEASING.md` are in
the repository root.

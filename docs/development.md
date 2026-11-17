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

The HTML entry point is `docs/_build/html/index.html`. Documentation builds
do not run simulations. The numeric examples can run with Sphinx's doctest
builder; the runnable tutorial is included from the simulator-tested source.

The simulator regression uses VHDL-2008 and both values of
`COCOTB_TRUST_INERTIAL_WRITES`. It includes full-rate spacing, backpressure,
records, scalar payloads, optional signals, meta-values, reset monitoring,
and cancellation. The tested baseline is Python 3.13.5, cocotb 2.1.0,
and NVC 1.21.1 on Linux. This does not establish support for other simulators
or every permitted dependency version.

`tests/test_distribution.py` builds an sdist and a wheel from it, checks their
contents, installs only declared runtime dependencies in a fresh environment,
and runs the packaged vector/record example under NVC in both write modes.
No package publication is performed.

## Reliability and coverage

```console
uv run python tests/run_reliability.py
uv run python tests/run_reliability.py --seeds 73 2028 --rounds 240
uv run python tests/run_reliability.py --mutations
uv run python tests/run_coverage.py
```

Ordinary regression uses seeds `73`, `2028`, and `65537`, with 24 lifecycle
rounds per seed in each write mode. Independent wire peers check acceptance,
ordering, stalled signals, and repeated recovery.

The extended reliability run defaults to seeds `0..7` and 120 lifecycle rounds
in each mode. Failures include the seed and recent traffic history.
Mutation checks use temporary faulty copies, leaving the working library
unchanged. A successful run writes `reliability-results.json`. These checks
sample assertion strength; they cannot prove the absence of defects.
Do not disable assertions with `-O` or `PYTHONOPTIMIZE`.

Coverage combines Python and cocotb branch data into `coverage.json` and
`htmlcov/`. It has no percentage gate.

## Releases and hosting

The repository's `RELEASING.md` describes Trusted Publishing setup and recovery.
Pushing a `v*` tag publishes to production PyPI after validation, version-match
checks, and any GitHub environment approvals. Manual runs support both indices.
Do not move a published tag or attempt to replace uploaded release files.

The documentation workflow builds pull requests targeting `master` and deploys
only `master` to GitHub Pages. There is one current site, with no versioned
manuals or pull-request deployments. Publishing requires Pages to use GitHub
Actions as its source.

`ARCHITECTURE.md` describes the implementation, and `AGENTS.md` records
development and writing requirements. These files and `RELEASING.md` are in
the repository root.

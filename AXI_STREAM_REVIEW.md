# AXI_STREAM_REVIEW.md
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

# AXI4-Stream static and coverage-guided review

Baseline: `e012b85`, the completed first AXI4-Stream slice. This review stays
within that scope; it adds no new protocol features or timing abstractions.

## Findings and repairs

1. **Late failure for an invalid mandatory binding.** Direct construction of
   `AxiStreamBus` accepted `valid=None`, unlike the named binding path. Endpoint
   construction then failed with an unrelated attribute error. Both paths now
   validate mandatory valid immediately. Malformed direct controls also produce
   `SignalBindingError`, rather than an attribute error while formatting it.
   `tests/test_validation.py` covers absent/non-handle valid arguments.
2. **Unobserved reset-watcher failures.** An immutable scalar/one-bit reset
   handle passed binding, but cocotb refuses its ValueChange callback.
   Monitored constants/generics now fail synchronously with a named binding
   error. Unexpected watcher exceptions are generation-guarded, preserve the
   first fault, invalidate pending work and reach callers through endpoint
   operations. They require explicit initialisation and cannot silently reopen
   the endpoint through a pin-release task.
3. **Insufficient conversion diagnostics.** Width/value failures inside a
   record or sideband previously lost the failing signal's identity. Errors
   now name the HDL leaf/sideband, retaining the exception class and cause.
   Frame identity changes identify the zero-based entry and old/new identities.
   Atomic record validation still leaves all fields unchanged on failure.

Failing regressions were run before the repairs. The repaired cases pass under
both NVC inertial-write modes. The watcher-registration test deliberately
injects a backend failure; the constant-reset test uses an actual VHDL generic.
These findings concern validation, background error delivery and diagnostics;
this review established no further silent data-corruption or handshake defect.

## Coverage collection and interpretation

Coverage.py 7.17.2 is a development-only dependency, locked in uv.lock.
Run:

```console
uv run python tests/run_coverage.py
```

The runner measures coaxi in pytest and in Python embedded in NVC using cocotb's
native coverage hook. It combines per-process files and writes `coverage.json`
and `htmlcov/index.html`. The separate wheel installation remains runtime-only
and deliberately disables coverage collection there.

| Metric | Original suite | Reviewed implementation and strengthened suite |
| --- | ---: | ---: |
| Statements | 702/717 (97.9%) | 723/733 (98.6%) |
| Branch outcomes | 264/284 (93.0%) | 273/290 (94.1%) |

The denominator changes because the repair adds validation and fault handling.
The terminal tool's headline combines statement and branch counts, rounding to
97% for both runs. That figure alone obscures the useful differences.
No percentage gate or additional exclusions were added to reach these numbers.

The missing paths directed attention to safety continuations and weak assertion
patterns. New tests check observable outcomes, not merely executed lines:

- cancellation before deferred ReadOnly initialisation cleanup, followed by a
  second asynchronous pin assertion proving that monitoring remains armed;
- obsolete pin-cycle tasks resuming after ownership changes, including replay
  against distinctive live replacement outputs;
- exact capacity conservation when raw receives discard one packet prefix, or
  all prefixes for an unresolved identity, followed by overflow at the precise
  next acceptance;
- independent record and mutable LogicArray sideband snapshots;
- exact exception class/cause and atomic multi-field validation;
- exactly one accepted prefix beat before a frame identity failure, with no
  second beat and explicit recovery required.

The stale-cycle replay deliberately bypasses task cancellation to exercise
ownership guards; it is fault injection, not a claim that normal cancellation
routinely leaves tasks running.

## Follow-up: independent stress and mutation checks

The follow-up on `d80c332` keeps the public API and production implementation
unchanged. `tests/reliability_cases.py` uses directly driven peers and an
index-based reference ledger instead of coaxi's opposite endpoint or packet
dictionary. It compares all payload/sideband fields, detects extra or missing
acceptance, checks stable stalled outputs and reconciles mixed raw/frame delivery
and discarded prefixes. Randomised traffic includes meta-values, zero payloads,
null qualifiers, interleaved identities and caller idle periods.

Repeated no-ready sink lifecycles check reset, cancellation of unfinished packets,
adapter-read failures, overflow, stopped-clock close and reinitialisation.
Retained counts are checked before recovery can conceal errors. Fault identity
must survive pin cycling. Saved background tasks must finish, state must be empty
after disposal and closed capture must stop reading the adapter. These checks
measure endpoint task/state lifetime, not general interpreter memory growth.

The ordinary regression uses three recorded seeds with both reset polarities.
The extended run uses seeds 0..7 and 120 lifecycle epochs each in both write modes
(1,920 sink lifecycle epochs), plus independent source and sink traffic per seed.
The suite has simulation-time bounds and a host-process bound.

Four temporary-copy mutations were detected in both NVC write modes:

| Deliberate fault | Required detecting oracle |
| --- | --- |
| Drop the user sideband | Source wire comparison |
| Delay cleanup so a beat can be accepted twice | Source wire comparison |
| Retire one retained beat instead of the completed packet | Sink retention conservation |
| Leave an invalidated collector running | Saved-task completion after close |

Each mode first requires a passing unmodified control and the complete four-case
mutation inventory. Mutants must fail the designated test through its specific
AssertionError, not a timeout or infrastructure fault. Package/test origins and
module hashes are verified in the simulator; working source hashes are unchanged.
The verdict checker has negative tests for unrelated failures, skipped/missing
tests, surviving mutants and optimised Python. The worker overrides inherited
failure limits and removes embedded optimisation settings. See README.md for
repeatable stress and mutation commands and `reliability-results.json` output.

No new production defect was established in this follow-up. These four mutants
are representative assertion checks, not exhaustive fault injection. Scheduler
boundary regressions from the earlier suites remain necessary alongside longer
seeded runs; the stress suite does not replace them.

## Remaining gaps and limits

The report intentionally leaves missing paths visible: unsupported/empty payload
fallbacks, abstract hooks and selected obsolete-task/fault/cleanup alternatives
are not all exercised. Some payload fallbacks are unreachable after ordinary
construction; no private state was corrupted merely to execute them. Several
scheduler guards remain partially covered even though complementary stale-task
tests pass. These are residual validation gaps, not proof of a defect or proof
of safety.

Coverage measures execution, not the strength of assertions, protocol compliance
or the absence of bugs. The high baseline did not prevent the findings above.
There is no bug-free guarantee or formal conformance claim. Validation remains
Python 3.13.5, cocotb 2.1.0 and NVC 1.21.1 on Linux, in both write modes.
Other simulators and dependency versions remain unverified. Caller preconditions
and custom Payload adapter correctness remain documented responsibilities.

The runnable record example is `examples/stream_loopback.py`; the README shows
the HDL type, exact signal binding and signed field conversion. Neither packing
nor a custom adapter is needed for the VHDL IQ record.

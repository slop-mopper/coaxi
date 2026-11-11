# ARCHITECTURE.md
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

## Project and package

The project, Python distribution and import package are named `coaxi`. The
package lives in `src/coaxi` and exposes its public API from `coaxi.__init__`.
Hatchling builds the distribution. There is no compatibility package under the
former `cocotbext.axi` namespace.

The initial AXI-Stream implementation supports individual transfers and complete
frames, all AXI4-Stream transfer sidebands, and interleaved packet assembly.
The agreed target is AXI4-Stream only, excluding AXI5-Stream wake-up/parity.
AXI4 memory-mapped, AXI4-Lite, permitted data/ready omissions, continuous queued
capture without ready, and automatic reset-pin monitoring are not implemented.
The current subset is not yet the full-standard target.

## Components

- `_binding.py` resolves each protocol role to an independent HDL handle.
  `AxiStreamBus` contains data/valid/ready and explicitly selected optional
  last/keep/strb/user/id/dest handles. It does
  not drive signals. Clock binding is independent of the bus naming defaults.
- `_payload.py` separates payload access from handshake logic. `HandlePayload`
  handles logic/vector leaves and named containers such as VHDL records using
  field mappings. `Payload[T]` lets applications supply their own representation.
  Reads retain HDL logic values; integer conversion is explicit. Endpoint
  constructor overloads require an adapter when using application value types;
  omitting the adapter selects `PayloadValue`.
- `_sideband.py` keeps metadata conversion separate from generic payload access.
  `AxiStreamSidebands` is an optional immutable source input; it is unnecessary
  for bare-bones traffic. Bound defaults are keep=ones, strb=effective keep,
  user/id/dest=zero. Reads return raw independent logic snapshots. Both source
  and sink reject literal keep=0/strb=1 lane pairs; meta-valued qualifiers remain
  raw and do not establish protocol validity. No byte packing is performed.
- `_stream.py` provides `AxiStreamSource`, `AxiStreamSink` and
  `AxiStreamTransfer[T]`. An endpoint permits one active operation (one transfer
  or one whole frame) and has no background queue. Drives occur at falling edges;
  transfer values are sampled
  at rising edges before clocked HDL updates. Completion schedules cleanup at
  the following falling edge. Immediately consecutive calls reuse that edge
  to sustain one accepted transfer per rising edge when data and ready permit.
  Reuse requires both the recorded completion time (in simulator steps) and
  `current_gpi_trigger()` to identify that clock's falling-edge callback.
  Other simulator phases, later times, reset and failures invalidate reuse.
  Cleanup writes can be superseded on the same edge; valid/ready need not pulse
  low between calls. Initial calls still wait for a fresh falling edge.

`send_frame(Sequence[T], *, sidebands=None)` requires non-empty input and bound
last, generating last only on the final transfer. Optional metadata is a matching
sequence of `AxiStreamSidebands`. Values remain caller-owned until completion;
validation occurs per transfer. Packet identity (id,dest) must remain constant;
individual sends can interleave streams. No metadata objects are needed for
ordinary sends or frames, even when sideband signals are bound.

`AxiStreamTransfer[T]` preserves positional data/last, adding optional raw logic
keep/strb/user/id/dest fields. None means physically absent, distinct from each
signal's effective protocol default.

`recv_frame(*, max_transfers=None)` requires last and returns the next completed
packet as a non-empty `list[AxiStreamTransfer[T]]`. Incomplete packets are retained
in a dictionary keyed by effective (id,dest), defaulting absent identifiers to zero.
Each packet retains its own transfer order; packets return in completion order.
Assembly requires literal binary identifiers; `recv()` preserves raw wire order
and meta-valued identifiers. A raw receive discards the retained prefix for its
identity (all prefixes if unresolved), preventing assembly across consumed beats
or packet boundaries. It does not replay prefixes or discard other known streams.
None collects without a length/memory bound. The optional positive limit applies
to each packet, including retained prefixes; it does not bound stream count.
Last exactly at the limit succeeds. Without last at that length, cleanup deasserts
ready and raises ValueError with no extra acceptance or draining. A later call
whose limit was already reached by a retained prefix fails before more acceptance.
Reset, cancellation and in-progress faults discard partial packet assembly.

Public single/frame operations acquire one ownership token, share private
token-aware per-transfer routines, and release only after final cleanup.
Per-transfer cleanup records the reusable edge without releasing ownership.
This preserves full rate within/across frames and mixed single/frame calls.
The outer failure handler invalidates only its own token, so an interrupted
old frame cannot invalidate newer work after reset. Preflight argument failures
do not acquire ownership or alter endpoint state. In-progress errors (including
sequence indexing or frame limits) and cancellation require reset. A receive
starts at the next accepted transfer, possibly partway through an existing
frame; local reset restores outputs but does not restore frame alignment.

The source owns data, valid, last and all selected sidebands; the sink owns ready
and its partial packet assembly. Explicit `reset()`
invalidates pending work and clears owned outputs at a falling edge. Failed or
cancelled operations require reset. Local recovery cannot undo a transfer
already accepted by the DUT and must be coordinated with DUT reset. Spawned
transfer coroutines must catch `TransferReset` internally when reset may
interrupt them; cocotb can fail a test on an unobserved task exception before a
later await observes it.

Every clock must contain only literal 0/1 values from before the first endpoint
reset onwards. Weak L/H and unresolved clock values are unsupported. This is a
caller precondition, without runtime clock monitoring. The endpoints use
cocotb's raw rising/falling-edge triggers, whose behaviour for non-0/1 clocks
can differ from VHDL `rising_edge`/`falling_edge`.

Payload meta-values are preserved. Sampled handshake controls and accepted last
must be exactly 0 or 1. Explicit numeric helpers reject unresolved values even
when cocotb's environment would otherwise resolve them. Routine transfer and
reset messages use the `coaxi.stream` logger at DEBUG level.

## Signal binding

Protocol roles are independent of HDL signal names. Standard names such as
`foo_tdata`, `foo_tvalid`, `foo_tready` and `foo_tlast` have convenient defaults,
with a `t_prefix=False` option for names without `t`. These conveniences do not
limit explicit bindings.

Each signal accepts an exact child name or an already-bound cocotb handle.
Per-signal arguments allow one override while retaining all other defaults;
supplied names receive no prefix, suffix or case changes. Names need not share
a pattern or be valid Python attribute names. Optional last is explicitly
selected, as are keep/strb/user/id/dest; no optional signal is discovered merely
because a naming default exists. Bare-bones binding is unchanged.
This subset still requires data and ready. Byte qualifiers require a byte-aligned
LogicArrayObject payload and exactly one bit per byte; no scalar/record layout is
inferred. Qualifier significance is positional (rightmost bit is the least
significant byte), independent of HDL indices. User/id/dest accept any positive
logic width and do not depend on payload shape.
Signals for different roles and the clock must not overlap. Identical aliases
are checked, but payload-field or bit overlap remains the caller's responsibility.

Lookup first uses cocotb's named child access. If that fails, it enumerates
children and matches their exact reported names. This accommodates VHPI lookup
limitations with extended identifiers containing punctuation, without rewriting
a caller's name.

## Tests and development

- `tests/test_values.py` covers explicit numeric conversion.
- `tests/test_distribution.py` builds the sdist and a wheel from that sdist using
  `uv build`, checks metadata, the CC0 licence and package contents, then installs
  the wheel without dependencies into a temporary target directory. A fresh
  interpreter imports all public exports and exercises conversions/frame
  signatures from that installation. The check uses the current `.venv`
  dependencies; it does not claim validation in a minimal consumer environment.
- `tests/test_typing.py` checks default/custom constructor inference and
  rejection of specialised endpoints without adapters, and generic frame method
  input/result types using default Pyrefly.
- `tests/stream_cases.py` contains cocotb cases for binding, vector/record
  payloads, framing, timing, backpressure, reset and cancellation. Recovery
  cases include interruption between acceptance and cleanup, cancellation of
  reset, and injected adapter drive/read/clear failures. DUT counters verify
  that interruption does not undo a previously accepted transfer.
- `tests/full_rate_cases.py` measures acceptance cycle spacing through the
  registered DUT and on direct vector/record buses, including custom adapters.
  Independent peers check backpressure stability and continuous ready across
  source gaps; other cases check simulator-phase/time guards and chained
  failures. Interrupted full-rate receives cover adapter failure, cancellation
  and local reset after acceptance, preserving the DUT's buffered next value.
- `tests/frame_cases.py` covers frame-wide ownership, singleton/multiple frames,
  full-rate intra/inter-frame and mixed API boundaries, independent peers with
  source gaps/final-beat stalls, record/meta-value/custom payload snapshots,
  optional-limit boundaries, preflight validation and incomplete-frame recovery.
  Interruptions cover intermediate/final acceptance before cleanup, stale tasks
  after reset, adapter/control failures and sequence access failures.
- `tests/sideband_cases.py` checks default/mixed/direct bindings, qualifier width
  and record restrictions, unchanged bare-bones usage, defaults with omitted
  signals, scalar qualifier handles and wide identifiers. The registered DUT
  carries all sidebands; 128-beat tests check snapshots before HDL updates and
  consecutive acceptance cycles. Independent peers check backpressure, reserved
  qualifier faults, metadata preflight validation and reset ownership. Packet
  cases cover id/dest demultiplexing, completion order, per-packet metadata,
  null final beats, retained-prefix limits, cancellation and raw wire order.
- `tests/handle_cases.py` exercises scalar payloads with one-bit vector controls
  and a one-bit vector clock, using both ascending and descending non-zero
  indices. It checks full-rate frames, independent scalar snapshots, deliberate
  payload meta-values, scalar validation, backpressure, control faults and reset
  ownership.
- `tests/hdl/stream_dut.vhd` is the VHDL-2008 DUT, including a registered stream
  path, a two-field signed IQ record and undriven scalar/vector-control signals.
- `examples/stream_loopback.py` is a bounded cocotb usage example for unframed
  vectors and signed IQ-record frame helpers on the fixture's undriven buses.
- `tests/test_simulation.py` runs the cocotb regression and usage example with
  `nvc` in both inertial write modes. `uv run pytest -q` runs the Python and
  simulator tests.

`pyproject.toml` declares metadata, build configuration, runtime dependencies,
development tools and Ruff settings. The distribution's long description uses
`README.md`. `LICENSE.txt` contains the unmodified CC0 legal code and is explicitly
included in distribution metadata and both archives. `uv.lock` records resolved
dependencies.
Use `uv sync --locked` to create the project-local `.venv`; `.python-version`
selects Python 3.13. cocotb 2.1.0 or later is a runtime dependency.

Pytest, Pyrefly and Ruff are development dependencies. Pyrefly uses its defaults.
Ruff uses a 120-character line length, tab indentation, double quotes and
docstring code formatting. The lint configuration ignores `I001` and `BLE001`;
no additional lint rules are selected.

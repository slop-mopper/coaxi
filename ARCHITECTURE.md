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
Data/ready omissions and continuous queued capture without ready are supported.
Optional reset-pin monitoring supports active-low and active-high interfaces.
AXI4 memory-mapped and AXI4-Lite are not implemented.

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
  omitting the adapter selects `PayloadValue | None`. A private absent-data
  adapter accepts/returns only None, with no handle access. An explicit adapter
  requires data; with data present its T remains precise, and the default
  HandlePayload rejects None.
- `_sideband.py` keeps metadata conversion separate from generic payload access.
  `AxiStreamSidebands` is an optional immutable source input; it is unnecessary
  for bare-bones traffic. Bound defaults are keep=ones, strb=effective keep,
  user/id/dest=zero. Reads return raw independent logic snapshots. Both source
  and sink reject literal keep=0/strb=1 lane pairs; meta-valued qualifiers remain
  raw and do not establish protocol validity. No byte packing is performed.
- `_stream.py` provides `AxiStreamSource`, `AxiStreamSink` and
  `AxiStreamTransfer[T]`. An endpoint permits one active operation (one transfer
  or one whole frame). Ready-backed reception is call-driven without a queue;
  no-ready reception uses a continuously running collector. Drives occur at falling edges;
  transfer values are sampled
  at rising edges before clocked HDL updates. Completion schedules cleanup at
  the following falling edge. Immediately consecutive calls reuse that edge
  to sustain one accepted transfer per rising edge when data and ready permit.
  Reuse requires both the recorded completion time (in simulator steps) and
  `current_gpi_trigger()` to identify that clock's falling-edge callback.
  Other simulator phases, later times, initialisation, pin assertion and failures invalidate reuse.
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
Last exactly at the limit succeeds. Without last at that length, a ready-backed
sink deasserts ready at cleanup and raises ValueError with no extra acceptance
or draining. A no-ready sink stops capture, discarding undelivered traffic.
A retained prefix already at the limit fails before consuming further snapshots.
Initialisation, pin assertion, cancellation and in-progress faults discard partial packet assembly.
Without ready, a length error stops capture but cannot prevent physical acceptance.

Public single/frame operations acquire one ownership token, share private
token-aware per-transfer routines, and release only after final cleanup.
Per-transfer cleanup records the reusable edge without releasing ownership.
This preserves full rate within/across frames and mixed single/frame calls.
The outer failure handler invalidates only its own token, so an interrupted
old frame cannot invalidate newer work after initialisation or pin reset. Preflight argument failures
do not acquire ownership or alter endpoint state. In-progress errors (including
sequence indexing or frame limits) and cancellation require initialise(). A receive
starts at the next accepted transfer, possibly partway through an existing
frame; local initialisation restores outputs but does not restore frame alignment.

### No-ready capture

After successful initialisation, a no-ready sink starts a generation-owned cocotb
task. Every valid rising edge snapshots data/last/sidebands immediately, before
HDL updates. The accepted snapshot counts towards retention immediately and is
published to a deque at the following falling edge. A waiting receive wakes then;
a receive with existing backlog dequeues without advancing simulation time.
No historical cleanup edge is recorded/reused for backlog reads.
The collector persists independently of successful foreground receives.

Optional positive `buffer_capacity` counts all undelivered retained snapshots:
queued, awaiting cleanup/publication, in a foreground receive and in unfinished
packets. Only delivery or explicit prefix disposal frees capacity. Moving a
snapshot between those locations does not change the count. None is unlimited;
a finite capacity is rejected for ready-backed sinks.

OverflowError or an ordinary capture exception is observed and latched inside the
collector, stopping it and waking receivers. Receives check the fault before
dequeue/delivery, so older backlog cannot hide an error. The fault remains until
initialise()/close(). No unobserved background exception is used for notification.
Foreground receive cancellation/failure also stops capture and requires initialise().
Initialisation clears retained state and faults before yielding; successful cleanup starts
a new collector. Invalidating a generation and detaching its task reference
precede cancellation. If the collector itself observes reset before the pin
watcher, it is not cancelled from within its own task; it returns through its
generation guard after invalidation has discarded state and notified receivers.
All post-edge publication/finalisation is generation-guarded. Old foreground tasks
are also token-guarded before retiring counts or changing assembly.
Wake-up events are replaced after notification to avoid stale-set busy loops.

`await sink.close()` stops capture, invalidates pending operations and discards
queued/partial state, with no clock edge needed on no-ready sinks. A ready-backed
sink also clears ready at a falling edge. Close is repeatable; initialise/close may
not overlap, and initialise() is required to restart. Captures before initialisation or
while stopped are unavailable. Stopping capture cannot backpressure physical
traffic. Pending no-ready receives are woken with TransferReset on close/initialisation;
spawned receivers must observe that exception internally.

### Local lifecycle and reset monitoring

The source owns data, valid, last and all selected sidebands; the sink owns ready
and its partial packet assembly. `initialise()` replaces the former `reset()`
method. It invalidates pending work and performs local recovery without driving
the DUT reset pin. Without a pin it clears owned outputs at a falling edge.
Errors/cancellation require successful explicit initialisation. Local recovery
cannot undo accepted traffic, empty DUT buffers or restore packet alignment.

Both endpoints accept keyword-only `reset: Signal | None = None` and
`reset_active_high: bool = False`. Binding is independent of bus naming defaults,
accepting exact names and one-bit handles (including non-zero vector indices).
Polarity is not inferred. Literal pin 0/1 values are required. Construction
is non-driving; monitoring begins with initialise() and ends with close().

The base endpoint owns a reset watcher and a generation-guarded pin-cycle task.
Every observed pin change invalidates release eligibility and pending work,
stops capture and discards retained snapshots/packets before deferred cleanup.
Owned outputs clear without a clock edge; ReadOnly defers clearing by a
scheduled one-simulator-step Timer. Every delayed continuation rechecks monitor
and cycle ownership before writing. Source valid/last clear first, and sideband
cleanup is attempted even if the custom payload adapter fails.

For an inactive pin, the cycle task waits for rising R0, rising R1 and falling F1.
Eligibility begins at F1, so the earliest acceptance is R2. Reassertion replaces
this cycle. Deassertion must be synchronous after a rising edge; this conservative
release gate follows Arm IHI 0051B §2.8.2 with configurable polarity and does not
implement a synchroniser. A healthy pin-only interruption recovers automatically,
including no-ready capture. New calls while unavailable reject rather than queue.

Per-operation tokens carry an interruption event and error. Pin-aware waits
race the clock edge against that event, then check ownership and synchronously
inspect the pin before driving or sampling. This wakes stalled operations even
with a stopped clock. No-pin edge waits retain their direct trigger path.
Pin-aware registered-DUT regressions verify pre-update samples and full rate.

Manual-recovery state is separate from pin eligibility: earlier cancellation,
foreground errors, overflow and capture faults cannot be acknowledged by a pin
cycle. Invalid reset values latch ProtocolValueError; asynchronous cleanup
failures latch their exception. The first fault is retained until explicit
initialise()/close(), and exceptions are delivered through foreground operations
rather than unobserved monitor tasks. Cancelled initialisation leaves monitoring
armed for safety but manual recovery required. Initialisation waits through
assertion/release and can block indefinitely without a running clock or release.

Both source and sink expose close(). It invalidates work, stops monitoring/capture
and clears retained faults/state. Source/ready-backed sink outputs clear at a
falling edge; no-ready sinks need no clock. A failed/cancelled close remains
closed. Pin activity cannot reopen it; explicit initialise() rearms monitoring.
Initialise and close are mutually exclusive. Spawned operation coroutines must
catch TransferReset internally when initialisation, pin assertion or close may
interrupt them; cocotb may fail on an unobserved exception before a later await observes it.

Every clock must contain only literal 0/1 values from before the first endpoint
initialisation onwards. Weak L/H and unresolved clock values are unsupported. This is a
caller precondition, without runtime clock monitoring. The endpoints use
cocotb's raw rising/falling-edge triggers, whose behaviour for non-0/1 clocks
can differ from VHDL `rising_edge`/`falling_edge`.

Payload meta-values are preserved. Sampled handshake controls and accepted last
must be exactly 0 or 1. Explicit numeric helpers reject unresolved values even
when cocotb's environment would otherwise resolve them. Routine transfer and
initialisation and reset messages use the `coaxi.stream` logger at DEBUG level.

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
Generated data/ready defaults remain unchanged; bind(data=False, ready=False)
explicitly omits either signal. None still means generated names in bind; direct
construction uses None for an absent handle. Every valid edge accepts without
ready. Absent data transfers explicitly use None, including in frame sequences.
Without data, keep defines lanes from its own width and strb is forbidden.
With data present, byte qualifiers require a byte-aligned LogicArrayObject
payload and exactly one bit per byte; no scalar/record layout is
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
  `uv build`, checks metadata, the CC0 licence and package contents, then creates
  a temporary uv virtual environment without development packages. Wheel
  installation resolves only declared runtime dependencies, constrained to the
  versions in `uv.lock`, downloading uncached packages. An isolated interpreter checks
  all public exports, conversions and frame signatures from that installation.
  The source archive's vector/IQ-record example and HDL fixture run under NVC
  in both write modes in the consumer environment. Import-origin assertions in
  Python and the simulator reject accidental use of the editable checkout.
  This validates the locked runtime graph, not every permitted dependency version.
  Both this check and the main simulator runner explicitly set write-mode and
  meta-value resolution environment variables, overriding inherited settings.
  Result XML must contain successful, non-skipped test cases; a successful
  simulator process alone is insufficient.
- `tests/test_typing.py` checks default/custom constructor inference and
  rejection of specialised endpoints without adapters, and generic frame method
  input/result types using default Pyrefly.
- `tests/stream_cases.py` contains cocotb cases for binding, vector/record
  payloads, framing, timing, backpressure, local initialisation and cancellation. Recovery
  cases include interruption between acceptance and cleanup, cancellation of
  initialisation, and injected adapter drive/read/clear failures. DUT counters verify
  that interruption does not undo a previously accepted transfer.
- `tests/full_rate_cases.py` measures acceptance cycle spacing through the
  registered DUT and on direct vector/record buses, including custom adapters.
  Independent peers check backpressure stability and continuous ready across
  source gaps; other cases check simulator-phase/time guards and chained
  failures. Interrupted full-rate receives cover adapter failure, cancellation
  and local initialisation after acceptance, preserving the DUT's buffered next value.
- `tests/frame_cases.py` covers frame-wide ownership, singleton/multiple frames,
  full-rate intra/inter-frame and mixed API boundaries, independent peers with
  source gaps/final-beat stalls, record/meta-value/custom payload snapshots,
  optional-limit boundaries, preflight validation and incomplete-frame recovery.
  Interruptions cover intermediate/final acceptance before cleanup, stale tasks
  after initialisation, adapter/control failures and sequence access failures.
- `tests/sideband_cases.py` checks default/mixed/direct bindings, qualifier width
  and record restrictions, unchanged bare-bones usage, defaults with omitted
  signals, scalar qualifier handles and wide identifiers. The registered DUT
  carries all sidebands; 128-beat tests check snapshots before HDL updates and
  consecutive acceptance cycles. Independent peers check backpressure, reserved
  qualifier faults, metadata preflight validation and initialisation ownership. Packet
  cases cover id/dest demultiplexing, completion order, per-packet metadata,
  null final beats, retained-prefix limits, cancellation and raw wire order.
- `tests/omission_cases.py` covers all four data/ready combinations, data-less
  keep lanes, unchanged naming defaults and rejected adapters/strb without data.
  Independent peers and the registered DUT check idle capture, one accepted
  beat per rising edge, pre-update snapshots, live cleanup timing and immediate
  backlog dequeue. Capacity tests include partial packets and in-flight values;
  faults are delivered error-first while idle/waiting. Recovery cases cover
  initialise/cancel/close, stale receivers/collectors and close with a stopped clock.
  Records/meta-values, packet limits and mixed raw/frame retirement are covered.
- `tests/handle_cases.py` exercises scalar payloads with one-bit vector controls
  and a one-bit vector clock, using both ascending and descending non-zero
  indices. It checks full-rate frames, independent scalar snapshots, deliberate
  payload meta-values, scalar validation, backpressure, control faults and
  initialisation ownership.
- `tests/reset_pin_cases.py` covers both polarities, exact names and one-bit vector
  reset handles, asynchronous clearing/stopped-clock interruption, R0/R1/F1/R2
  release timing and reassertion during release. It checks 128-beat registered
  full-rate packet traffic, error-first overflow preservation across invalid
  pin values, deferred ReadOnly cleanup, cancelled initialisation, shutdown/rearm,
  accepted-before-interruption traffic and stale foreground tasks. It also verifies
  that cancellation and first faults survive pin cycling and adapter-clear errors.
  Deterministic collector-first reset cases delay the watcher, then assert before
  a rising-edge sample or before falling-edge publication, for both polarities.
  Held-reset/stopped-clock checks require prompt interruption, complete retention
  disposal and automatic capture recovery without replaying pre-reset traffic.
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

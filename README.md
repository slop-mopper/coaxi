# README.md
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

# coaxi

AXI interface helpers for cocotb testbenches, written for Python 3.13.
This is a ground-up rewrite of `cocotbext-axi`, with AXI-Stream as the first
implementation goal. The initial AXI-Stream API supports individual transfers
and complete frames; AXI4 and AXI4-Lite are not implemented yet.

The distribution and Python import name are both `coaxi`:

```python
from coaxi import AxiStreamBus, AxiStreamSource, AxiStreamSink
```

## Installation

Use Python 3.13 or later and cocotb 2.1.0 or later. cocotb is installed as a
runtime dependency. These commands use a local checkout and do not assume a
package-index release:

```text
# In this library's checkout:
uv sync --locked
uv build

# In a separate Python 3.13+ testbench project managed by uv:
uv add /absolute/path/to/coaxi/dist/coaxi-0.1.0-py3-none-any.whl
```

Run testbench tools through that project's `uv run`. To use the source checkout
instead, run `uv add /absolute/path/to/coaxi` in the testbench project.
The Python package is pure Python, but running a testbench also requires a
simulator and cocotb's simulator integration. The regression has been run with
Python 3.13.5, cocotb 2.1.0 and `nvc` 1.21.1 on Linux; other simulator timing
models are not covered by these results.

The examples, test fixture and architecture links below refer to files in the
source checkout or unpacked source distribution.

## Signal names

Defaults are optional conveniences. Every signal can be overridden independently
with an exact HDL name or an already-bound cocotb handle:

```python
# Standard defaults: samples_tdata, samples_tvalid, samples_tready.
bus = AxiStreamBus.bind(dut, prefix="samples")

# Keep the defaults except for ready.
bus = AxiStreamBus.bind(dut, prefix="samples", ready="consumer_accepts")

# Unrelated names, including an explicitly selected frame boundary.
bus = AxiStreamBus.bind(
	dut,
	data="iq_word_in",
	valid="sample_available",
	ready="consumer_accepts",
	last="end_of_packet",
)
source = AxiStreamSource(bus, clock="beat_clock")
```

Explicit names are used unchanged. Use `t_prefix=False` for generated names
such as `samples_valid`. Last and the other sidebands are absent unless
explicitly selected with `True`, a name or a handle. Data and ready use their
generated names by default; select `data=False` or `ready=False` to omit either.
`None` retains the generated name. Direct bus construction uses `None` for an
absent handle. No sidebands need to be selected for bare-bones usage.

## Sending and receiving

Start the clock before awaiting either endpoint's initial `reset()`. Every clock
must contain only literal 0/1 values from before the first endpoint reset onwards;
weak L/H and X/U/Z/etc. clock values are unsupported. This is a caller precondition:
endpoints do not monitor clocks for invalid values. Cocotb's raw edge triggers
can differ from VHDL `rising_edge`/`falling_edge` for non-0/1 values.

The following bounded cocotb test uses an otherwise undriven, unframed stream in
the example DUT:

```python
import cocotb
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject

from coaxi import AxiStreamBus, AxiStreamSink, AxiStreamSource, to_unsigned


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def loopback(dut: HierarchyObject) -> None:
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	bus = AxiStreamBus.bind(dut, prefix="plain", t_prefix=False)
	source = AxiStreamSource(bus, clock="beat_clock")
	sink = AxiStreamSink(bus, clock="beat_clock")
	await source.reset()
	await sink.reset()

	sending = cocotb.start_soon(source.send(42))
	transfer = await sink.recv()
	await sending
	assert isinstance(transfer.data, LogicArray)
	assert to_unsigned(transfer.data) == 42
	assert transfer.last is None
```

Only start a cocotb clock when the testbench owns it. In a DUT testbench, bind
the source to a DUT input stream and the sink to a DUT output stream instead of
the same bus, and coordinate initialisation with the DUT's reset.

[The runnable example](examples/stream_loopback.py) includes this loopback and
framed IQ-record transfers. It runs against
[the VHDL-2008 fixture](tests/hdl/stream_dut.vhd) in both write modes when running
`uv run pytest -q tests/test_simulation.py -k example`.

`send(data, last=...)` holds data and last stable until ready is sampled high.
`recv()` asserts ready while waiting for valid and returns an
`AxiStreamTransfer` with `data` and `last`. Values are sampled at rising edges,
before clocked HDL updates. Both calls schedule handshake cleanup and return at
the following falling edge, rather than at the accepting rising edge. The source
owns data, valid, last and all bound sidebands; the sink owns ready.

Each endpoint allows one active operation. With ready present, there are no
background queues or capture tasks; the sink accepts only during a receive.
Start send/receive concurrently when the peer needs both operations to progress;
awaiting send before starting a same-bus receive would stall. Each operation needs
a running clock for live traffic and a cooperating peer; buffered no-ready
receives can return immediately. Use a bounded cocotb test or a simulation-time
timeout to detect stalled traffic.

### Data-less streams and reception without ready

Without data, send an explicit `None`, or a non-empty sequence of `None` values
for a frame. The received `data` is `None`. Sidebands remain independent:

```python
bus = AxiStreamBus.bind(dut, prefix="events", data=False, ready=False, last=True)
source = AxiStreamSource(bus, clock="beat_clock")
sink = AxiStreamSink(bus, clock="beat_clock")
await source.reset()
await sink.reset()
try:
	await source.send_frame([None, None])  # No receiver call is needed to accept.
	frame = await sink.recv_frame()
	assert all(transfer.data is None for transfer in frame)
finally:
	await sink.close()
```

Without ready, every valid rising edge accepts a transfer. Successful initial
`sink.reset()` starts a background collector; it continues while Python is idle.
It snapshots the payload and sidebands before clocked HDL updates and makes the
snapshot available at the following falling edge. A waiting receive therefore
retains the existing falling-edge completion timing. Already-buffered transfers
return immediately, so several dequeues or complete buffered packets can return
in one simulation step. Raw receives keep wire order; packets keep `(id, dest)`
assembly and completion order. The source never waits for a receiver call.

Use `await sink.close()` when capture is no longer needed. It stops capture,
invalidates pending receives with `TransferReset` and discards all retained
traffic. Closing a no-ready sink needs no clock edge; closing a ready-backed
sink clears ready at a falling edge. Repeated closes are safe. A subsequent
`reset()` restarts the sink. Reset/close must not overlap. Catch `TransferReset`
inside any spawned receive that shutdown can interrupt. Traffic accepted before
initial reset or while capture is stopped cannot be recovered.

No-ready buffering is unlimited by default. An optional positive
`buffer_capacity` on `AxiStreamSink(...)` counts **all retained, undelivered
transfers**, including incomplete packets and snapshots awaiting delivery.
Moving a transfer into packet assembly does not free capacity; returning or
explicitly discarding it does. A finite capacity is rejected on a bus with ready.
Overflow raises `OverflowError`; it cannot prevent physical acceptance.

Overflow or a payload/control/qualifier capture error stops the collector.
The current or next receive raises the original exception **before returning
older buffered data**, without an unobserved background task exception.
Further receives keep reporting that fault until local recovery. Reset discards
the queue, partial packets and fault, and restarts capture. Close also discards
them but leaves capture stopped. Cancellation, frame-limit failure and other
in-progress receive failures stop capture and require reset. Argument errors or
a rejected competing receive do not disturb existing capture.

### Full-rate transfers

Immediately consecutive calls can sustain **one accepted transfer per rising
clock edge** whenever data and ready are available:

```python
# Run these in separate coroutines so both endpoints can progress.
async def send_samples() -> None:
	for sample in samples:
		await source.send(sample)  # Supply last explicitly on a framed bus.


async def receive_samples() -> None:
	for _ in samples:
		transfer = await sink.recv()
		# Process this independent snapshot without a simulator-phase/time wait.
```

The next call reuses the preceding call's falling-edge cleanup point to drive
the next payload or reassert ready. Valid and ready may remain continuously high;
there is no promised low pulse or settled-low state between calls. Data and last
remain stable throughout backpressure. Frame boundaries do not require idle
cycles. The final call still schedules deassertion at its cleanup edge.

To sustain full rate, use separate sending/receiving coroutines and start each
next call immediately, without advancing simulation time or awaiting a different
simulator phase. `ReadOnly()`, `ReadWrite()` or a delay between calls can introduce
idle cycles: the next call then waits for a fresh falling edge before driving.
Initial reset and the first transfer also wait for their own falling edges.
Normal Python processing without a simulator wait does not consume a clock cycle.

## Framing and payloads

Unframed transfers omit last and return `transfer.last is None`. When last is
bound, every individual `send()` must explicitly supply `last=False` or
`last=True`. Individual `recv()` calls retain last without assembling a frame:

```python
await source.send(first_sample, last=False)
await source.send(final_sample, last=True)
```

Here the peer must already be receiving. These are individual transfers on a
framed bus.

### Frame helpers

With last bound on both endpoints, send a non-empty sequence of payloads and
receive a list of `AxiStreamTransfer[T]` snapshots:

```python
# Run concurrently on an otherwise undriven framed bus.
sending = cocotb.start_soon(source.send_frame([first_sample, final_sample]))
frame = await sink.recv_frame()
await sending
assert [transfer.last for transfer in frame] == [False, True]
```

`send_frame(data, *, sidebands=None)` takes a finite `Sequence[T]`, such as a list or tuple, and
generates `last=False` on all but the final transfer. Input elements are payloads,
not transfer objects. Generators and empty sequences are rejected. The sequence
and its payloads remain caller-owned: do not mutate them until the call finishes.
Payloads are validated as they are driven; a later invalid payload can fail after
an earlier prefix has been accepted. Arbitrary custom values are not deep-copied.

`recv_frame(*, max_transfers=None)` assembles packets separately by `(id, dest)`,
returning the next completed packet and retaining other streams' unfinished
packets for later calls. Packet completion order can differ from start order.
Absent id/dest have effective value zero, so the usual single-stream behaviour
is unchanged. All payloads and sidebands are independent snapshots.
The default has **no length or memory bound**. An optional positive integer
`max_transfers` limits each packet's length, not elapsed cycles or total traffic
across interleaved streams:

```python
frame = await sink.recv_frame(max_transfers=1024)
```

Last on the packet's limit-th transfer succeeds. If that transfer has no last,
the helper raises `ValueError` without returning a partial frame, draining or
retrying. On a ready-backed bus it first clears ready at the falling-edge
cleanup, accepting no extra transfer. Without ready, it stops capture; later
transfers might already be buffered, and physical acceptance cannot be prevented.
Reset is then required. Both an unlimited receive and a length-limited receive
need a simulation-time timeout for stalled traffic; a missing last with the
default limit can also grow memory without bound. The limit applies to retained
prefixes too: selecting a limit already reached by a retained unfinished packet
raises before consuming further transfers. There is no bound on the number of
unfinished streams unless a no-ready `buffer_capacity` is set. Reset,
cancellation and in-progress failures discard partial assembly.

Both helpers require last. Absent last, empty/non-sequence send input and invalid
limits are rejected before wire activity and do not themselves require reset.
A frame operation reserves its endpoint through every transfer and final cleanup;
overlapping single-transfer or frame calls raise `EndpointStateError`. Frame
helpers share the individual-transfer timing and sustain full rate within frames
and between immediately consecutive calls, including mixed single/frame calls.

Collection begins at the next accepted transfer. Last marks the end, not the
start, so a frame receive after individual receives returns the remaining suffix.
In-progress failures, cancellation or reset can leave an accepted prefix or even
an entire frame on the peer. There is no rollback or automatic retry. Local reset
restores owned outputs but **does not restore frame alignment**; coordinated
recovery with the peer or DUT may be necessary.

### Optional AXI4-Stream sidebands

The basic API stays unchanged:

```python
bus = AxiStreamBus.bind(dut, prefix="samples")
source = AxiStreamSource(bus, clock="clock")
# After reset, with a cooperating peer:
await source.send(42)
```

Opt in only to the signals on your interface. Each role has the same exact-name,
direct-handle and mixed-default binding support as data/valid/ready:

```python
from coaxi import AxiStreamSidebands

bus = AxiStreamBus.bind(dut, prefix="samples", last=True, keep=True, user="flags")
source = AxiStreamSource(bus, clock="clock")
# After reset, with a cooperating peer:
await source.send(0x1234, last=True, sidebands=AxiStreamSidebands(keep=1, user=5))
```

`sidebands` is optional even when signals are bound. For every transfer the source
defaults keep to all ones, strb to effective keep, and user/id/dest to zero. Values
from the previous transfer do not become defaults. Supplying metadata for an
unbound signal raises before an individual send changes the wires.
Unsigned integers must fit the selected width; strings and cocotb logic values
must match it. Deliberate X/U/etc. are retained for propagation/fault-injection
tests, with no implicit conversion or claim that the traffic is protocol-valid.

`AxiStreamTransfer` adds `keep`, `strb`, `user`, `id` and `dest` snapshots. Each is
a cocotb `Logic`/`LogicArray` when physically bound, or **None when absent**.
This distinguishes absence from an explicit zero. For protocol interpretation,
absent keep means all bytes present, absent strb follows effective keep, and
absent id/dest/user have value zero. Absent last remains None; this library does
not silently impose a packet-boundary policy on an interface without last.
`recv()` always returns individual transfers in wire order, including raw
meta-valued identifiers. Packet assembly requires literal 0/1 id/dest values;
it raises `ProtocolValueError` rather than guessing a stream for X/U/weak values.
When mixing APIs, a raw receive discards any retained prefix for its stream;
a raw unresolved identity discards all retained prefixes. This prevents later
assembly from splicing across a raw-consumed beat or packet boundary. Other
streams' retained prefixes are unaffected when the identity is known.

With data present, keep and strb require a **byte-aligned logic-vector payload**,
with exactly one qualifier bit per byte. Without data, keep defines its own lane
count from its handle width; strb is forbidden. Scalar and record/custom HDL
payloads have no inferred byte layout and reject these qualifiers. A custom Python adapter over a vector
can still use its physical byte lanes. The rightmost qualifier bit describes
the least-significant data byte, regardless of the HDL index bounds/direction.
User/id/dest do not require a byte layout and work with record payloads too.

The keep/strb pairs per lane distinguish data (`1/1`), position (`1/0`) and null
(`0/0`) bytes. Literal `0/1` is reserved: the source rejects it before driving
and the sink raises `ProtocolValueError` after sampling it at an accepting edge.
Unresolved qualifiers are preserved without claiming that the pair is valid.
No bytes or final null transfers are discarded, packed, padded or reordered.

For per-transfer frame metadata, supply a sequence matching the payload count:

```python
metadata = [
	AxiStreamSidebands(keep=3, user=1, id=7),
	AxiStreamSidebands(keep=1, user=2, id=7),
]
await source.send_frame([0x1234, 0x0056], sidebands=metadata)
```

Keep/strb/user may vary within a packet; id/dest must remain constant.
A later invalid entry can fail after a prefix has already been accepted, requiring
reset. Use individual `send()` calls to deliberately interleave different streams.
The existing `send_frame`/`recv_frame` names denote a packet ending in last; the
AXI4-Stream specification also uses “frame” for application groupings of packets.

### Payloads

Payload access is separate from handshake logic. The default `HandlePayload`
adapter accepts scalar logic, vectors and named containers such as VHDL records.
Reads retain cocotb `Logic`/`LogicArray` values and use field mappings for records.
For example, an IQ record with two signed 16-bit fields can be sent directly:

```python
from cocotb.types import LogicArray

await source.send(
	{"i": LogicArray.from_signed(-12, 16), "q": LogicArray.from_signed(34, 16)},
	last=True,
)
```

Integer inputs are unsigned and must fit the leaf width. Field mappings must
match all record fields exactly. Negative numbers need an explicitly signed
`LogicArray`, as above. Default payload validation checks the entire value before
writing any leaf. Unsupported handle types require a custom adapter.

`to_unsigned()` and `to_signed()` explicitly convert vector snapshots. They
reject unresolved X/U/Z/etc. even if cocotb is configured to resolve them;
weak L/H bits remain resolvable. Payload X/U/etc. are otherwise retained.
Driving meta-values is supported for deliberate propagation or fault-injection
tests; ordinary reset clears them to zero. Sampled valid, ready and accepted
last must be exactly 0 or 1, including rejection of weak L/H control values.

Default endpoint typing is `PayloadValue | None`; `PayloadValue` itself remains
the data-bearing scalar/vector/field-mapping input type. Default-adapter sends
on a data-bearing bus reject `None`. A data-less bus requires `None` and rejects
custom payload adapters. Supplying an adapter on a data-bearing bus retains its
precise `T`, without adding `None`.

Applications can supply a `Payload[T]` adapter using `payload=...` on an endpoint
to work with a custom value type. Its synchronous `drive`, `read` and `clear`
methods must not yield. `read` must return an independent snapshot, and `clear`
must define every owned leaf. A custom source adapter can partially write before
raising; recovery does not roll those writes back. The sink never calls the
payload's `clear`, since it does not own incoming data. Do not mutate a value
passed to `send` or `send_frame` until that call finishes.

## Reset, errors and cancellation

Always await `reset()` initially and after an in-progress operation fails or is
cancelled, including frame length errors. Preflight argument errors are exempt.
Source reset clears valid, last, every bound sideband and all owned payload
leaves; sink reset clears ready and all retained queued/partial packet state.
No-ready capture stops immediately on reset and restarts after successful cleanup.
Outputs clear at a falling edge, so reset also needs a running clock.
A failed or cancelled reset leaves the endpoint unusable until reset succeeds.
Reset is explicit local recovery; there is no automatic reset-pin monitoring.

Local reset invalidates pending operations with `TransferReset`. When reset
may interrupt a spawned operation, catch this exception **inside that coroutine**;
cocotb can fail a test on an unobserved task exception before a later await
observes it. Concurrent operations on one endpoint, overlapping reset calls, and
operations started while reset is active raise `EndpointStateError`. Reset may
interrupt an active transfer or frame. Invalid sampled controls raise `ProtocolValueError`,
and invalid bindings raise
`SignalBindingError`.

Neither cancellation nor local reset can undo a transfer already accepted at a
rising edge. Interruption can occur after acceptance but before cleanup returns,
so **do not blindly retry an interrupted transfer**: it could duplicate data.
Cancellation leaves driven outputs for explicit reset recovery. Coordinate
recovery with DUT reset during active traffic; local reset does not reset the
DUT or discard its buffered transfers.

## Current scope

The target is **AXI4-Stream**, excluding AXI5-Stream wake-up/parity extensions.
The implemented subset supports data/ready omissions, explicit optional
last/keep/strb/user/id/dest, continuous no-ready capture and interleaved packet
assembly. Frame helpers require last; unframed traffic uses individual transfers.
Automatic protocol reset-pin monitoring remains to be implemented.
This is not yet full-standard support.
The timing model targets event-driven simulators and is tested
with `nvc`; no support for other simulator timing models is claimed.

## Development

```text
uv sync --locked
uv run pytest -q
uv run pyrefly check
uv run ruff format --check .
uv run ruff check .
```

Simulation uses `nvc` and VHDL-2008. The handle regressions include scalar
payloads and one-bit vector controls/clocks as well as ordinary vector and
record payloads. Both cocotb inertial-write modes are tested.

`uv run pytest -q tests/test_distribution.py` builds a source distribution and a
wheel from it in a temporary directory. It checks metadata, licence inclusion,
the public exports and type marker, installs the wheel without dependencies into
a temporary directory, then imports/exercises that installed package in a fresh
interpreter. This smoke check uses dependencies from the current project-local
`.venv`; it does not validate a minimal consumer environment.
Build isolation may need to download the declared build backend when uncached.
It performs no publication or upload.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the components, timing model and
current limitations, and [AGENTS.md](AGENTS.md) for the development rules.

## Licence

coaxi uses CC0-1.0. [LICENSE.txt](LICENSE.txt) contains the unmodified
[CC0 1.0 Universal legal code](https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt),
included in both source and wheel distributions.

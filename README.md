# README.md
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

# coaxi

AXI interface helpers for cocotb testbenches, written for Python 3.13.
This is a ground-up rewrite of `cocotbext-axi`, with AXI-Stream as the first
implementation goal. The first single-transfer API is under development;
AXI4, AXI4-Lite and higher-level frame helpers are not implemented yet.

The distribution and Python import name are both `coaxi`:

```python
from coaxi import AxiStreamBus, AxiStreamSource, AxiStreamSink
```

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
such as `samples_valid`. Last is absent unless explicitly selected with
`last=True`, a name or a handle. This initial subset requires ready.

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
owns data, valid and last; the sink owns ready.

Each endpoint allows one active operation. There are no background queues.
Start send/receive concurrently when the peer needs both operations to progress;
awaiting send before starting a same-bus receive would stall. Each operation needs
a running clock and a cooperating peer; use a bounded cocotb test or a
simulation-time timeout to detect stalled traffic.

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
bound, **every** send must explicitly supply `last=False` or `last=True`. Last
is captured on each accepted transfer; there is no implicit frame assembly:

```python
await source.send(first_sample, last=False)
await source.send(final_sample, last=True)
```

Here the peer must already be receiving. These are individual transfers on a
framed bus, not a higher-level frame API.

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

Applications can supply a `Payload[T]` adapter using `payload=...` on an endpoint
to work with a custom value type. Its synchronous `drive`, `read` and `clear`
methods must not yield. `read` must return an independent snapshot, and `clear`
must define every owned leaf. A custom source adapter can partially write before
raising; recovery does not roll those writes back. The sink never calls the
payload's `clear`, since it does not own incoming data. Do not mutate a value
passed to `send` until that call finishes.

## Reset, errors and cancellation

Always await `reset()` initially and after a failed or cancelled transfer.
Source reset clears valid, last and all owned payload leaves; sink reset clears
ready. Outputs clear at a falling edge, so reset also needs a running clock.
A failed or cancelled reset leaves the endpoint unusable until reset succeeds.
Reset is explicit local recovery; there is no automatic reset-pin monitoring.

Local reset invalidates pending operations with `TransferReset`. When reset
may interrupt a spawned operation, catch this exception **inside that coroutine**;
cocotb can fail a test on an unobserved task exception before a later await
observes it. Concurrent transfers on one endpoint, overlapping reset calls, and
transfers started while reset is active raise `EndpointStateError`. Reset may
interrupt an active transfer. Invalid sampled controls raise `ProtocolValueError`,
and invalid bindings raise
`SignalBindingError`.

Neither cancellation nor local reset can undo a transfer already accepted at a
rising edge. Interruption can occur after acceptance but before cleanup returns,
so **do not blindly retry an interrupted transfer**: it could duplicate data.
Cancellation leaves driven outputs for explicit reset recovery. Coordinate
recovery with DUT reset during active traffic; local reset does not reset the
DUT or discard its buffered transfers.

## Current scope

The implemented subset requires ready and optionally supports last. Other
AXI-Stream sidebands, frame helpers and automatic reset monitoring are not yet
implemented. The timing model targets event-driven simulators and is tested
with `nvc`; no support for other simulator timing models is claimed.

## Development

```text
uv sync --locked
uv run pytest -q
uv run pyrefly check
uv run ruff format --check .
uv run ruff check .
```

Simulation uses `nvc` and VHDL-2008. See [ARCHITECTURE.md](ARCHITECTURE.md) for the
components, timing model and current limitations, and [AGENTS.md](AGENTS.md) for
the development rules.

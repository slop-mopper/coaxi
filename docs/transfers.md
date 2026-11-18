# Transfers, timing, and frames

## Handshake timing

A transfer is accepted at a rising clock edge when `valid` and `ready` are
asserted. Without `ready`, `valid` alone determines acceptance.
A source drives at a falling edge and holds `data`, `last`, and sidebands
stable until acceptance. A sink asserts `ready` at a falling edge.
Reception samples at the accepting rising edge before clocked HDL updates.

Live single-transfer operations return at the following falling edge.
A send schedules `valid` and bound `last` low; a receive schedules `ready` low.
Payload and other sidebands keep their values after a successful send.
Initialisation and `close()` clear them.

Immediately consecutive calls can share the cleanup edge and sustain one
accepted transfer per rising edge. For an unframed source with a receiving
peer already running:

```python
await source.send(10)
await source.send(20)
await source.send(30)
```

`valid` and `ready` can stay high between calls. Waiting for another
simulator phase or advancing time between calls can insert idle cycles.
The same full-rate behaviour applies within frames, between consecutive frames,
and when mixing single-transfer and frame calls. Backpressure delays acceptance
until the peer is ready.

Only one send or receive operation may be active on an endpoint. A frame
owns its endpoint until the whole operation completes. Separate source and
sink endpoints can run concurrently.

The caller must supply a clock containing literal `0` and `1`, including while
idle and before the first initialisation. Endpoints do not monitor clock values;
weak or unresolved clocks are unsupported.

## Simulated backpressure

Use {py:meth}`~coaxi.AxiStreamSource.set_pause_generator` to insert gaps in
transmission, or {py:meth}`~coaxi.AxiStreamSink.set_pause_generator` to hold
`ready` low during pending receives. A source pause delays new offers. A beat
waiting for `ready` keeps `valid`, `data`, and sidebands stable until acceptance.
A sink without `ready` cannot stall its peer.

```python
from collections.abc import Iterator


def source_pauses() -> Iterator[bool]:
	while True:
		yield False
		yield False
		yield True


source.set_pause_generator(source_pauses())
sink.set_pause_generator([False, True])
```

Each initialised endpoint takes one value in `ReadOnly` after every rising
edge for use at the following falling edge, including when idle. Install a
pattern before a rising edge to use its first value for the next drive.
A generator can inspect settled signals at that point; leave writes to the
endpoint.

A list or other sequence repeats from a copy. A generator or other non-sequence
iterable is read once, without caching; it unpauses the endpoint on the cycle
it runs out. If iteration raises or yields an invalid value, the current or
next transfer raises the error. Call `initialise()` to recover; the failed
pattern is discarded.

Call `set_pause_generator(None)` to stop a pattern and allow traffic at the
next drive. Reset suspends sampling, and the pattern resumes from the same
position after release. Reinitialisation also keeps that position. `close()`
discards the pattern. Use a simulation-time timeout for tests with intentional
stalls.

## Unframed and framed streams

Without `last`, use `send()` and `recv()`. With `last`, each individual send must
explicitly identify whether it ends a frame:

```python
await source.send(10, last=False)
await source.send(20, last=True)
```

Frame helpers require a bound `last` signal. Run sending and receiving concurrently
so both endpoints can progress through backpressure:

```python
import cocotb

sending = cocotb.start_soon(source.send_frame([10, 20]))
frame = await sink.recv_frame(max_transfers=2)
await sending
```

A source frame is a non-empty sequence of payloads.
Each received {py:class}`coaxi.AxiStreamTransfer` includes the sampled `last`
value. Frame reception starts with the next available transfer.
Starting midway through a packet can produce a suffix.

Use simulation-time timeouts for stalled traffic. By default, frame reception
allows any packet length. Memory usage grows with unfinished packets.
A packet ending at its configured limit succeeds; one reaching that length
with `last` low raises `ValueError` after cleanup and requires `initialise()`.
Recovery must account for the accepted prefix and the rest of the packet.

## Interleaved packets

Frame reception assembles a separate incomplete packet for each effective
`(id, dest)` pair. Missing identifiers have effective value zero.
Transfers within a packet stay in wire order; packets are delivered in
completion order.

| Wire order | Frame returned |
|---|---|
| A0, B0, B1 with `last` | B0, B1 |
| A1 with `last` | A0, A1 |

Unfinished packets from other identities remain available for later frame
calls. Packet assembly requires literal binary `id` and `dest`. Use raw `recv()`
to inspect meta-valued identifiers.

`send_frame()` keeps one constant effective identity. Use individual `send()`
calls to interleave packets. A changing or unresolved identity during a frame send
can fail after an earlier prefix has already been transmitted.

Raw receives deliver the next wire-order transfer and discard any unfinished
prefix for that identity. An unresolved identity discards all unfinished prefixes.
Later frame calls begin a fresh packet for an identity whose prefix was discarded,
and can therefore return packet suffixes.

A frame-length limit applies to each packet, including prefixes from earlier
calls. Any number of identities can have unfinished packets.

## Streams without `ready`

A sink without `ready` continuously captures every rising edge with `valid`
asserted after successful initialisation, including while the caller is idle.
Each snapshot becomes available at the following falling edge. An existing
backlog can be received within the current simulation step.

Use a finite capacity when unlimited growth is unsuitable. Capacity counts
undelivered transfers across the queue, an accepted snapshot awaiting publication,
a foreground receive, and unfinished packets. Delivery or explicit prefix disposal
frees capacity.

Overflow stops capture and raises `OverflowError` through the current or next
receive. Capture faults take priority over older backlog and block delivery
until recovery. A collector fault can leave queued transfers and incomplete
packets in memory. Initialisation, reset assertion, `close()`, or an in-progress
foreground failure or cancellation discards that state. Preflight rejection
leaves capture and queued traffic unchanged.

Physical traffic continues while capture is stopped. Successful initialisation
starts capture; healthy pin-reset recovery restarts it automatically.

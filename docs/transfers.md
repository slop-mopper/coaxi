# Transfers, timing, and frames

## Handshake timing

A transfer is accepted at a rising clock edge when `valid` and `ready` are
asserted. Without `ready`, `valid` alone determines acceptance.
A source drives at a falling edge and holds `data`, `last`, and sidebands
stable until acceptance. A sink asserts `ready` at a falling edge.
Reception samples at the accepting rising edge before clocked HDL updates.

A live `send()` or `recv()` returns at the falling edge after acceptance.
The source schedules `valid` and bound `last` low; the sink schedules `ready`
low, when present. Payload and other sidebands keep their values until the
next send or until the source clears its outputs.

A call made immediately on that edge can drive the next transfer. With a
receiver ready on every cycle, consecutive calls can transfer one beat per
rising edge:

```python
await source.send(10)
await source.send(20)
await source.send(30)
```

`valid` and `ready` can stay high between calls. Waiting for another
simulator phase or advancing time between calls can insert idle cycles.
This also applies within frames, between frames, and when mixing
single-transfer and frame calls.

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

An available endpoint reads one pause value in `ReadOnly` after every
rising edge, including when idle. This value controls the next falling-edge
drive. A generator can read settled signals at that point. Leave writes to
the endpoint.

A list or other sequence repeats from a copy. A generator or other non-sequence
iterable is read once, without caching; it unpauses the endpoint on the cycle
it runs out. If iteration raises or yields an invalid value, the current or
next transfer raises the error. Call `initialise()` to recover; the failed
pattern is discarded.

Call `set_pause_generator(None)` to stop a pattern and allow traffic at the
next drive. Reset suspends sampling, and the pattern resumes from the same
position after release. Reinitialisation also keeps that position. `close()`
discards the pattern. Use a simulation-time timeout for tests with intentional
stalls. See [Source gaps and sink backpressure](examples/backpressure.md)
for a test with both patterns.

## Unframed and framed streams

Without `last`, use `send()` and `recv()`. With `last`, each individual send must
explicitly identify whether it ends a frame:

```python
await source.send(10, last=False)
await source.send(20, last=True)
```

Frame helpers require a bound `last` signal.

### Send and receive concurrently

````{warning}
Avoid this order when the DUT can stall its input until its output is read:

```python
await source.send_frame(samples)
frame = await sink.recv_frame()
```

The sink holds output `ready` low until a receive is pending. The DUT may
accept some input before its buffer fills and it lowers input `ready`.
`send_frame()` then waits for the next beat to be accepted, and `recv_frame()`
never starts.
````

Start the send as a task so the receive can run before the send completes:

```python
import cocotb

sending = cocotb.start_soon(source.send_frame([10, 20]))
frame = await sink.recv_frame(max_transfers=2)
await sending
```

A source frame is a non-empty sequence of payloads.
Each received {py:class}`coaxi.AxiStreamTransfer` includes the sampled `last`
value. If reception starts part-way through a packet, it can return only
the remaining transfers.

Use simulation-time timeouts for stalled traffic. By default, frame reception
allows any packet length. Memory usage grows with unfinished packets.
A packet ending at its configured limit succeeds; one reaching that length
with `last` low raises `ValueError` after cleanup and requires `initialise()`.
Check what the peer has already sent before restarting reception.

## Interleaved packets

One packet per `(id, dest)` pair can be in progress. An unbound `id` or
`dest` counts as zero. `recv_frame()` returns whichever packet finishes first,
with its transfers in wire order.

| Wire order | Frame returned |
|---|---|
| A0, B0, B1 with `last` | B0, B1 |
| A1 with `last` | A0, A1 |

Unfinished packets from other identities remain available for later frame
calls. Packet assembly requires literal binary `id` and `dest`. Use raw `recv()`
to inspect meta-valued identifiers.

`send_frame()` uses one `(id, dest)` pair. Alternate packets with individual
`send()` calls, as in [Interleaved packets](examples/interleaved.md). If the
pair changes or becomes unresolved in `send_frame()`, the peer may already
have accepted earlier beats when the error is raised.

Raw receives deliver the next wire-order transfer and discard any unfinished
prefix for that identity. An unresolved identity discards all unfinished prefixes.
Later frame calls begin a fresh packet for an identity whose prefix was discarded,
and can therefore return packet suffixes.

A frame-length limit applies to each packet, including prefixes from earlier
calls. Any number of identities can have unfinished packets.

## Streams without `ready`

Once available, a sink without `ready` captures every rising edge with
`valid` asserted, including while the caller is idle.
Each snapshot becomes available at the following falling edge. An existing
backlog can be received within the current simulation step.

Capacity counts each accepted transfer until delivery or discard, including
snapshots waiting for the falling edge and transfers in unfinished packets.

Overflow stops capture. The current or next receive raises `OverflowError`
before returning any queued transfer. Other capture errors also stop delivery.
A background capture error can leave queued transfers and unfinished packets
in memory. Initialisation, reset assertion, `close()`, or failure or cancellation
during a receive discards them. An argument error before a receive starts
leaves capture and the queue unchanged.

The sender can keep transmitting while capture is stopped. Call
`initialise()` to recover from a capture fault. A sink that monitors reset
starts capture after the release interval. See [Capture without `ready`](examples/no-ready.md).

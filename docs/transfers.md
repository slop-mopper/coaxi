# Transfers, timing, and frames

## Handshake timing

A transfer is accepted at a rising clock edge when valid and ready are
asserted. Without ready, valid alone determines acceptance.
A source drives at a falling edge and holds data, last, and sidebands
stable until acceptance. A ready-backed sink asserts ready at a falling edge.
Reception samples at the accepting rising edge before clocked HDL updates.

Live single-transfer operations return at the following falling edge,
after scheduling valid or ready cleanup. Payload and other sidebands need
not clear after a successful send. Initialisation and close perform that cleanup.

Immediately consecutive calls can share the cleanup edge and sustain one
accepted transfer per rising edge. For an unframed source with a receiving
peer already running:

```python
await source.send(10)
await source.send(20)
await source.send(30)
```

No low valid or ready pulse is required between calls. Waiting for another
simulator phase or advancing time between calls can insert idle cycles.
The same full-rate behaviour applies within frames, between consecutive frames,
and when mixing single-transfer and frame calls. Backpressure can delay
acceptance for any number of cycles.

Only one send or receive operation may be active on an endpoint. A frame
owns its endpoint until the whole operation completes. Separate source and
sink endpoints can run concurrently.

The clock must contain literal `0` and `1` values, including while idle and
before the first initialisation. Weak or unresolved clock values are unsupported.
Endpoints do not monitor this precondition.

## Unframed and framed streams

Without last, use `send()` and `recv()`. With last, each individual send must
explicitly identify whether it ends a frame:

```python
await source.send(10, last=False)
await source.send(20, last=True)
```

Frame helpers require a bound last signal:

```python
await source.send_frame([10, 20])
frame = await sink.recv_frame(max_transfers=2)
```

Run these calls in concurrent tasks if the sender can block waiting for that
receiver. They are shown sequentially only to illustrate the two operations.
A source frame contains payloads, not received transfer objects. It must be
a non-empty sequence; generators are unsupported.

Each received {py:class}`coaxi.AxiStreamTransfer` includes the sampled last
value. It is `None` only when no last signal is bound. Frame reception starts
with the next available transfer; it does not search for a packet start.
Starting midway through a packet can produce a suffix.

Use simulation-time timeouts for stalled traffic. By default, frame reception
has no packet-length or memory limit. A length error returns no partial frame,
does not drain the rest of the packet, and requires explicit initialisation.
A packet ending at its configured limit succeeds; one reaching that length
without last fails without deliberately accepting another transfer.

## Interleaved packets

Frame reception assembles a separate incomplete packet for each effective
`(id, dest)` pair. Missing identifiers have effective value zero.
Transfers within a packet stay in wire order; packets are delivered in
completion order.

| Wire order | Frame returned |
|---|---|
| A0, B0, B1 with last | B0, B1 |
| A1 with last | A0, A1 |

Unfinished packets from other identities remain available for later frame
calls. Packet assembly requires literal binary id and dest. Use raw `recv()`
to inspect meta-valued identifiers.

`send_frame()` keeps one constant effective identity. Use individual sends
to interleave packets. A changing or unresolved identity during a frame send
can fail after an earlier prefix has already been transmitted.

Raw receives always deliver the next wire-order transfer. They discard any
unfinished prefix for that identity, so later frame calls cannot join across
a raw-consumed beat. An unresolved identity causes all unfinished prefixes to
be discarded. Mixing raw and frame receives can therefore produce packet suffixes.

A frame-length limit applies to each packet, including prefixes from earlier
calls. It does not limit the number of unfinished identities.

## Streams without ready

A no-ready sink continuously captures every valid rising edge after successful
initialisation, including while the caller is idle. Each snapshot becomes
available at the following falling edge. Receiving an existing backlog can
return without advancing simulation time.

Use a finite capacity when unlimited growth is unsuitable. Capacity counts
undelivered transfers across the queue, an accepted snapshot awaiting publication,
a foreground receive, and unfinished packets. Moving a transfer between these
locations does not free space. Delivery or explicit prefix disposal does.

Overflow stops capture and raises `OverflowError` through the current or next
receive. Capture faults take priority over older backlog and block delivery
until recovery. A collector fault can leave queued transfers and incomplete
packets in memory. Initialisation, reset assertion, close, or an in-progress
foreground failure or cancellation discards that state. Preflight rejection
does not stop capture or discard traffic.

Stopping capture cannot prevent physical acceptance on a bus without ready.
Traffic before initialisation or while capture is stopped is unavailable.
Use `close()` when the sink is no longer needed.

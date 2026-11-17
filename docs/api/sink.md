# AxiStreamSink

```{py:currentmodule} coaxi
```

Receives transfer snapshots and drives `ready`, when present.
Await `initialise()` before use. The caller must supply a clock containing literal
`0` and `1` from before the first initialisation onwards; endpoints do not monitor clock values.

```{py:class} AxiStreamSink[T = PayloadValue | None](bus: AxiStreamBus, clock: Signal, *, payload: Payload[T] | None = None, buffer_capacity: int | None = None, reset: Signal | None = None, reset_active_high: bool = False) -> None

:Parameters:
  - `bus: AxiStreamBus`

    Validated stream binding.

  - `clock: Signal`

    Independent child name in the bus's binding entity, or a one-bit logic handle.

  - `payload: Payload[T] | None`

    Custom synchronous snapshot adapter. Default `None` selects `HandlePayload`, or data-less access when `data` is absent. A custom adapter requires `data`.

  - `buffer_capacity: int | None`

    Maximum number of undelivered transfers without `ready`. Positive integer, excluding `bool`; default `None` is unlimited. A finite value requires a bus without `ready`.

  - `reset: Signal | None`

    Optional mutable one-bit reset name or handle. Default `None` disables monitoring.

  - `reset_active_high: bool`

    `True` for active-high, `False` for active-low. Default `False`; must be a `bool`.

:returns: `None`.
```

Default endpoints use `PayloadValue | None`. A `Payload[T]` adapter selects `T`
through the constructor overloads. The sink uses the adapter's `read()` method.

With `ready`, reception is call-driven. Without `ready`, successful initialisation
starts continuous capture, including while the caller is idle.
See [Streams without `ready`](../transfers.md#streams-without-ready) for capacity
accounting and overflow.

## recv

```{py:method} AxiStreamSink.recv() -> AxiStreamTransfer[T]
:async:

:returns: The next wire-order transfer snapshot. Absent `data`, `last`, and sidebands are `None`.
:raises EndpointStateError: The endpoint is unavailable or another operation is active.
:raises ProtocolValueError: Sampled controls, reset, or literal byte-qualifier pairs are invalid.
:raises OverflowError: Capture without `ready` exceeds its capacity.
:raises TransferReset: Reset, initialisation, or `close()` interrupts the receive.
```

Works with framed and unframed streams. A sink with `ready` samples at the accepting
rising edge and returns at the following falling edge. Immediately consecutive
receives can keep `ready` asserted and sustain one transfer per rising edge.
Without `ready`, existing backlog returns immediately; live snapshots become
available at the following falling edge.

Raw reception discards the unfinished packet prefix for that transfer's
identity. An unresolved identity discards all unfinished prefixes.
Payload and sideband meta-values stay raw; `valid` and accepted `last` must be
literal `0` or `1`. Capture faults are reported before older backlog.

## recv_frame

```{py:method} AxiStreamSink.recv_frame(*, max_transfers: int | None = None) -> list[AxiStreamTransfer[T]]
:async:

:Parameters:
  - `max_transfers: int | None`

    Positive integer limit per packet, including earlier unfinished prefixes; `bool` is rejected. Default `None` allows any packet length.

:returns: A non-empty list of snapshots for the next completed packet, in its transfer order.
:raises TypeError: The limit is not an integer or `None`.
:raises ValueError: `last` is absent, the limit is not positive, or a packet reaches its limit without `last`.
:raises ProtocolValueError: Controls, reset, qualifiers, or packet identifiers are invalid.
:raises EndpointStateError: The endpoint is unavailable or another operation is active.
:raises OverflowError: Capture without `ready` exceeds its capacity.
:raises TransferReset: Reset, initialisation, or `close()` interrupts assembly.
```

Requires `last`. Assembles independent packets by effective `(id, dest)`, with
absent identifiers treated as zero. Packet identifiers must be literal binary.
Packets return in completion order; other unfinished packets remain for later
calls. Collection begins at the next transfer, possibly midway through a packet.

A packet ending at the configured limit succeeds. Reaching the limit with
`last` low raises after cleanup. A previously unfinished packet already at the
limit fails before consuming more snapshots. Any number of identities can be incomplete.

Use a simulation-time timeout. In-progress faults and caller cancellation discard
queued transfers and incomplete packets, stop capture, and require `initialise()`.
`TransferReset` follows the interrupting lifecycle operation: healthy pin-only
reset resumes automatically, explicit initialisation recovers, and `close()`
leaves the endpoint stopped. Physical traffic on a bus without `ready` continues
while capture is stopped. Preflight argument errors leave the endpoint and
queued traffic unchanged. Payload read errors propagate with their original types.

## initialise

```{py:method} AxiStreamSink.initialise() -> None
:async:

:returns: `None`, when local recovery and any reset-release interval have completed and continuous capture has started if needed.
:raises EndpointStateError: Initialisation or `close()` is already active.
:raises ProtocolValueError: The monitored reset pin is invalid.
```

Invalidates pending work, discards queued transfers and incomplete packets,
acknowledges faults, and clears `ready`. Without a reset pin, waits for a falling
edge. With monitoring, waits through any asserted reset and release interval.
DUT reset is caller-controlled. A stopped clock or asserted reset can make
this wait indefinitely.

## close

```{py:method} AxiStreamSink.close() -> None
:async:

:returns: `None`, after capture and monitoring stop and `ready` clears at a falling edge. Without `ready`, completes immediately.
:raises EndpointStateError: Initialisation or `close()` is already active.
```

Invalidates work and discards queued transfers, incomplete packets, and faults.
Repeated calls are safe. Explicit `initialise()` restarts the endpoint.
Failed or cancelled `close()` leaves it closed, though `ready` cleanup may be incomplete.

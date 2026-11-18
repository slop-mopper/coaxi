# AxiStreamSink

```{py:currentmodule} coaxi
```

Receives transfers and drives `ready`, when present. Await `initialise()`
before receiving. Supply a clock with literal `0` and `1` from before
initialisation; the sink does not check clock values.

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

With `ready`, the sink receives only during a call. Without `ready`, it
captures transfers after initialisation even when no receive is pending.
See [Streams without `ready`](../transfers.md#streams-without-ready) for
capacity and overflow.

## set_pause_generator

```{py:method} AxiStreamSink.set_pause_generator(pattern: Iterable[bool | int] | None = None) -> None

:Parameters:
  - `pattern: Iterable[bool | int] | None`

    `True` or `1` pauses; `False` or `0` allows reception. A sequence is copied and repeated. Other iterables are consumed once. An empty sequence or `None` disables pausing.

:returns: `None`.
:raises TypeError: The pattern is neither iterable nor `None`.
:raises ValueError: `ready` is absent and the pattern is not `None`, or a sequence contains an invalid value.
```

A pause holds `ready` low during pending receives. A sink requires `ready` to
stall the sender. See [Simulated backpressure](../transfers.md#simulated-backpressure)
for clock timing, exhaustion, and iteration errors.

## recv

```{py:method} AxiStreamSink.recv() -> AxiStreamTransfer[T]
:async:

:returns: The next wire-order transfer snapshot. Absent `data`, `last`, and sidebands are `None`.
:raises EndpointStateError: The endpoint is unavailable or another operation is active.
:raises ProtocolValueError: Sampled controls, reset, or literal byte-qualifier pairs are invalid.
:raises OverflowError: Capture without `ready` exceeds its capacity.
:raises TransferReset: Reset, initialisation, or `close()` interrupts the receive.
```

The sink samples at the accepting rising edge and makes the transfer
available at the following falling edge. Without `ready`, a queued transfer
can return immediately.

`recv()` discards any unfinished packet for that transfer's `(id, dest)`.
An unresolved identity discards all unfinished packets. Payload and sideband
meta-values are returned as sampled. The sink samples `valid` when `ready`
is high or absent; sampled `valid` and accepted `last` must be literal `0` or
`1`. A capture error is raised before any queued transfer is returned.

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

Requires `last` and literal binary packet identifiers. An unbound `id` or
`dest` counts as zero. `recv_frame()` returns whichever packet finishes
first and keeps other unfinished packets for later calls. A call that starts
part-way through a packet can return only its remaining transfers.

A packet ending at the configured limit succeeds. Reaching the limit with
`last` low raises after cleanup. A previously unfinished packet already at the
limit fails before consuming more snapshots. Any number of identities can be incomplete.

Use a simulation-time timeout. A fault or cancellation during reception
discards queued transfers and incomplete packets, stops capture, and requires
`initialise()`. Argument checks before reception leave queued traffic unchanged.
Adapter exceptions propagate unchanged. See [Lifecycle and recovery](../lifecycle.md)
for reset and interruption.

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

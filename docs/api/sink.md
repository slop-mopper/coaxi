# AxiStreamSink

```{py:currentmodule} coaxi
```

Receives transfer snapshots and drives only ready, when present. Construction
does not drive signals. Await `initialise()` before use. The clock must contain
literal `0` and `1` from before the first initialisation onwards; this is not monitored.

```{py:class} AxiStreamSink[T = PayloadValue | None](bus: AxiStreamBus, clock: Signal, *, payload: Payload[T] | None = None, buffer_capacity: int | None = None, reset: Signal | None = None, reset_active_high: bool = False) -> None

:param bus: Validated stream binding.
:type bus: AxiStreamBus
:param clock: Independent child name in the bus's binding entity, or a one-bit logic handle.
:type clock: Signal
:param payload: Custom synchronous snapshot adapter. Default `None` selects `HandlePayload`, or data-less access when data is absent. A custom adapter requires data.
:type payload: Payload[T] | None
:param buffer_capacity: Maximum number of undelivered transfers without ready. Positive integer, excluding `bool`; default `None` is unlimited. A finite value is forbidden with ready.
:type buffer_capacity: int | None
:param reset: Optional mutable one-bit reset name or handle. Default `None` disables monitoring.
:type reset: Signal | None
:param reset_active_high: `True` for active-high, `False` for active-low. Default `False`; must be a `bool`.
:type reset_active_high: bool
:returns: None.
:rtype: None
```

Default payload typing is `PayloadValue | None`. A `Payload[T]` adapter selects
`T` through the constructor overloads. The sink never calls an adapter's
`clear()` or `drive()`.

With ready, reception is call-driven and has no transfer queue. Without ready,
successful initialisation starts continuous capture, including while the caller
is idle. See [Streams without ready](../transfers.md#streams-without-ready)
for capacity accounting and overflow.

## recv

```{py:method} AxiStreamSink.recv() -> AxiStreamTransfer[T]
:async:

:returns: The next wire-order transfer snapshot. Absent data, last, and sidebands are `None`.
:rtype: AxiStreamTransfer[T]
:raises EndpointStateError: The endpoint is unavailable or another operation is active.
:raises ProtocolValueError: Sampled controls, reset, or literal byte-qualifier pairs are invalid.
:raises OverflowError: No-ready capture exceeds its capacity.
:raises TransferReset: Reset, initialisation, or close interrupts the receive.
```

No optional signal is required. A ready-backed sink samples at the accepting
rising edge and returns at the following falling edge. Immediately consecutive
receives can keep ready asserted and sustain one transfer per rising edge.
Without ready, existing backlog returns immediately; live snapshots become
available at the following falling edge.

Raw reception discards the unfinished packet prefix for that transfer's
identity. An unresolved identity discards all unfinished prefixes.
Payload and sideband meta-values stay raw; valid and accepted last must be
literal `0` or `1`. Capture faults are reported before older backlog.

## recv_frame

```{py:method} AxiStreamSink.recv_frame(*, max_transfers: int | None = None) -> list[AxiStreamTransfer[T]]
:async:

:param max_transfers: Positive integer limit per packet, including earlier unfinished prefixes; `bool` is rejected. Default `None` has no length limit.
:type max_transfers: int | None
:returns: A non-empty list of snapshots for the next completed packet, in its transfer order.
:rtype: list[AxiStreamTransfer[T]]
:raises TypeError: The limit is not an integer or `None`.
:raises ValueError: Last is absent, the limit is not positive, or a packet reaches its limit without last.
:raises ProtocolValueError: Controls, reset, qualifiers, or packet identifiers are invalid.
:raises EndpointStateError: The endpoint is unavailable or another operation is active.
:raises OverflowError: No-ready capture exceeds its capacity.
:raises TransferReset: Reset, initialisation, or close interrupts assembly.
```

Requires last. Assembles independent packets by effective `(id, dest)`, with
absent identifiers treated as zero. Packet identifiers must be literal binary.
Packets return in completion order; other unfinished packets remain for later
calls. Collection begins at the next transfer, possibly midway through a packet.

A packet ending at the configured limit succeeds. Reaching the limit without
last fails after cleanup, with no deliberate extra acceptance or draining.
A previously unfinished packet already at the limit fails before consuming
more snapshots. There is no limit on the number of incomplete identities.

Use a simulation-time timeout. In-progress faults and caller cancellation return
no partial list, discard queued/partial state, stop no-ready capture, and require
initialisation. `TransferReset` follows the interrupting lifecycle operation:
healthy pin-only reset resumes automatically, explicit initialisation recovers,
and close leaves the endpoint stopped.
Stopping capture cannot prevent physical traffic on a no-ready bus.
Preflight argument errors leave the endpoint usable and do not discard traffic.
Payload read errors propagate with their original types.

## initialise

```{py:method} AxiStreamSink.initialise() -> None
:async:

:returns: None, when local recovery and any reset-release interval have completed and no-ready capture has started if needed.
:rtype: None
:raises EndpointStateError: Initialisation or close is already active.
:raises ProtocolValueError: The monitored reset pin is invalid.
```

Invalidates pending work, discards queued transfers and incomplete packets,
acknowledges faults, and clears ready. Incoming data is never cleared.
Without a reset pin, waits for a falling edge. With monitoring, waits through
any asserted reset and release interval. It never drives the DUT reset.
A stopped clock or asserted reset can make this wait indefinitely.

## close

```{py:method} AxiStreamSink.close() -> None
:async:

:returns: None, after capture/monitoring stop and ready clears at a falling edge. Without ready, no clock edge is needed.
:rtype: None
:raises EndpointStateError: Initialisation or close is already active.
```

Invalidates work and discards queued transfers, incomplete packets, and faults.
Repeated closes are safe. Pin activity cannot reopen a closed endpoint.
Initialisation is required to restart it. Failed or cancelled close leaves it
closed, though ready cleanup may be incomplete.

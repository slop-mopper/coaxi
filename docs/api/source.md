# AxiStreamSource

```{py:currentmodule} coaxi
```

Drives source-owned signals. Construction is non-driving; await `initialise()`
before sending. The clock must contain literal `0` and `1` from before the first
initialisation onwards. This precondition is not monitored.

```{py:class} AxiStreamSource[T = PayloadValue | None](bus: AxiStreamBus, clock: Signal, *, payload: Payload[T] | None = None, reset: Signal | None = None, reset_active_high: bool = False) -> None

:param bus: Validated stream binding.
:type bus: AxiStreamBus
:param clock: Independent child name in the bus's binding entity, or a one-bit logic handle.
:type clock: Signal
:param payload: Custom synchronous adapter. Default `None` selects `HandlePayload`, or data-less access when data is absent. A custom adapter requires data.
:type payload: Payload[T] | None
:param reset: Optional mutable one-bit reset name or handle. Default `None` disables monitoring.
:type reset: Signal | None
:param reset_active_high: `True` for active-high, `False` for active-low. Default `False`; must be a `bool`.
:type reset_active_high: bool
:returns: None.
:rtype: None
```

Without an adapter the payload type is `PayloadValue | None`. With a
`Payload[T]` adapter it is `T`. The constructor overloads enforce that relation.
Only one send operation can be active at a time. Payload and adapter errors
propagate with their original exception types, including errors during
initialisation or close.

## send

```{py:method} AxiStreamSource.send(data: T, *, last: bool | None = None, sidebands: AxiStreamSidebands | None = None) -> None
:async:

:param data: Payload for one transfer. With the default adapter, `None` requires absent data. Do not mutate it until completion.
:type data: T
:param last: Required explicit `bool` when last is bound; must be `None` otherwise. Default `None`.
:type last: bool | None
:param sidebands: Per-transfer metadata overrides. Default `None` uses the source defaults on bound signals.
:type sidebands: AxiStreamSidebands | None
:returns: None, at the falling-edge cleanup after acceptance.
:rtype: None
:raises TypeError: The metadata type is invalid.
:raises ValueError: Last selection or sideband values are invalid.
:raises EndpointStateError: The endpoint is unavailable or another operation is active.
:raises ProtocolValueError: Sampled ready or monitored reset is invalid.
:raises TransferReset: Reset, initialisation, or close interrupts the operation.
```

No optional signal is required. Drives begin at a falling edge and remain
stable through backpressure. Without ready, the next valid rising edge accepts.
Immediately consecutive calls can sustain one transfer per rising edge.

Invalid last or metadata fails before starting work. Payload failures occur
during the operation and require recovery. Errors and cancellation can occur
after acceptance; do not retry without checking what the peer accepted.

## send_frame

```{py:method} AxiStreamSource.send_frame(data: Sequence[T], *, sidebands: Sequence[AxiStreamSidebands] | None = None) -> None
:async:

:param data: Non-empty sequence of payloads. Generators and sequences of received transfer objects are not frame inputs.
:type data: Sequence[T]
:param sidebands: Parallel sequence with one metadata object per payload. Default `None` uses defaults for every transfer.
:type sidebands: Sequence[AxiStreamSidebands] | None
:returns: None, at the final transfer's falling-edge cleanup.
:rtype: None
:raises TypeError: An input is not a sequence, or a metadata entry has the wrong type.
:raises ValueError: Last is absent, input is empty, lengths differ, or per-transfer metadata/identity is invalid.
:raises EndpointStateError: The endpoint is unavailable or another operation is active.
:raises ProtocolValueError: Sampled ready or monitored reset is invalid.
:raises TransferReset: Reset, initialisation, or close interrupts the frame.
```

Requires last and generates it only on the final transfer. The effective
`(id, dest)` stays constant and must be literal binary. Use individual sends
to interleave packets.

The endpoint is reserved for the whole frame. Payloads and metadata are
validated per transfer, so later failures may follow an accepted prefix.
Do not mutate either sequence or its values until completion.
No rollback or packet realignment is performed.

## initialise

```{py:method} AxiStreamSource.initialise() -> None
:async:

:returns: None, when local recovery and any reset-release interval have completed.
:rtype: None
:raises EndpointStateError: Initialisation or close is already active.
:raises ProtocolValueError: The monitored reset pin is invalid.
```

Invalidates pending operations, acknowledges faults, and clears valid, last,
payload, and bound sidebands. Without a reset pin, clearing occurs at a falling
edge. With monitoring, clearing occurs at the first writable opportunity.
Waits through any asserted reset and release interval. Never drives the reset pin.

Initialisation can wait indefinitely for a running clock or released reset.
Cancellation requires a later successful initialisation. See
[Lifecycle and recovery](../lifecycle.md) for asynchronous assertion and release timing.

## close

```{py:method} AxiStreamSource.close() -> None
:async:

:returns: None, after stopping monitoring and clearing source outputs at a falling edge.
:rtype: None
:raises EndpointStateError: Initialisation or close is already active.
```

Invalidates pending work and clears local faults. Repeated closes are safe.
The endpoint stays closed after failure or cancellation, though output cleanup
may be incomplete. Explicit initialisation is required to reopen it.

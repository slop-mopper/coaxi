# AxiStreamSource

```{py:currentmodule} coaxi
```

Drives source-owned signals after `initialise()`. The caller must supply a
clock containing literal `0` and `1` from before the first initialisation
onwards; endpoints do not monitor clock values.

```{py:class} AxiStreamSource[T = PayloadValue | None](bus: AxiStreamBus, clock: Signal, *, payload: Payload[T] | None = None, reset: Signal | None = None, reset_active_high: bool = False) -> None

:Parameters:
  - `bus: AxiStreamBus`

    Validated stream binding.

  - `clock: Signal`

    Independent child name in the bus's binding entity, or a one-bit logic handle.

  - `payload: Payload[T] | None`

    Custom synchronous adapter. Default `None` selects `HandlePayload`, or data-less access when `data` is absent. A custom adapter requires `data`.

  - `reset: Signal | None`

    Optional mutable one-bit reset name or handle. Default `None` disables monitoring.

  - `reset_active_high: bool`

    `True` for active-high, `False` for active-low. Default `False`; must be a `bool`.

:returns: `None`.
```

Default endpoints use `PayloadValue | None`. Supplying a `Payload[T]` adapter
selects `T` through the constructor overloads.
Only one send operation can be active at a time. Payload and adapter errors
propagate with their original exception types, including errors during
initialisation or `close()`.

## set_pause_generator

```{py:method} AxiStreamSource.set_pause_generator(pattern: Iterable[bool | int] | None = None) -> None

:Parameters:
  - `pattern: Iterable[bool | int] | None`

    `True` or `1` pauses; `False` or `0` allows a new transfer. A sequence is copied and repeated. Other iterables are consumed once. An empty sequence or `None` disables pausing.

:returns: `None`.
:raises TypeError: The pattern is neither iterable nor `None`.
:raises ValueError: A sequence contains a value other than `True`, `False`, `1`, or `0`.
```

A pause delays the next assertion of `valid`. An offered transfer stays stable
until accepted, even if the pattern pauses again.
See [Simulated backpressure](../transfers.md#simulated-backpressure) for clock
timing, exhaustion, and iteration errors.

## send

```{py:method} AxiStreamSource.send(data: T, *, last: bool | None = None, sidebands: AxiStreamSidebands | None = None) -> None
:async:

:Parameters:
  - `data: T`

    Payload for one transfer. With the default adapter, `None` requires absent `data`. Keep the value unchanged until completion.

  - `last: bool | None`

    Required explicit `bool` when `last` is bound; must be `None` otherwise. Default `None`.

  - `sidebands: AxiStreamSidebands | None`

    Per-transfer metadata overrides. Default `None` uses the source defaults on bound signals.

:returns: `None`, at the falling-edge cleanup after acceptance.
:raises TypeError: The metadata type is invalid.
:raises ValueError: `last` selection or sideband values are invalid.
:raises EndpointStateError: The endpoint is unavailable or another operation is active.
:raises ProtocolValueError: Sampled `ready` or monitored reset is invalid.
:raises TransferReset: Reset, initialisation, or `close()` interrupts the operation.
```

Works with framed and unframed streams. Drives begin at a falling edge and
remain stable through backpressure. Without `ready`, the next rising edge
with `valid` asserted accepts. Immediately consecutive calls can sustain one transfer per rising edge.

Invalid `last` or metadata fails before starting work. Payload failures occur
during the operation and require recovery. Errors and cancellation can occur
after acceptance; check what the peer accepted before retrying.

## send_frame

```{py:method} AxiStreamSource.send_frame(data: Sequence[T], *, sidebands: Sequence[AxiStreamSidebands] | None = None) -> None
:async:

:Parameters:
  - `data: Sequence[T]`

    Non-empty sequence of payloads. Keep the sequence and its values unchanged until completion.

  - `sidebands: Sequence[AxiStreamSidebands] | None`

    Parallel sequence with one metadata object per payload. Default `None` uses defaults for every transfer. Keep the sequence and its values unchanged until completion.

:returns: `None`, at the final transfer's falling-edge cleanup.
:raises TypeError: An input is not a sequence, or a metadata entry has the wrong type.
:raises ValueError: `last` is absent, input is empty, lengths differ, or per-transfer metadata/identity is invalid.
:raises EndpointStateError: The endpoint is unavailable or another operation is active.
:raises ProtocolValueError: Sampled `ready` or monitored reset is invalid.
:raises TransferReset: Reset, initialisation, or `close()` interrupts the frame.
```

Requires `last` and asserts it on the final transfer. The effective `(id, dest)`
stays constant and must be literal binary. Use individual `send()` calls to
interleave packets.

The endpoint is reserved for the whole frame. Payloads and metadata are
validated per transfer, so later failures may follow an accepted prefix.
Coordinate recovery with the peer to restore packet alignment.

## initialise

```{py:method} AxiStreamSource.initialise() -> None
:async:

:returns: `None`, when local recovery and any reset-release interval have completed.
:raises EndpointStateError: Initialisation or `close()` is already active.
:raises ProtocolValueError: The monitored reset pin is invalid.
```

Invalidates pending operations, acknowledges faults, and clears `valid`, `last`,
payload, and bound sidebands. Without a reset pin, clearing occurs at a falling
edge. With monitoring, clearing occurs at the first writable opportunity.
Waits through any asserted reset and release interval. DUT reset is caller-controlled.

Initialisation can wait indefinitely for a running clock or released reset.
Cancellation requires a later successful initialisation. See
[Lifecycle and recovery](../lifecycle.md) for asynchronous assertion and release timing.

## close

```{py:method} AxiStreamSource.close() -> None
:async:

:returns: `None`, after stopping monitoring and clearing source outputs at a falling edge.
:raises EndpointStateError: Initialisation or `close()` is already active.
```

Invalidates pending work and clears local faults. Repeated calls are safe.
The endpoint stays closed after failure or cancellation, though output cleanup
may be incomplete. Explicit `initialise()` reopens it.

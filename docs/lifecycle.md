# Lifecycle and recovery

Construction binds and validates handles. Driving starts with `initialise()`.
Await `initialise()` before sending or receiving. It clears local state and
owned outputs, and acknowledges previous faults and cancellation.
DUT reset is caller-controlled.

| Endpoint | Owned signals |
|---|---|
| Source | `data`, `valid`, `last`, and bound sidebands |
| Sink | `ready`, when present |

Without a monitored reset pin, initialisation clears at a falling edge.
The source clears `valid`, `last`, and bound sidebands to zero, and calls the
payload adapter's `clear()`. `HandlePayload` clears every payload leaf to zero;
custom adapters define their own recovery values and can raise during clearing.
The sink clears its `ready` signal, queued transfers, and incomplete packets.
A sink without `ready` starts continuous capture after successful
initialisation.

Local recovery clears endpoint state. Coordinate DUT reset and peer recovery
to empty DUT buffers and restore packet alignment during active traffic.

## Reset-pin monitoring

Reset monitoring is optional, independently bound, and starts with
`initialise()`. For an active-high pin:

```python
source = AxiStreamSource(
	bus,
	clock=dut.clk,
	reset="my_reset",
	reset_active_high=True,
)
await source.initialise()
```

Choose the polarity explicitly; the default is active-low.
The pin must be mutable one-bit logic and separate from the clock and stream
signals. Pin values must be literal `0` or `1`; weak and unresolved values
latch `ProtocolValueError` and stop traffic.

Assertion invalidates pending work, stops capture, discards queued transfers
and incomplete packets, and clears owned outputs at the first writable
opportunity, including while the clock is stopped.
If observed in `ReadOnly`, clearing is deferred by one simulator step.

Release uses this interval:

| Edge | Endpoint state |
|---|---|
| R0 | First rising edge sampling the inactive pin |
| R1 | Following rising edge; traffic still disabled |
| F1 | Falling edge after R1; endpoint becomes available |
| R2 | Earliest new transfer acceptance |

The caller must deassert reset synchronously after a rising edge.
This conservative release interval follows Arm IHI 0051B §2.8.2, adapted to
the chosen polarity. Reassertion restarts the interval.

A healthy endpoint resumes automatically after a pin-only interruption,
including continuous capture. Check accepted traffic before restarting interrupted work.
New calls during assertion or release raise `EndpointStateError`.
Earlier faults, overflow, failed operations, and cancellation still need
explicit `initialise()`.
The first latched fault continues to be reported until explicit recovery or `close()`.

Initialisation waits through assertion and release. It can wait indefinitely
if reset stays asserted or the clock stops. Cancelled initialisation leaves
monitoring active for output safety, but a later successful initialisation is
needed before traffic can resume.

## Errors and cancellation

Preflight errors leave the endpoint usable. Examples include missing `last` for
a frame operation, an invalid single-send metadata value, an empty frame,
a metadata-sequence length mismatch, or an invalid frame-length limit.

In-progress conversion, protocol, metadata, capture, or frame-length faults,
and caller cancellation require `initialise()`. A healthy pin-only reset
interrupts work with `TransferReset` and resumes automatically after release.
Explicit initialisation performs its own recovery; interruption by `close()` leaves
the endpoint stopped until it is initialised again.
Cancellation leaves driven outputs for explicit cleanup unless pin monitoring
subsequently clears them.

A transfer can be accepted at a rising edge before interruption prevents the
call from returning at its cleanup edge. Blindly retrying can duplicate traffic.
Use a scoreboard or DUT-level recovery to determine what happened.

Initialisation, pin assertion, and `close()` interrupt active operations with
{py:class}`coaxi.TransferReset`. An invalid reset or recorded fault can instead
report that fault. Catch expected interruption inside spawned coroutines:

```python
import cocotb
from cocotb.triggers import Timer
from coaxi import TransferReset


async def receive_until_interrupted() -> None:
	try:
		await sink.recv()
	except TransferReset:
		pass


receiving = cocotb.start_soon(receive_until_interrupted())
await Timer(100, unit="ns")
await sink.initialise()
await receiving
```

The snippet assumes an initialised sink and a running clock.
Cocotb can fail a test on an unobserved task exception before a later await
observes it. Handle other expected faults inside the task as appropriate.

Concurrent transfer operations on one endpoint, unavailable endpoints, and
overlapping `initialise()` and `close()` calls raise {py:class}`coaxi.EndpointStateError`.
Invalid bindings raise {py:class}`coaxi.SignalBindingError`.
See [Errors](api/index.md#errors) for the remaining exception contracts.

## Closing

`close()` stops reset monitoring and capture, discards queued state and faults,
and invalidates active operations. A source or sink with `ready` clears its
outputs at a falling edge. A sink without `ready` closes immediately.
Repeated closes are safe.

A failed or cancelled close leaves the endpoint closed, but output cleanup may
be incomplete. Explicit `initialise()` starts it again.
Run initialisation and `close()` sequentially.

Routine transfer, framing, initialisation, and reset activity is logged at
DEBUG level through `coaxi.stream`.

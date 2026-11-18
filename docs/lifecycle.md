# Lifecycle and recovery

Await `initialise()` before sending or receiving. It clears the endpoint's
state, outputs, and previous faults. Reset the DUT separately.

| Endpoint | Owned signals |
|---|---|
| Source | `data`, `valid`, `last`, and bound sidebands |
| Sink | `ready`, when present |

Without a monitored reset pin, initialisation clears at a falling edge.
The source clears `valid`, `last`, and bound sidebands to zero, and calls the
payload adapter's `clear()`. `HandlePayload` clears every payload leaf to zero;
custom adapters define their own recovery values and can raise during clearing.
The sink clears `ready`, queued transfers, and incomplete packets. It never
calls the adapter's `clear()`. Without `ready`, capture starts as soon as
initialisation succeeds.

If you initialise during traffic, reset or drain the DUT and coordinate with
the peer before starting another packet.

## Reset-pin monitoring

To monitor an active-high reset pin, bind it when constructing the endpoint.
Monitoring starts with `initialise()`:

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

The endpoint waits through these edges after release:

| Edge | Endpoint state |
|---|---|
| R0 | First rising edge sampling the inactive pin |
| R1 | Following rising edge; traffic still disabled |
| F1 | Falling edge after R1; endpoint becomes available |
| R2 | Earliest transfer through the re-enabled endpoint |

The caller must deassert reset synchronously after a rising edge.
The interval follows Arm IHI 0051B §2.8.2 for the chosen polarity.
Reasserting reset restarts the interval.

A healthy endpoint resumes after release, including capture without `ready`.
Calls during assertion or release raise `EndpointStateError`. The endpoint
keeps reporting a previous fault until `initialise()` or `close()`.

`initialise()` waits through the release interval even if the pin is already
inactive. It can wait indefinitely if reset stays asserted or the clock stops.
Cancelling it leaves reset monitoring active to clear outputs on assertion.
Call `initialise()` again before starting traffic. See
[Interrupt a stalled send with reset](examples/reset-recovery.md).

## Errors and cancellation

Argument checks before a transfer leave the endpoint usable. If an operation
fails after it starts, or you cancel it, call `initialise()` before starting
another. On cancellation, the outputs keep their driven values until
initialisation, `close()`, or reset assertion clears them.

Check what the peer accepted before retrying. An operation can be interrupted
after acceptance and before it returns. Use a scoreboard or reset both ends
to avoid sending a transfer twice.

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

`close()` stops reset monitoring, capture, and pause sampling. It discards
queued state, faults, and the pause pattern, and invalidates active operations.
A source or sink with `ready` clears its outputs at a falling edge.
A sink without `ready` closes immediately.
Repeated closes are safe.

A failed or cancelled close leaves the endpoint closed, but output cleanup may
be incomplete. Explicit `initialise()` starts it again.

Enable `DEBUG` on `coaxi.stream` to log transfers, framing, initialisation,
and reset.

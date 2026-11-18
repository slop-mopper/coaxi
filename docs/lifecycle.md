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
calls the adapter's `clear()`. Without `ready` or reset monitoring, capture
starts when initialisation completes.

If you initialise during traffic, reset or drain the DUT and coordinate with
the peer before starting another packet.

## Reset-pin monitoring

To monitor an active-high reset pin, bind it when constructing the endpoint:

```python
source = AxiStreamSource(
	bus,
	clock=dut.clk,
	reset="my_reset",
	reset_active_high=True,
)
```

Choose the polarity explicitly; the default is active-low.
The pin must be mutable one-bit logic and separate from the clock and stream
signals. `initialise()` samples the pin after writes for the current simulator
time step settle. Any sampled value other than literal `0` or `1` latches
`ProtocolValueError`. The call clears the endpoint's outputs and returns
without waiting for reset release or a clock edge.

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

The release interval applies even when the pin is already inactive at setup.
In code that previously sent or received immediately after `initialise()`
with a reset pin, add `await endpoint.wait_available()` before that first
transfer. If the same task controls reset, deassert it before waiting.
The wait is optional: once the interval ends, transfers work automatically.
An early send or receive raises `EndpointStateError` without queuing a
transfer. `wait_available()` can block while reset is asserted or the clock
is stopped. Cancelling the wait leaves the endpoint unchanged.

See [Start and recover with a reset pin](examples/reset-recovery.md).

Cancelling `initialise()` leaves reset monitoring active to clear outputs on
assertion. Call `initialise()` again before starting traffic.

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

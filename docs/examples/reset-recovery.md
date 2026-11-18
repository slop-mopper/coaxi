# Interrupt a stalled send with reset

Start a send while the sink is idle, then assert an active-high reset pin.
The send raises `TransferReset`, and the source clears `valid`. The test
releases reset after a rising edge and sends a different value after both
endpoints resume.

```{literalinclude} ../../examples/reset_recovery.py
:language: python
:lines: 7-
```

```console
uv run --locked pytest -q tests/test_simulation.py -k reset_recovery
```

The shared `plain` bus and `reset_lane` pin in
{download}`stream_dut.vhd <../../tests/hdl/stream_dut.vhd>` have no HDL
logic between the endpoints. In a DUT test, reset its logic separately or
connect the same pin to it. Check what was accepted before retrying
interrupted work: this test checks `ready` was low, but a transfer can be
accepted before its send returns.

A pin-only reset restarts healthy endpoints after the release interval. It
does not clear an earlier fault or cancellation; call `initialise()` for
those. See [Reset-pin monitoring](../lifecycle.md#reset-pin-monitoring).

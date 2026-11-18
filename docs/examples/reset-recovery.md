# Start and recover with a reset pin

The VHDL reset pin starts at `U`. The test writes `1` and calls `initialise()`
on both endpoints while the clock is stopped. Initialisation samples the
settled pin and returns while reset is asserted. The test starts the clock,
releases reset, and calls `wait_available()` before sending.

The test then asserts reset during a stalled send, checks for `TransferReset`
and `valid` going low, and sends a different value after release.

```{literalinclude} ../../examples/reset_recovery.py
:language: python
:lines: 7-
```

```console
uv run --locked pytest -q tests/test_simulation.py -k reset_recovery
```

The shared `plain` bus and `startup_reset` pin in
{download}`stream_dut.vhd <../../tests/hdl/stream_dut.vhd>` have no HDL
logic between the endpoints. In a DUT test, reset its logic separately or
connect the same pin to it. Check what was accepted before retrying
interrupted work: this test checks `ready` was low, but a transfer can be
accepted before its send returns.

A pin-only reset restarts healthy endpoints after the release interval. It
does not clear an earlier fault or cancellation; call `initialise()` for
those. See [Reset-pin monitoring](../lifecycle.md#reset-pin-monitoring).

# Start and recover with a reset pin

Start both endpoints while an active-high reset is asserted. The VHDL pin
starts at `U`, so let the write of `1` take effect before starting
`initialise()`. Both calls wait for the test to release reset. The test then
asserts reset during a stalled send, checks that the send raises `TransferReset`
and clears `valid`, and sends a different value after release.

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

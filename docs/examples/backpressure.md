# Source gaps and sink backpressure

Send a frame through the one-entry register in
{download}`stream_dut.vhd <../../tests/hdl/stream_dut.vhd>`. The source's
generator permits two cycles of new offers, then pauses for one. The sink's
list permits one cycle of reception out of every three. The test checks that
the register accepted and forwarded every value in order.

```{literalinclude} ../../examples/backpressure.py
:language: python
:lines: 7-
```

```console
uv run --locked pytest -q tests/test_simulation.py -k backpressure
```

Both patterns advance while the endpoints are idle. A paused source still
holds a beat it has already offered until the peer accepts it. The sink
needs `ready` to stall the register. Keep the test timeout: a pattern that
never permits traffic can leave an operation waiting indefinitely.

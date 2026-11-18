# Capture without `ready`

Count three events on a bus with only `valid`. The source sends `None`
because `data` is also absent. The sink starts capturing at initialisation;
all three events arrive before the first `recv()` call.

```{literalinclude} ../../examples/no_ready.py
:language: python
:lines: 7-
```

```console
uv run --locked pytest -q tests/test_simulation.py -k no_ready
```

The fixture's `plain_valid` signal is in
{download}`stream_dut.vhd <../../tests/hdl/stream_dut.vhd>`. On a stream
with data, bind `data` as usual and leave `ready=False`. There is no way to
stall the sender. Set `buffer_capacity` for the total number of undelivered
transfers you expect; overflow stops capture and requires `initialise()`.

# Vector and record transfers

Send a single vector, then a frame of VHDL records. The vector bus uses names
such as `plain_data`; the record bus binds each signal by name. The default
adapter accepts a dictionary for each record and reads the fields back as
logic values.

Both loopbacks use buses with no HDL drivers in
{download}`stream_dut.vhd <../../tests/hdl/stream_dut.vhd>`. The source and
sink share each bus, so a send needs a concurrent receive. If the DUT
processes the data, bind its input and output separately.

```{literalinclude} ../../examples/stream_loopback.py
:language: python
:lines: 8-
```

```console
uv run --locked pytest -q tests/test_simulation.py -k example
```

See [Signal binding](../binding.md) for naming options and
[IQ samples as a dataclass](custom-payload.md) for a record adapter.

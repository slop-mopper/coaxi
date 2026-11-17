# Getting started

## Installation

In a Python 3.13 or later testbench project managed by uv:

```console
uv add coaxi
```

cocotb is a runtime dependency. A simulator and cocotb's simulator integration
are also required to run a testbench. Run Python tools through the testbench's
`uv run` environment.

For development from a coaxi source checkout:

```console
uv sync --locked
```

To use that checkout in a separate testbench project:

```console
uv add /absolute/path/to/coaxi
```

## Connecting to a DUT

A source drives the DUT's input stream; a sink receives its output stream.
Bind each end separately. The testbench must own the signals its endpoints
drive: `data`, `valid`, and sidebands for a source, and `ready` for a sink.

```python
from coaxi import AxiStreamBus, AxiStreamSink, AxiStreamSource

input_bus = AxiStreamBus.bind(dut, prefix="s", last=True)
output_bus = AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True)
source = AxiStreamSource(input_bus, clock=dut.clk)
sink = AxiStreamSink(output_bus, clock=dut.clk)
await source.initialise()
await sink.initialise()
```

This example expects `s_tdata`, `s_tvalid`, `s_tready`, and `s_tlast` on the
input, and `m_data`, `m_valid`, `m_ready`, and `m_last` on the output.
The clock must already be running. Only start a cocotb clock if the testbench
owns that signal. The clock must contain literal `0` and `1` values from
before the first initialisation onwards; clock values are not monitored.

`initialise()` starts driving, clearing local state and owned outputs.
Reset the DUT separately when its state needs clearing.

Start sending and receiving concurrently when the DUT can apply backpressure:

```python
import cocotb
from coaxi import to_unsigned

sending = cocotb.start_soon(source.send_frame([10, 20, 30]))
frame = await sink.recv_frame(max_transfers=3)
await sending
assert [to_unsigned(beat.data) for beat in frame] == [10, 20, 30]
```

The assertion assumes vector payloads. In a complete test, use a bounded
simulation-time timeout, for example
`@cocotb.test(timeout_time=2000, timeout_unit="ns")`. An unterminated frame or
stalled peer can otherwise wait indefinitely, including when a frame-length
limit is set.

## Runnable loopback

The source checkout includes a test with an unframed vector stream and a
framed VHDL record stream. NVC must be installed and on `PATH`.
Run it in the checkout:

```console
uv run pytest -q tests/test_simulation.py -k example
```

The runner builds `tests/hdl/stream_dut.vhd` as VHDL-2008 and runs this test
in both cocotb inertial-write modes:

```{literalinclude} ../examples/stream_loopback.py
:language: python
:lines: 8-
```

These loopbacks connect source and sink directly on buses in the fixture.
For a real DUT, use separate input and output bindings as above.

After traffic has finished, `await source.close()` and `await sink.close()`
stop background work and clear owned outputs. See [Lifecycle and recovery](lifecycle.md)
before interrupting active operations or adding reset monitoring.

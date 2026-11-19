# Getting started

## Installation

In a Python 3.13 or later testbench project managed by uv:

```console
uv add coaxi
```

cocotb is a runtime dependency. A simulator and cocotb's simulator integration
are also required to run a testbench. Run Python tools through the testbench's
`uv run` environment.

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

```{warning}
Start the receive before waiting for the send to finish. A sink with `ready`
holds it low until a receive is pending. The DUT can accept a few input beats
before its output backs up. If that stalls the send, the test never reaches
the receive.
```

Start the send as a task, receive the output frame, then await the send:

```python
import cocotb
from coaxi import to_unsigned

sending = cocotb.start_soon(source.send_frame([10, 20, 30]))
frame = await sink.recv_frame(max_transfers=3)
await sending
assert [to_unsigned(beat.data) for beat in frame] == [10, 20, 30]
```

This assumes a DUT out of reset that forwards the vector frame unchanged.
Set a simulation-time timeout, for example
`@cocotb.test(timeout_time=2000, timeout_unit="ns")`. `max_transfers` limits
frame length; it cannot detect a stalled peer.

## Runnable loopback

[Vector and record transfers](examples/loopback.md) shows a full cocotb test
with one single transfer and one frame. The [Examples](examples/index.md)
section also covers custom payloads, pauses, and reset.

After traffic has finished, `await source.close()` and `await sink.close()`
stop background work and clear owned outputs. See [Lifecycle and recovery](lifecycle.md)
before interrupting active operations or adding reset monitoring.

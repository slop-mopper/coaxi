# Examples

The cocotb examples run in NVC from the coaxi checkout. Install NVC, put it
on `PATH`, and run `uv sync --locked` before using the commands on these
pages. Each test runs with both settings of `COCOTB_TRUST_INERTIAL_WRITES`.
The arithmetic example runs in Python without a simulator.

```{toctree}
:maxdepth: 1

loopback
custom-payload
backpressure
interleaved
no-ready
reset-recovery
arithmetic
```

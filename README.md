# README.md
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

# coaxi

AXI interface helpers for cocotb testbenches, written for Python 3.13.
This is a ground-up rewrite of `cocotbext-axi`, with AXI-Stream as the first
implementation goal. The first single-transfer API is under development;
AXI4, AXI4-Lite and higher-level frame helpers are not implemented yet.

The distribution and Python import name are both `coaxi`:

```python
from coaxi import AxiStreamBus, AxiStreamSource, AxiStreamSink
```

## Signal names

Defaults are optional conveniences. Every signal can be overridden independently
with an exact HDL name or an already-bound cocotb handle:

```python
# Standard defaults: samples_tdata, samples_tvalid, samples_tready.
bus = AxiStreamBus.bind(dut, prefix="samples")

# Keep the defaults except for ready.
bus = AxiStreamBus.bind(dut, prefix="samples", ready="consumer_accepts")

# Unrelated names, including an explicitly selected frame boundary.
bus = AxiStreamBus.bind(
	dut,
	data="iq_word_in",
	valid="sample_available",
	ready="consumer_accepts",
	last="end_of_packet",
)
source = AxiStreamSource(bus, clock="beat_clock")
```

Explicit names are used unchanged. Use `t_prefix=False` for generated names
such as `samples_valid`. Last is absent unless explicitly selected with
`last=True`, a name or a handle. This initial subset requires ready.

Payload access is separate from handshake logic. The default payload adapter
retains cocotb logic values and represents VHDL records as field mappings.
Applications can supply a `Payload[T]` adapter for their own types.

## Development

```text
uv sync --locked
uv run pytest -q
uv run pyrefly check
uv run ruff format --check .
uv run ruff check .
```

Simulation uses `nvc` and VHDL-2008. See [ARCHITECTURE.md](ARCHITECTURE.md) for the
components, timing model and current limitations, and [AGENTS.md](AGENTS.md) for
the development rules.

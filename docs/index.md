# coaxi

coaxi provides AXI4-Stream sources and sinks for cocotb testbenches.
It supports individual transfers, frames, optional sidebands, arbitrary signal
names, and structured HDL payloads.

Use [Getting started](getting-started.md) for installation and a runnable test.
The [API reference](api/index.md) lists constructors, operations, types, and errors.

The current implementation covers AXI4-Stream. AXI4 memory-mapped, AXI4-Lite,
and AXI5-Stream wake-up and parity extensions are not implemented.

```{toctree}
:caption: User guide
:maxdepth: 1

getting-started
binding
payloads
transfers
sidebands
lifecycle
```

```{toctree}
:caption: Reference
:maxdepth: 2

api/index
development
```

coaxi requires Python 3.13 or later and cocotb 2.1.0 or later.
The regression uses NVC on Linux; other simulator timing models have not been
validated. The project uses the CC0-1.0 licence.

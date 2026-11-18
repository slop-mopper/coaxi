# coaxi

AXI4-Stream helpers for cocotb testbenches, targeting Python 3.13 and later.
The distribution and import package are named `coaxi`.

```console
uv add coaxi
```

cocotb 2.1.0 or later is a runtime dependency. Running a testbench also needs
a simulator and cocotb's simulator integration.

## Documentation

[Getting started](https://slop-mopper.github.io/coaxi/getting-started.html),
[examples](https://slop-mopper.github.io/coaxi/examples/index.html), and
[API reference](https://slop-mopper.github.io/coaxi/api/index.html).
Sources are in [`docs/`](docs/).

The runnable [vector and VHDL-record example](examples/stream_loopback.py)
uses NVC. From a source checkout with NVC on `PATH`:

```console
uv sync --locked
uv run pytest -q tests/test_simulation.py -k example
```

## Scope

Sources and sinks support individual transfers and frames, optional AXI4-Stream
sidebands, optional `data` and `ready`, interleaved packet assembly, and monitored
reset pins with configurable polarity. Signal names can be unrelated; each
role accepts a name or a cocotb handle. Payload access is separate from handshake
and framing logic.

`Signed` and `Unsigned` provide immutable VHDL-2008 `numeric_std` values,
with VHDL-width arithmetic, explicit integer conversion, and cocotb `LogicArray`
interoperation. See [Numeric values](https://slop-mopper.github.io/coaxi/numeric.html).

AXI4 memory-mapped, AXI4-Lite, and AXI5-Stream extensions are not implemented.
Tests cover Python 3.13.5, cocotb 2.1.0, and NVC 1.21.1 on Linux.

Await `initialise()` before traffic and for explicit recovery from faults or
caller cancellation. With a reset pin, setup can finish while reset is
asserted. Release DUT reset before calling `wait_available()` to wait for
the endpoint to resume. Healthy pin-only resets recover automatically.
Clocks must contain literal `0` and `1` from before the first initialisation
onwards; endpoints do not monitor this precondition. See
[Lifecycle and recovery](https://slop-mopper.github.io/coaxi/lifecycle.html)
before interrupting traffic.

## Development

```console
uv sync --locked --group docs
uv run pytest -q
uv run pyrefly check
uv run ruff format --check .
uv run ruff check .
uv run --locked --group docs sphinx-build -M html docs docs/_build -n -W --keep-going
uv run --locked --group docs sphinx-build -M doctest docs docs/_build -n -W --keep-going
```

Simulation tests use NVC and VHDL-2008. The HTML output is
`docs/_build/html/index.html`. See
[Development](https://slop-mopper.github.io/coaxi/development.html) for
distribution, coverage, and reliability checks, [ARCHITECTURE.md](ARCHITECTURE.md)
for implementation decisions, and [AGENTS.md](AGENTS.md) for repository rules.

## Releases

Pushing a matching `v*` version tag starts production PyPI publishing after
validation and any configured environment approval. Manual runs support PyPI
and TestPyPI. [RELEASING.md](RELEASING.md) describes configuration and recovery.

## Licence

CC0-1.0. [LICENSE.txt](LICENSE.txt) contains the unmodified
[CC0 1.0 Universal legal code](https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt)
and is included in the source and wheel distributions.

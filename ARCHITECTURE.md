# ARCHITECTURE.md
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/CLIProxyAPI/gpt-6.1-sol

## Current state

The repository contains project guidance and development configuration. No
protocol implementation, Python package, HDL DUT, or tests have been added.

## Signal binding requirements

Signal binding is not implemented yet. Its implementation must separate protocol
roles from HDL signal names and allow every signal to be named independently.

Standard names such as `foo_tdata`, `foo_tvalid`, `foo_tready`, and `foo_tlast`
will have convenient defaults, along with the corresponding names without `t`.
These defaults must not limit explicit bindings. For example, one interface could
use `iq_word_in` for data, `sample_available` for valid, `consumer_accepts` for
ready, and `end_of_packet` for last.

A caller must be able to override one signal through a simple per-signal argument
or mapping while retaining the other defaults. Every signal must also accept an
already-bound cocotb handle. This applies to optional sidebands and any clock or
reset signals accepted by an API. No custom adapter or subclass may be required
to change names.

Explicit names must be used exactly as supplied, without case changes or added
prefixes or suffixes. They need not share a naming pattern or be valid Python
attribute names. Optional signals must remain optional regardless of the naming
defaults. Tests must cover arbitrary names, partial overrides, and direct handle
binding alongside both default naming styles.

## Development configuration

- `AGENTS.md` records the project requirements and working rules.
- `pyproject.toml` declares the project metadata, Python requirement, runtime
  dependencies, development tools, and Ruff settings.
- `uv.lock` records the resolved dependency versions and package hashes.
- `.python-version` selects Python 3.13 for `uv`.
- `.gitignore` excludes the local environment, Python bytecode, and tool caches.

Use `uv sync --locked` to create the project-local `.venv` with the dependency
versions recorded in `uv.lock`.
The runtime dependency is cocotb 2.1.0 or later. Pyrefly and Ruff are development
dependencies. Pyrefly uses its default configuration.

Ruff uses a 120-character line length, tab indentation, double quotes, and
docstring code formatting. Its lint configuration ignores `I001` and `BLE001`;
the supplied import-sorting settings remain available if import sorting is
enabled later. No additional lint rules are selected.

No build backend is configured because there is no Python package yet.

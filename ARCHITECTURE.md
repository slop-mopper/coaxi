# ARCHITECTURE.md
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/CLIProxyAPI/gpt-6.1-sol

## Current state

The repository contains project guidance and development configuration. No
protocol implementation, Python package, HDL DUT, or tests have been added.

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

# AGENTS.md
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

## Project purpose

`coaxi` is a ground-up rewrite of `cocotbext-axi`. It provides helpers for
interacting with AXI4, AXI4-Lite, and AXI-Stream interfaces in cocotb testbenches.
The project and distribution name is `coaxi`; the Python package is `coaxi`,
located at `src/coaxi`. Use imports such as `from coaxi import AxiStreamBus`.
Do not use the former `cocotbext.axi` namespace or add a compatibility package.

The first implementation should make AXI-Stream work well, with a small, clear
foundation that can later support AXI4 and AXI4-Lite. Do not implement the other
protocols ahead of that goal or build abstractions solely for hypothetical needs.

Do not depend on `cocotb-bus` or `cocotbext-bus`. Keep signal binding simple and
within this library.

## Decisions and clarification

Never assume the answer to an ambiguous project architecture choice or other
decision. If a decision is unclear, or it would otherwise be useful to consult
the user, always ask the user what to do and wait for their answer before
proceeding with that decision.

Explain the uncertainty briefly and, where useful, give the available options
and their trade-offs. Do not invent requirements or silently settle the choice.

## Interface requirements

### Signal names

- Do not require any HDL signal naming convention. Treat protocol roles such as
  data, valid, ready, and last independently of the signals' actual names.
- Provide convenient defaults for standard AXI-Stream names such as
  `foo_tvalid` and `foo_tready`, and for names such as `foo_valid` and `foo_ready`.
  Prefix and `t`-prefix options are conveniences only.
- Let callers override every signal independently with an arbitrary HDL name
  or an already-bound cocotb handle. This includes optional sidebands and any
  clock or reset signals accepted by an API.
- Make overrides straightforward through per-signal arguments or a mapping.
  Overriding one signal must not require restating the others, subclassing,
  writing an adapter, or renaming signals in the DUT.
- Use explicit names exactly as supplied. Do not add prefixes or suffixes,
  change case, or require a shared naming pattern. Accept HDL names supported
  by cocotb even when they are not valid Python attribute names.
- Keep optional-signal selection explicit; naming defaults must not require
  optional signals to exist.

### Data types

- Support ordinary `std_logic_vector` payloads and custom HDL data types.
- A VHDL record such as `IQ_t`, containing two `signed(15 downto 0)` fields,
  should be usable as naturally as a vector payload.
- Keep payload access and conversion separate from handshake and framing logic.
  Do not require every payload to be flattened into an integer or byte sequence.

### Transactions and framing

- Provide straightforward support for unframed streams without `tlast` and
  framed streams with `tlast`.
- Keep the value of `tlast` available for individual transfers, even when using
  higher-level frame helpers.
- Document which optional signals an operation needs. Do not silently assume
  that every interface has every AXI-Stream sideband signal.
- Full-rate transfers are critical: sustain one accepted transfer per rising
  clock edge with immediately consecutive calls when data and ready are
  available. Verify cycle spacing and recovery from backpressure in tests.

### Clocks

- Require every clock to contain only literal 0/1 values from before the first
  endpoint reset onwards. Weak L/H and unresolved clock values are unsupported.
- Document this as a caller precondition. The current endpoints do not monitor
  clocks for invalid values.

### Meta-values and reset

- Handle HDL meta-values such as `X` and `U` explicitly. Do not silently convert
  them into ordinary data values.
- Drive meta-values only for a clear, documented protocol or testing reason.
- Reset must restore the library's driven signals and internal state to defined
  values, clearing meta-values that the library introduced where appropriate.
- Make unsupported values or conversions produce clear errors.

### Logging

Use DEBUG-level logging where useful for observing transfers, framing, reset,
and other bus activity. Avoid unconditional printing and routine transaction
messages at higher log levels.

## Python and development tools

- Target Python 3.13 and use `uv` for dependency and environment management.
- Use a project-local, `uv`-managed `.venv` for Python work. Run tools through
  `uv run` rather than relying on a globally activated environment.
- Avoid system-wide package installation. If sandbox restrictions prevent
  environment creation, dependency installation, or tool execution, report the
  limitation rather than working around those restrictions.
- Use modern Python practices and keep the design straightforward.
- Use cocotb 2.1.0 or later. Keep it as a runtime dependency in `pyproject.toml`.
- Keep `uv.lock` consistent with changes to declared dependencies. Avoid
  unrelated dependency upgrades.
- Use Pyrefly for type checking with its default configuration. Do not add
  Pyrefly overrides unless requested.
- Use Ruff for formatting and linting. Follow the settings in `pyproject.toml`:
  a 120-character line length, tab indentation, double quotes, docstring code
  formatting, and the supplied lint and import-sorting rules.
- Run `uv run pyrefly check`, `uv run ruff format --check .`, and
  `uv run ruff check .`. Apply formatting with `uv run ruff format .`.
- Run `uv run pytest -q` for the Python and simulator tests. Add a regression
  test for each bug fix where practical.

## Public APIs and documentation

- Give every public function, method, class, and type a succinct, useful
  docstring or equivalent documentation.
- Give all public function and method parameters and return values type
  annotations. Annotate public attributes and other exposed types as appropriate.
- Choose self-describing parameter names. Still explain each parameter's meaning
  in the function documentation, including units, defaults, or constraints where
  relevant.
- Document behaviour that callers need to understand, especially reset,
  handshake timing, framing, payload conversion, and meta-value handling.

## Language and style

- Use British English in code, comments, documentation, and user-facing prose:
  for example, `initialise`, `serialise`, and `colour`.
- Preserve spelling required by existing APIs, protocol names, identifiers, and
  external tools.
- Write simple, direct English. Use technical terms when they have a precise,
  useful meaning; avoid unnecessary jargon.
- Avoid stock assistant phrasing, rhetorical contrasts such as “not X but Y”,
  and inflated claims.

## Source headers and licence

The project licence is CC0-1.0. Start every new first-party source file with:

```python
# <FILENAME>
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/<MODEL-NAME>
```

Replace `<FILENAME>` with the file's basename, without any directory components.
Replace `<MODEL-NAME>` with the exact name of the model creating the file, such
as `gpt-6.1-sol`. Use `openai/<MODEL-NAME>`, omitting routing or proxy components.
Do not use a generic assistant name or invent a model name.
Use the language's comment syntax where `#` is unsuitable, such as `--` for
VHDL, while retaining the same header text.

## HDL and simulation

- Use `nvc` as the simulator. It is installed in the development environment.
- Write any required HDL DUTs in VHDL-2008.
- Test default naming styles, arbitrary unrelated signal names, individual
  overrides mixed with defaults, and direct handle binding as signal binding
  is implemented.
- Test framed and unframed transfers, custom data types, meta-values, reset
  behaviour, and backpressure as the relevant features are implemented.
- Give simulation tests bounded simulation-time timeouts so stalled transfers
  fail instead of hanging indefinitely.
- Record the seeds used by randomised tests so failures can be reproduced.

## Architecture and commits

- Maintain `ARCHITECTURE.md` as an accurate description of the implemented
  architecture, including the main components, their responsibilities, and
  important design decisions.
- Before every commit, review the code changes against `ARCHITECTURE.md`.
  Update it whenever needed so that all architectural effects of those changes
  are reflected. Do not describe planned features as already implemented.
- Do not overwrite or revert unrelated changes, discard uncommitted work, or
  rewrite Git history without the user's explicit permission.
- Commit work in self-contained, appropriately sized chunks. Keep unrelated
  changes separate and use succinct, readable commit messages.
- Run the relevant tests, type checks, and formatting checks before committing.
  State which checks ran and report any that could not run, with the reason.

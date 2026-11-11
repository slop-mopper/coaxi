# test_typing.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check endpoint constructor inference with Pyrefly's default configuration."""

import sys
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("endpoint", ["AxiStreamSource", "AxiStreamSink"])
@pytest.mark.parametrize("scenario", ["default", "custom", "missing"])
def test_constructor_types(tmp_path: Path, endpoint: str, scenario: str) -> None:
	"""Check endpoint's scenario in a temporary source file below tmp_path."""
	statements = {
		"default": f"assert_type({endpoint}(bus, clock), {endpoint}[PayloadValue])",
		"custom": f"assert_type({endpoint}(bus, clock, payload=payload), {endpoint}[int])",
		"missing": f"{endpoint}[int](bus, clock)",
	}
	statement = statements[scenario]
	source = tmp_path / "constructor_case.py"
	source.write_text(
		"# constructor_case.py\n"
		"# SPDX-License-Identifier: CC0-1.0\n"
		"# This file was created by an AI model: openai/gpt-6.1-sol\n"
		"from typing import assert_type\n"
		f"from coaxi import {endpoint}, AxiStreamBus, Payload, PayloadValue, Signal\n"
		"def check(bus: AxiStreamBus, clock: Signal, payload: Payload[int]) -> None:\n"
		f"\t{statement}\n",
		encoding="utf-8",
	)
	# Use the checker installed alongside this uv-managed Python interpreter.
	checker = Path(sys.executable).with_name("pyrefly")
	# The temporary file is outside the project; use its unchanged project config
	# so the checker discovers the local environment and editable package.
	config = Path(__file__).resolve().parents[1] / "pyproject.toml"
	result = subprocess.run(
		[str(checker), "check", "--config", str(config), str(source)],
		capture_output=True,
		text=True,
		check=False,
	)
	output = result.stdout + result.stderr
	if scenario == "missing":
		assert result.returncode != 0, output
		assert statement in output, output
	else:
		assert result.returncode == 0, output

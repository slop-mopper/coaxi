# test_typing.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check constructor and frame-method types with Pyrefly's default configuration."""

import sys
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("endpoint", ["AxiStreamSource", "AxiStreamSink"])
@pytest.mark.parametrize("scenario", ["default", "custom", "missing"])
def test_constructor_types(tmp_path: Path, endpoint: str, scenario: str) -> None:
	"""Check endpoint's scenario in a temporary source file below tmp_path."""
	statements = {
		"default": f"assert_type({endpoint}(bus, clock), {endpoint}[PayloadValue | None])",
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
		timeout=60,
	)
	output = result.stdout + result.stderr
	if scenario == "missing":
		assert result.returncode != 0, output
		assert statement in output, output
	else:
		assert result.returncode == 0, output


@pytest.mark.parametrize("scenario", ["default", "custom", "wrong_input"])
def test_frame_types(tmp_path: Path, scenario: str) -> None:
	"""Preserve generic payload and transfer-list types through the frame APIs."""
	custom = scenario != "default"
	value_type = "int" if custom else "PayloadValue | None"
	adapter = ", payload=payload" if custom else ""
	samples = '["wrong"]' if scenario == "wrong_input" else "[1, 2]"
	source = tmp_path / "frame_typing_case.py"
	source.write_text(
		"# frame_typing_case.py\n"
		"# SPDX-License-Identifier: CC0-1.0\n"
		"# This file was created by an AI model: openai/gpt-6.1-sol\n"
		"from typing import assert_type\n"
		"from cocotb.types import Logic, LogicArray\n"
		"from coaxi import AxiStreamSource, AxiStreamSink, AxiStreamTransfer, AxiStreamBus, Payload, PayloadValue, AxiStreamSidebands\n"
		"async def check(bus: AxiStreamBus, payload: Payload[int]) -> None:\n"
		f"\tsource = AxiStreamSource(bus, 'clock'{adapter})\n"
		f"\tsink = AxiStreamSink(bus, 'clock'{adapter})\n"
		f"\tassert_type(await source.send_frame({samples}), None)\n"
		f"\tassert_type(await sink.recv_frame(), list[AxiStreamTransfer[{value_type}]])\n"
		f"\tassert_type(await sink.recv_frame(max_transfers=3), list[AxiStreamTransfer[{value_type}]])\n"
		f"\tassert_type(await source.send_frame({samples}, sidebands=[AxiStreamSidebands(user=3)]), None)\n"
		"\tassert_type((await sink.recv()).keep, Logic | LogicArray | None)\n"
		"\tassert_type((await sink.recv()).id, Logic | LogicArray | None)\n",
		encoding="utf-8",
	)
	checker = Path(sys.executable).with_name("pyrefly")
	config = Path(__file__).resolve().parents[1] / "pyproject.toml"
	result = subprocess.run(
		[str(checker), "check", "--config", str(config), str(source)],
		capture_output=True,
		text=True,
		check=False,
		timeout=60,
	)
	output = result.stdout + result.stderr
	if scenario == "wrong_input":
		assert result.returncode != 0 and "send_frame" in output, output
	else:
		assert result.returncode == 0, output

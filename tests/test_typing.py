# test_typing.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check public call signatures with Pyrefly's default configuration."""

import re
import sys
import subprocess
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]


def _check(source: Path) -> subprocess.CompletedProcess[str]:
	# Use the checker next to the uv-managed interpreter. Source files outside
	# the checkout need its config to discover the editable package.
	checker = Path(sys.executable).with_name("pyrefly")
	return subprocess.run(
		[str(checker), "check", "--config", str(_ROOT / "pyproject.toml"), str(source)],
		capture_output=True,
		text=True,
		check=False,
		timeout=60,
	)


@pytest.mark.parametrize("endpoint", ["AxiStreamSource", "AxiStreamSink"])
@pytest.mark.parametrize("scenario", ["default", "custom", "missing"])
def test_constructor_types(tmp_path: Path, endpoint: str, scenario: str) -> None:
	"""Check endpoint's scenario in a temporary source file below tmp_path."""
	statements = {
		"default": f"assert_type({endpoint}(bus, clock, reset=reset, reset_active_high=True), {endpoint}[PayloadValue | None])",
		"custom": f"assert_type({endpoint}(bus, clock, payload=payload, reset=reset, reset_active_high=False), {endpoint}[int])",
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
		"def check(bus: AxiStreamBus, clock: Signal, reset: Signal, payload: Payload[int]) -> None:\n"
		f"\t{statement}\n",
		encoding="utf-8",
	)
	result = _check(source)
	output = result.stdout + result.stderr
	if scenario == "missing":
		assert result.returncode != 0, output
		assert statement in output, output
	else:
		assert result.returncode == 0, output


@pytest.mark.parametrize("kind", ["Signed", "Unsigned"])
@pytest.mark.parametrize("valid", [True, False])
def test_numeric_width_signatures(tmp_path: Path, kind: str, valid: bool) -> None:
	"""Type check zero construction, integer conversion, and resize with either spelling."""
	lines = [
		"from typing import assert_type",
		"from cocotb.types import LogicArray",
		f"from coaxi import {kind}",
		"",
		f"def check(number: int, vector: LogicArray, value: {kind}) -> None:",
	]
	if valid:
		statements = [
			f"{kind}(vector)",
			f"{kind}(value)",
			f"{kind}(0, width=16)",
			f"{kind}(value=0, w=16)",
			f"{kind}.from_int(number, width=16)",
			f"{kind}.from_int(value=number, w=16)",
			"value.resize(16)",
			"value.resize(width=16)",
			"value.resize(w=16)",
		]
		statements = [f"assert_type({call}, {kind})" for call in statements]
	else:
		statements = [
			f"{kind}(0)",
			f"{kind}(1, width=16)",
			f"{kind}(False, w=16)",
			f"{kind}(number, w=16)",
			f"{kind}(vector, width=16)",
			f"{kind}(0, width=16, w=16)",
			f"{kind}.from_int(number)",
			f"{kind}.from_int(number, width=16, w=16)",
			f"{kind}.from_int(number, w=None)",
			"value.resize()",
			"value.resize(width=16, w=16)",
			"value.resize(16, w=16)",
		]
	source = tmp_path / "numeric_typing_case.py"
	source.write_text("\n".join([*lines, *(f"\t{statement}" for statement in statements)]) + "\n", encoding="utf-8")
	result = _check(source)
	output = result.stdout + result.stderr
	if valid:
		assert result.returncode == 0, output
	else:
		assert result.returncode == 1, output
		error_lines = [int(line) for line in re.findall(r"--> .*numeric_typing_case\.py:(\d+):\d+", output)]
		assert sorted(error_lines) == list(range(len(lines) + 1, len(lines) + len(statements) + 1)), output


def test_custom_payload_example_types(tmp_path: Path) -> None:
	"""Check inference and explicit IQ annotations with named clock and reset handles."""
	example = _ROOT / "examples" / "custom_payload.py"
	source = tmp_path / example.name
	checks = [
		"",
		"",
		"from typing import assert_type",
		"",
		"",
		"def check(bus: AxiStreamBus, clock: LogicObject, reset: LogicObject) -> None:",
		"\tadapter: Payload[IQ] = IQPayload(bus)",
	]
	for kind in ("Source", "Sink"):
		endpoint = f"AxiStream{kind}"
		args = "bus, clock=clock, reset=reset, reset_active_high=True, payload=IQPayload(bus)"
		checks.extend(
			[
				f"\t{kind.lower()} = {endpoint}({args})",
				f"\tassert_type({kind.lower()}, {endpoint}[IQ])",
				f"\ttyped_{kind.lower()}: {endpoint}[IQ] = {endpoint}[IQ]({args})",
				f"\tassert_type(typed_{kind.lower()}, {endpoint}[IQ])",
			]
		)
	source.write_text(example.read_text(encoding="utf-8") + "\n".join(checks) + "\n", encoding="utf-8")
	result = _check(source)
	assert result.returncode == 0, result.stdout + result.stderr


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
		"\tassert_type((await sink.recv()).id, Logic | LogicArray | None)\n"
		"\tassert_type(await source.initialise(), None)\n"
		"\tassert_type(await sink.initialise(), None)\n"
		"\tassert_type(await source.close(), None)\n"
		"\tassert_type(await sink.close(), None)\n",
		encoding="utf-8",
	)
	result = _check(source)
	output = result.stdout + result.stderr
	if scenario == "wrong_input":
		assert result.returncode != 0 and "send_frame" in output, output
	else:
		assert result.returncode == 0, output

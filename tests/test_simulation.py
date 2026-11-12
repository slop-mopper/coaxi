# test_simulation.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Run the VHDL-2008 regression with nvc and both cocotb write modes."""

from pathlib import Path
from xml.etree import ElementTree

import pytest
from cocotb_tools.runner import get_runner


@pytest.mark.parametrize("trust_inertial", ["0", "1"])
@pytest.mark.parametrize(
	"suite", ["regression", "full_rate", "frames", "handles", "sidebands", "omissions", "reset_pin", "example"]
)
def test_stream_simulation(tmp_path: Path, trust_inertial: str, suite: str, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Build in tmp_path, run suite with the selected write mode and require passing results."""
	# cocotb's runner merges os.environ over extra_env. Override inherited
	# values so parametrisation really exercises both modes in any environment.
	monkeypatch.setenv("COCOTB_TRUST_INERTIAL_WRITES", trust_inertial)
	monkeypatch.setenv("COCOTB_RESOLVE_X", "ZEROS")
	tests = Path(__file__).parent.resolve()
	test_module = {
		"regression": "stream_cases",
		"full_rate": "full_rate_cases",
		"frames": "frame_cases",
		"handles": "handle_cases",
		"sidebands": "sideband_cases",
		"omissions": "omission_cases",
		"reset_pin": "reset_pin_cases",
		"example": "stream_loopback",
	}[suite]
	test_dir = tests.parent / "examples" if suite == "example" else tests
	runner = get_runner("nvc")
	runner.build(
		sources=[tests / "hdl" / "stream_dut.vhd"],
		hdl_toplevel="stream_dut",
		build_args=["--std=2008"],
		build_dir=tmp_path / "sim_build",
	)
	runner.test(
		hdl_toplevel="stream_dut",
		test_module=test_module,
		test_dir=test_dir,
		build_dir=tmp_path / "sim_build",
		results_xml=str(tmp_path / "results.xml"),
	)
	results = ElementTree.parse(tmp_path / "results.xml").findall(".//testcase")
	assert results, "simulator produced no test cases"
	for result in results:
		for status in ("failure", "error", "skipped"):
			assert result.find(status) is None, ElementTree.tostring(result, encoding="unicode")

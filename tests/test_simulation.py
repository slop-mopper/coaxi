# test_simulation.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Run the VHDL-2008 regression with nvc and both cocotb write modes."""

from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner


@pytest.mark.parametrize("trust_inertial", ["0", "1"])
@pytest.mark.parametrize("suite", ["regression", "full_rate", "frames", "handles", "sidebands", "omissions", "example"])
def test_stream_simulation(tmp_path: Path, trust_inertial: str, suite: str) -> None:
	"""Build in tmp_path and run suite with the selected write mode."""
	tests = Path(__file__).parent.resolve()
	test_module = {
		"regression": "stream_cases",
		"full_rate": "full_rate_cases",
		"frames": "frame_cases",
		"handles": "handle_cases",
		"sidebands": "sideband_cases",
		"omissions": "omission_cases",
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
		extra_env={
			"COCOTB_TRUST_INERTIAL_WRITES": trust_inertial,
			"COCOTB_RESOLVE_X": "ZEROS",
		},
	)

# test_simulation.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Run the VHDL-2008 regression with nvc and both cocotb write modes."""

from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner


@pytest.mark.parametrize("trust_inertial", ["0", "1"])
def test_stream_simulation(tmp_path: Path, trust_inertial: str) -> None:
	"""Build in tmp_path and run all cases with the selected write mode."""
	tests = Path(__file__).parent.resolve()
	runner = get_runner("nvc")
	runner.build(
		sources=[tests / "hdl" / "stream_dut.vhd"],
		hdl_toplevel="stream_dut",
		build_args=["--std=2008"],
		build_dir=tmp_path / "sim_build",
	)
	runner.test(
		hdl_toplevel="stream_dut",
		test_module="stream_cases",
		test_dir=tests,
		build_dir=tmp_path / "sim_build",
		results_xml=str(tmp_path / "results.xml"),
		extra_env={
			"COCOTB_TRUST_INERTIAL_WRITES": trust_inertial,
			"COCOTB_RESOLVE_X": "ZEROS",
		},
	)

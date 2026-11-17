# test_numeric_simulation.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Run numeric port interoperation in both cocotb write modes and resolution settings."""

from pathlib import Path
from xml.etree import ElementTree

import pytest
from cocotb_tools.runner import get_runner


@pytest.mark.parametrize("trust_inertial", ["0", "1"])
@pytest.mark.parametrize("resolve_x", ["ZEROS", "ONES"])
def test_numeric_simulation(
	tmp_path: Path,
	trust_inertial: str,
	resolve_x: str,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Require a successful bounded cocotb test against the numeric_std port fixture."""
	monkeypatch.setenv("COCOTB_TRUST_INERTIAL_WRITES", trust_inertial)
	monkeypatch.setenv("COCOTB_RESOLVE_X", resolve_x)
	tests = Path(__file__).parent.resolve()
	runner = get_runner("nvc")
	runner.build(
		sources=[tests / "hdl" / "numeric_dut.vhd"],
		hdl_toplevel="numeric_dut",
		build_args=["--std=2008"],
		build_dir=tmp_path / "sim_build",
	)
	runner.test(
		hdl_toplevel="numeric_dut",
		test_module="numeric_cases",
		test_dir=tests,
		build_dir=tmp_path / "sim_build",
		results_xml=str(tmp_path / "results.xml"),
	)
	results = ElementTree.parse(tmp_path / "results.xml").findall(".//testcase")
	assert len(results) == 1 and results[0].attrib["name"] == "numeric_values"
	for status in ("failure", "error", "skipped"):
		assert results[0].find(status) is None, ElementTree.tostring(results[0], encoding="unicode")

# test_simulation.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Run the VHDL-2008 regression with nvc and both cocotb write modes."""

from sys import executable
from pathlib import Path
from subprocess import run
from xml.etree import ElementTree

import pytest
from cocotb_tools.runner import get_runner


_EXAMPLE_MODULES = {
	"example": "stream_loopback",
	"custom_payload": "custom_payload",
	"backpressure": "backpressure",
	"interleaved": "interleaved",
	"no_ready": "no_ready",
	"reset_recovery": "reset_recovery",
}


@pytest.mark.parametrize("trust_inertial", ["0", "1"])
@pytest.mark.parametrize(
	"suite",
	[
		"regression",
		"full_rate",
		"frames",
		"handles",
		"sidebands",
		"omissions",
		"reset_pin",
		"pause",
		"audit",
		"reliability",
		*_EXAMPLE_MODULES,
	],
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
		"pause": "pause_cases",
		"audit": "audit_cases",
		"reliability": "reliability_cases",
		**_EXAMPLE_MODULES,
	}[suite]
	examples = tests.parent / "examples"
	test_dir = examples if suite in _EXAMPLE_MODULES else tests
	hdl_source = examples / "iq_loopback.vhd" if suite == "custom_payload" else tests / "hdl" / "stream_dut.vhd"
	runner = get_runner("nvc")
	runner.build(
		sources=[hdl_source],
		hdl_toplevel=hdl_source.stem,
		build_args=["--std=2008"],
		build_dir=tmp_path / "sim_build",
	)
	runner.test(
		hdl_toplevel=hdl_source.stem,
		test_module=test_module,
		test_dir=test_dir,
		build_dir=tmp_path / "sim_build",
		results_xml=str(tmp_path / "results.xml"),
	)
	results = ElementTree.parse(tmp_path / "results.xml").findall(".//testcase")
	assert results, "simulator produced no test cases"
	if suite in _EXAMPLE_MODULES:
		assert [result.get("name") for result in results] == [test_module]
	for result in results:
		for status in ("failure", "error", "skipped"):
			assert result.find(status) is None, ElementTree.tostring(result, encoding="unicode")


@pytest.mark.parametrize("stall_period", ["0", "4"])
def test_benchmark_drive_phase(stall_period: str) -> None:
	"""Audit frame loop timing with and without stalls in both write modes."""
	bench = Path(__file__).with_name("bench_stream.py")
	result = run(
		[
			executable,
			str(bench),
			"--implementation",
			"coaxi",
			"falling-loop",
			"rising-loop",
			"--beats",
			"64",
			"--frame-size",
			"1",
			"8",
			"--trust-inertial",
			"0",
			"1",
			"--stall-period",
			stall_period,
			"--repeat",
			"1",
			"--check-drive-phase",
		],
		check=False,
		capture_output=True,
		text=True,
		timeout=60,
	)
	assert result.returncode == 0, result.stdout + result.stderr
	assert result.stdout.count("drive phase checked") == 12, result.stdout

# reliability_worker.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Isolated simulator worker for run_reliability.py; not a standalone public tool."""

import os
import sys
import json
import hashlib
from pathlib import Path

from cocotb_tools.runner import get_runner


def main() -> None:
	"""Run one copied source variant and write complete XML even for assertion failures."""
	root = Path(sys.argv[1]).resolve()
	mode = sys.argv[2]
	sys.path[:0] = [str(root / "src"), str(root / "tests")]
	import coaxi

	package = root / "src" / "coaxi"
	assert Path(coaxi.__file__).resolve().parent == package, "HARNESS: worker imported wrong package"
	environment = {
		"COCOTB_TRUST_INERTIAL_WRITES": mode,
		"COCOTB_RESOLVE_X": "ZEROS",
		"COCOTB_USER_COVERAGE": "0",
		"COCOTB_MAX_FAILURES": "0",
		"COAXI_STRESS_SEEDS": "73",
		"COAXI_STRESS_ROUNDS": "24",
		"COAXI_EXPECT_PACKAGE": str(package),
		"COAXI_EXPECT_MANIFEST": json.dumps(
			{path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in package.glob("*.py")}
		),
	}
	for key in (
		"PYTEST_CURRENT_TEST",
		"PYTHONOPTIMIZE",
		"COCOTB_TEST_FILTER",
		"COCOTB_TESTCASE",
		"COCOTB_RANDOM_SEED",
		"RANDOM_SEED",
		"COCOTB_TEST_MODULES",
		"COCOTB_COVERAGE",
		"COVERAGE_PROCESS_START",
		"COAXI_EXPECT_PACKAGE",
	):
		os.environ.pop(key, None)
	os.environ.update(environment)
	build = root / f"build-{mode}"
	runner = get_runner("nvc")
	runner.build(
		sources=[root / "tests" / "hdl" / "stream_dut.vhd"],
		hdl_toplevel="stream_dut",
		build_args=["--std=2008"],
		build_dir=build,
		always=True,
	)
	runner.test(
		hdl_toplevel="stream_dut",
		hdl_toplevel_lang="vhdl",
		test_module="reliability_cases",
		test_dir=root / "tests",
		build_dir=build,
		results_xml=root / f"results-{mode}.xml",
		extra_env=environment,
	)


if __name__ == "__main__":
	main()

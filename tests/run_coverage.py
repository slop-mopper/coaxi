# run_coverage.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Collect checkout Python branch coverage in pytest and NVC; run with uv run."""

import os
import sys
import subprocess
from pathlib import Path


def main() -> None:
	"""Run the full suite with per-process data, then combine and report it.

	Measure only coaxi, including Python embedded in NVC via cocotb's native
	coverage hook. The runtime-only distribution smoke test deliberately does
	not install Coverage.py; it independently checks the built wheel.
	Write .coverage*, coverage.json and htmlcov/ in the project root.
	No percentage gate is imposed: inspect missing paths and their assertions.
	"""
	root = Path(__file__).resolve().parents[1]
	environment = os.environ.copy()
	environment["COCOTB_USER_COVERAGE"] = "1"
	environment["COVERAGE_RCFILE"] = str(root / "pyproject.toml")
	environment["COVERAGE_FILE"] = str(root / ".coverage")
	for arguments in (
		["erase"],
		["run", "-m", "pytest", "-q"],
		["combine"],
		["report"],
		["json", "-o", "coverage.json"],
		["html", "-d", "htmlcov"],
	):
		subprocess.run(
			[sys.executable, "-m", "coverage", *arguments],
			cwd=root,
			env=environment,
			check=True,
			timeout=300,
		)


if __name__ == "__main__":
	main()

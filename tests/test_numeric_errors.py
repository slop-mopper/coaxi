# test_numeric_errors.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check package error paths independently, without stopping the successful-value oracle."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from cocotb.types import Logic, LogicArray

from coaxi import Signed, Unsigned
from tests.test_numeric_vhdl import _HEADER


@pytest.mark.parametrize(
	("expression", "evaluate", "exception", "diagnostic"),
	[
		(
			'si("1") / si("0")',
			lambda: Signed(LogicArray("1")) / Signed(LogicArray("0")),
			ZeroDivisionError,
			"division by zero",
		),
		(
			'us("1") mod us("0")',
			lambda: Unsigned(LogicArray("1")) % Unsigned(LogicArray("0")),
			ZeroDivisionError,
			"division by zero",
		),
		(
			'si("1") rem si("0")',
			lambda: Signed(LogicArray("1")).rem(Signed(LogicArray("0"))),
			ZeroDivisionError,
			"division by zero",
		),
		('us("10") and us("1")', lambda: Unsigned(LogicArray("10")) & Unsigned(LogicArray("1")), ValueError, "length"),
		(
			'si("-1") ?< si("01")',
			lambda: Signed(LogicArray("-1")).match_lt(Signed(LogicArray("01"))),
			ValueError,
			"found",
		),
		("si(\"\") + std_logic'('1')", lambda: Signed(LogicArray("")) + Logic("1"), ValueError, "0"),
		('7 rem us("1")', lambda: Unsigned(LogicArray("1")).rrem(7), ValueError, "length"),
		('7 rem us("0")', lambda: Unsigned(LogicArray("0")).rrem(7), ZeroDivisionError, "by zero"),
		('1 rem us("")', lambda: Unsigned(LogicArray("")).rrem(1), ValueError, "length"),
	],
)
def test_numeric_package_errors(
	tmp_path: Path,
	expression: str,
	evaluate: Callable[[], object],
	exception: type[Exception],
	diagnostic: str,
) -> None:
	"""Require both a Python exception and the corresponding simulator diagnostic."""
	with pytest.raises(exception):
		evaluate()
	source = tmp_path / "numeric_error.vhd"
	source.write_text(
		_HEADER + f'\n    emit(0, {expression});\n    report "UNEXPECTED_SUCCESS"; wait;\n  end process;\nend;\n',
		encoding="utf-8",
	)
	analysis = subprocess.run(
		["nvc", "--std=2008", "-a", str(source), "-e", "numeric_oracle"],
		cwd=tmp_path,
		capture_output=True,
		text=True,
		timeout=30,
		check=False,
	)
	# Constant folding is permitted to report the package error during analysis.
	if analysis.returncode:
		output = analysis.stdout + analysis.stderr
	else:
		simulation = subprocess.run(
			["nvc", "--std=2008", "-r", "numeric_oracle", "--exit-severity=error", "--stop-time=1ns"],
			cwd=tmp_path,
			capture_output=True,
			text=True,
			timeout=30,
			check=False,
		)
		assert simulation.returncode != 0
		output = simulation.stdout + simulation.stderr
	if exception is ZeroDivisionError:
		diagnostic = "by zero"  # The package names all three operators in this diagnostic.
	assert diagnostic in output.lower(), output
	assert "UNEXPECTED_SUCCESS" not in output

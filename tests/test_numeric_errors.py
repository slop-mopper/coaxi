# test_numeric_errors.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check package error paths independently, without stopping the successful-value oracle."""

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from cocotb.types import Logic, LogicArray

from coaxi import Signed, Unsigned
from tests.test_numeric_vhdl import _HEADER


def _require_diagnostic(output: str, pattern: str) -> None:
	"""Reject unrelated compiler/runtime failures even if they contain a broad keyword."""
	assert re.search(pattern, output, re.IGNORECASE), output
	assert "numeric_std-body.vhdl" in output or "std_logic_1164-body.vhdl" in output, output
	assert "UNEXPECTED_SUCCESS" not in output, output


@pytest.mark.parametrize("intrinsics", ["0", "1"])
@pytest.mark.parametrize(
	("expression", "evaluate", "exception", "diagnostic"),
	[
		(
			'si("1") / si("0")',
			lambda: Signed(LogicArray("1")) / Signed(LogicArray("0")),
			ZeroDivisionError,
			r"NUMERIC_STD\.DIVMOD: DIV, MOD, or REM by zero",
		),
		(
			'us("1") mod us("0")',
			lambda: Unsigned(LogicArray("1")) % Unsigned(LogicArray("0")),
			ZeroDivisionError,
			r"NUMERIC_STD\.DIVMOD: DIV, MOD, or REM by zero",
		),
		(
			'si("1") rem si("0")',
			lambda: Signed(LogicArray("1")).rem(Signed(LogicArray("0"))),
			ZeroDivisionError,
			r"NUMERIC_STD\.DIVMOD: DIV, MOD, or REM by zero",
		),
		(
			'us("10") and us("1")',
			lambda: Unsigned(LogicArray("10")) & Unsigned(LogicArray("1")),
			ValueError,
			r'STD_LOGIC_1164\."and": arguments.*not of the same length',
		),
		(
			'si("-1") ?< si("01")',
			lambda: Signed(LogicArray("-1")).match_lt(Signed(LogicArray("01"))),
			ValueError,
			r"""NUMERIC_STD\."\?<": '-' found in compare string""",
		),
		(
			"si(\"\") + std_logic'('1')",
			lambda: Signed(LogicArray("")) + Logic("1"),
			ValueError,
			r"index 0 outside of NATURAL range -1 downto 0",
		),
		(
			'7 rem us("1")',
			lambda: Unsigned(LogicArray("1")).rrem(7),
			ValueError,
			r"value length 1 does not match variable XREM length 3",
		),
		(
			'7 rem us("0")',
			lambda: Unsigned(LogicArray("0")).rrem(7),
			ZeroDivisionError,
			r"NUMERIC_STD\.DIVMOD: DIV, MOD, or REM by zero",
		),
		(
			'1 rem us("")',
			lambda: Unsigned(LogicArray("")).rrem(1),
			ValueError,
			r"value length 0 does not match variable XREM length 1",
		),
	],
)
def test_numeric_package_errors(
	tmp_path: Path,
	expression: str,
	evaluate: Callable[[], object],
	exception: type[Exception],
	diagnostic: str,
	intrinsics: str,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Require successful compilation followed by the intended runtime package diagnostic."""
	monkeypatch.setenv("NVC_JIT_INTRINSICS", intrinsics)
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
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		timeout=30,
		check=False,
	)
	assert analysis.returncode == 0, analysis.stdout
	simulation = subprocess.run(
		["nvc", "--std=2008", "-r", "numeric_oracle", "--exit-severity=error", "--stop-time=1ns"],
		cwd=tmp_path,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		timeout=30,
		check=False,
	)
	assert simulation.returncode != 0
	_require_diagnostic(simulation.stdout, diagnostic)

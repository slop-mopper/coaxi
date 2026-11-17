# test_numeric_hardening.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check oracle safeguards and independent conversion/range contracts."""

import os
import sys
import subprocess
from pathlib import Path

import pytest
from cocotb.types import LogicArray, Range

from coaxi import Signed, Unsigned
from tests.test_numeric_vhdl import _evaluate, _parse_results
from tests.test_numeric_errors import _require_diagnostic


@pytest.mark.parametrize("kind", [Signed, Unsigned])
def test_small_arithmetic_matrix(kind: type[Signed] | type[Unsigned]) -> None:
	"""Exhaust small mixed widths against Python mathematics and explicit modulo encoding."""
	for left_width in range(1, 6):
		for right_width in range(1, 6):
			left_min = -(1 << (left_width - 1)) if kind is Signed else 0
			right_min = -(1 << (right_width - 1)) if kind is Signed else 0
			for a in range(left_min, left_min + (1 << left_width)):
				left = kind(LogicArray(format(a % (1 << left_width), f"0{left_width}b")))
				for b in range(right_min, right_min + (1 << right_width)):
					right = kind(LogicArray(format(b % (1 << right_width), f"0{right_width}b")))
					cases = [
						(left + right, a + b, max(left_width, right_width)),
						(left - right, a - b, max(left_width, right_width)),
						(left * right, a * b, left_width + right_width),
					]
					if b:
						quotient = abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)
						cases.extend(
							[
								(left / right, quotient, left_width),
								(left.rem(right), a - quotient * b, right_width),
								(left % right, a % b, right_width),
							]
						)
					for value, mathematical, width in cases:
						assert value.width == width, (a, b, left_width, right_width)
						assert str(value) == format(mathematical % (1 << width), f"0{width}b"), (
							a,
							b,
							left_width,
							right_width,
							mathematical,
						)
					assert (left == right) == (a == b)
					assert (left != right) == (a != b)
					assert (left < right) == (a < b)
					assert (left <= right) == (a <= b)
					assert (left > right) == (a > b)
					assert (left >= right) == (a >= b)


def test_unsigned_shift() -> None:
	"""Unsigned right shifts fill with zero even when the leftmost bit is one."""
	value = Unsigned(LogicArray("1001"))
	assert str(value >> 1) == "0100"


def test_valid_oracle_arithmetic() -> None:
	"""A valid arithmetic expression must yield its result instead of disappearing."""
	left = Unsigned(LogicArray("0011"))
	right = Unsigned(LogicArray("0001"))
	assert _evaluate("us(0011) + us(0001)", lambda: left + right, None) == ("0100|3|false|0", False)


@pytest.mark.parametrize("output", ["syntax error at 0", "fatal: array length", "division by zero", "found 0"])
def test_error_oracle_rejects_unrelated_failure(output: str) -> None:
	"""A compiler failure or broad substring is not the intended package diagnostic."""
	with pytest.raises(AssertionError):
		_require_diagnostic(output, r"index 0 outside of NATURAL range -1 downto 0")


@pytest.mark.parametrize("exception", [OverflowError, ZeroDivisionError, ValueError])
def test_oracle_cannot_drop_valid_case(exception: type[Exception]) -> None:
	"""An unexpected exception must fail a successful oracle case, not omit it."""

	def broken() -> bool:
		raise exception("array length mismatch")

	with pytest.raises(AssertionError, match="valid oracle case raised") as caught:
		_evaluate("known-valid operation", broken, None)
	assert isinstance(caught.value.__cause__, exception)


@pytest.mark.parametrize(
	"output",
	[
		"START|0\nRESULT|0|true\n",  # Missing end marker.
		"START|0\nRESULT|0|true\nRESULT|0|false\nDONE",
		"START|0\nRESULT|1|true\nDONE",
		"START|0\nSTART|1\nRESULT|1|true\nDONE",
		"RESULT|0|true\nDONE",
		"START|0\nRESULT|0|true\nDONE\nDONE",
		"START|0\nRESULT|0|true\nDONE\nwarning: NUMERIC_STD unexpected",
		"START|0\nRESULT|0|true\nNOT_DONE",
		"unrelated START|0\nRESULT|0|true\nDONE",
		"START|0\nRESULT|0|true\n** Error: NUMERIC_STD unexpected\nDONE",
		"START|0\n** Failure: NUMERIC_STD unexpected\nRESULT|0|true\nDONE",
		"START|0\nRESULT|0|true\nDONE\n** Fatal: unrelated",
	],
)
def test_oracle_rejects_bad_transcript(output: str) -> None:
	"""Missing, duplicate, misattributed, and late diagnostics must fail."""
	with pytest.raises(AssertionError):
		_parse_results(output, 1)


def test_oracle_warning_attribution() -> None:
	"""A warning belongs only to its active START/RESULT pair."""
	output = "START|0\nwarning: NUMERIC_STD metavalue\nRESULT|0|false\nSTART|1\nRESULT|1|true\nDONE"
	assert _parse_results(output, 2) == {0: ("false", True), 1: ("true", False)}


@pytest.mark.parametrize("kind", [Signed, Unsigned])
def test_distinct_null_concatenation(kind: type[Signed] | type[Unsigned]) -> None:
	"""The complete right operand range controls concatenation of two null arrays."""
	left = kind(LogicArray("", Range(7, "to", 6)))
	right = kind(LogicArray("", Range(2, "downto", 3)))
	assert left.concat(right).width == right.concat(left).width == 0

	# cocotb Range equality compares sequences: every null range compares equal.
	def bounds(value: Signed | Unsigned) -> tuple[int, str, int]:
		return value.range.left, value.range.direction, value.range.right

	assert bounds(left.concat(right)) == (2, "downto", 3)
	assert bounds(right.concat(left)) == (7, "to", 6)
	assert bounds(left[:]) == (7, "to", 6)


@pytest.mark.parametrize("kind", [Signed, Unsigned])
def test_large_integer_bit_patterns(kind: type[Signed] | type[Unsigned]) -> None:
	"""Check conversions against independent bit strings instead of round trips."""
	width = 521
	for number in [0, 1, (1 << 519) + 37, *((-1, -(1 << 520)) if kind is Signed else ((1 << 521) - 1,))]:
		expected = format(number % (1 << width), f"0{width}b")
		assert str(kind.from_int(number, width=width)) == expected
		assert kind(LogicArray(expected)).to_int() == number


@pytest.mark.parametrize("setting", ["ZEROS", "ONES", "RANDOM", "error"])
def test_resolver_before_import(setting: str) -> None:
	"""Set cocotb's resolver before import in a new interpreter."""
	environment = os.environ.copy()
	environment["COCOTB_RESOLVE_X"] = setting
	environment.pop("PYTHONOPTIMIZE", None)
	program = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import coaxi
from coaxi import Signed, Unsigned
from cocotb.types import LogicArray
assert Path(coaxi.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
setting = sys.argv[2]
array = LogicArray("XX")
if setting == "error":
    try:
        array.to_unsigned()
    except ValueError:
        pass
    else:
        raise AssertionError("control resolver should reject X")
else:
    control = array.to_unsigned()
    assert control == {"ZEROS": 0, "ONES": 3}.get(setting, control)
    assert 0 <= control <= 3
for kind, weak_number in [(Signed, -7), (Unsigned, 9)]:
    assert int(kind(LogicArray("HLLH"))) == weak_number
    for text in ("X", "U", "Z", "W", "-", "01XH"):
        value = kind(LogicArray(text))
        for convert in (int, lambda x: x.to_int()):
            try:
                convert(value)
            except ValueError:
                pass
            else:
                raise AssertionError(f"{kind.__name__} resolved {text} with {setting}")
print("resolver checks passed")
"""
	result = subprocess.run(
		[sys.executable, "-I", "-B", "-c", program, str(Path(__file__).resolve().parents[1] / "src"), setting],
		env=environment,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		timeout=30,
		check=False,
	)
	assert result.returncode == 0 and "resolver checks passed" in result.stdout, result.stdout

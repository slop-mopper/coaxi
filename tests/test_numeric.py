# test_numeric.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check Python contracts, conversions, diagnostics, and VHDL sizing examples."""

import operator
import warnings
from typing import Any, cast

import pytest
from cocotb.types import Logic, LogicArray, Range

from coaxi import NumericStdWarning, Signed, Unsigned


@pytest.mark.parametrize("kind", [Signed, Unsigned])
def test_copy_ranges_and_immutability(kind: type[Signed] | type[Unsigned]) -> None:
	"""Constructors and exports copy bits and ranges, including ascending/null arrays."""
	for bounds, text in [(Range(11, "downto", 8), "10UH"), (Range(3, "to", 6), "10UH"), (Range(4, "to", 3), "")]:
		array = LogicArray(text, bounds)
		value = kind(array)
		assert str(value) == text
		assert value.range.left == bounds.left and value.range.right == bounds.right
		assert value.range.direction == bounds.direction
		assert len(value) == value.width == len(text)
		assert list(value) == list(array)
		assert repr(value).startswith(kind.__name__ + "(LogicArray(")
		assert str(value[:]) == text
		exported = value.to_logic_array()
		if text:
			array[bounds.left] = "0"
			exported[bounds.left] = "0"
			assert str(value) == text
			assert value[bounds.left] == Logic(text[0])
			part = value[bounds.left : bounds.left + (1 if bounds.direction == "to" else -1)]
			assert isinstance(part, kind) and str(part) == text[:2]
			with pytest.raises((IndexError, ValueError)):
				_ = value[bounds.right : bounds.left]
		with pytest.raises(AttributeError):
			cast(Any, value).width = 42
		with pytest.raises(AttributeError):
			del value._text
		with pytest.raises(TypeError):
			bool(value)
		with pytest.raises(TypeError):
			operator.index(value)
		with pytest.raises(TypeError):
			hash(value)
		with pytest.raises(TypeError):
			kind(cast(Any, 7))
		with pytest.raises(AttributeError):
			value.__init__(LogicArray(text, bounds))


@pytest.mark.parametrize("kind", [Signed, Unsigned])
def test_index_domain(kind: type[Signed] | type[Unsigned]) -> None:
	"""numeric_std indices are natural; negative bounds are allowed only for null arrays."""
	with pytest.raises(ValueError, match="non-negative indices"):
		kind(LogicArray("01", Range(-2, "to", -1)))
	null = kind(LogicArray("", Range(-1, "downto", 0)))
	assert null.width == 0 and null.range.left == -1


def test_reinterpretation() -> None:
	"""Constructor conversions change signedness without changing any bits."""
	u = Unsigned.from_int(255, width=8)
	s = Signed(u)
	assert int(s) == -1
	assert int(Unsigned(s)) == 255
	assert int(s.as_unsigned()) == 255
	assert int(u.as_signed()) == -1
	x = Unsigned(LogicArray("HUZX", Range(7, "to", 10)))
	assert str(Signed(x)) == "HUZX"
	assert Signed(x).range == x.range


@pytest.mark.parametrize("kind", [Signed, Unsigned])
def test_integer_checks(kind: type[Signed] | type[Unsigned]) -> None:
	"""Positive widths are checked, while zero width follows VHDL's early null return."""
	for width in [1, 2, 7, 64, 257]:
		lower = -(1 << (width - 1)) if kind is Signed else 0
		upper = (1 << (width - (kind is Signed))) - 1
		for number in [lower, upper, 0]:
			assert int(kind.from_int(number, width=width)) == number
		with pytest.raises(OverflowError):
			kind.from_int(upper + 1, width=width)
		with pytest.raises((OverflowError, ValueError)):
			kind.from_int(lower - 1, width=width)
	for number in [0, 1, -1, 1 << 500] if kind is Signed else [0, 1, 1 << 500]:
		null = kind.from_int(number, width=0)
		assert str(null) == "" and null.range.left == 0 and null.range.right == 1
		with pytest.warns(NumericStdWarning, match="null"):
			assert int(null) == 0
	with pytest.raises(ValueError):
		kind.from_int(0, width=-1)
	with pytest.raises(TypeError):
		kind.from_int(cast(Any, 1.0), width=8)
	with pytest.raises(TypeError):
		kind.from_int(1, width=cast(Any, 8.0))


@pytest.mark.parametrize("kind", [Signed, Unsigned])
@pytest.mark.parametrize("boolean", [False, True])
def test_boolean_integer_values(kind: type[Signed] | type[Unsigned], boolean: bool) -> None:
	"""Boolean values mean zero or one, with the same signed range and null rules as integers."""
	number = int(boolean)
	for width in (1, 2, 8, 257):
		if kind is Signed and boolean and width == 1:
			with pytest.raises(OverflowError):
				kind.from_int(boolean, width=width)
		else:
			value = kind.from_int(boolean, width=width)
			assert str(value) == "0" * (width - 1) + str(number)
			assert value.to_int() == number
			assert type(value.to_int()) is int
	null = kind.from_int(boolean, width=0)
	assert str(null) == "" and null.width == 0
	assert (null.range.left, null.range.direction, null.range.right) == (0, "downto", 1)


@pytest.mark.parametrize("kind", [Signed, Unsigned])
@pytest.mark.parametrize("boolean", [False, True])
def test_boolean_numeric_operands(kind: type[Signed] | type[Unsigned], boolean: bool) -> None:
	"""Value validation continues to accept booleans in existing integer overloads."""
	value = kind.from_int(3, width=4)
	number = int(boolean)
	for operation in [operator.add, operator.sub, operator.mul, operator.truediv, operator.mod]:
		for left, right in [(value, boolean), (boolean, value)]:
			if not boolean and right is boolean and operation in (operator.truediv, operator.mod):
				with pytest.raises(ZeroDivisionError):
					operation(left, right)
			else:
				actual = operation(left, right)
				expected = operation(value, number) if right is boolean else operation(number, value)
				assert str(actual) == str(expected)
				assert actual.width == expected.width
	assert str(value.rrem(boolean)) == ("0001" if boolean else "0000")
	if boolean:
		assert str(value.rem(boolean)) == "0000"
	else:
		with pytest.raises(ZeroDivisionError):
			value.rem(boolean)
	assert (value == boolean) == (value == number)
	assert str(value.match_eq(boolean)) == str(value.match_eq(number))


@pytest.mark.parametrize("kind", [Signed, Unsigned])
@pytest.mark.parametrize("boolean", [False, True])
def test_boolean_sizes_and_counts(kind: type[Signed] | type[Unsigned], boolean: bool) -> None:
	"""Widths and movement counts reject bool, including null inputs and scalar-shift operators."""
	for number in (0, 1, boolean):
		with pytest.raises(TypeError, match="bool"):
			kind.from_int(number, width=boolean)
	for text in ("", "1", "HUX1"):
		value = kind(LogicArray(text))
		for operation in [
			value.resize,
			value.shift_left,
			value.shift_right,
			value.rotate_left,
			value.rotate_right,
			value.sll,
			value.srl,
			value.sla,
			value.sra,
			value.rol,
			value.ror,
			value.__lshift__,
			value.__rshift__,
		]:
			with pytest.raises(TypeError, match="bool"):
				operation(boolean)


def test_sizes_and_overflow() -> None:
	"""Arithmetic wraps at VHDL widths; checked input conversions never truncate."""
	u = Unsigned.from_int(255, width=8)
	assert int(u + 1) == 0
	assert int(1 + u) == 0
	assert int(u * 2) == 510 and (u * 2).width == 16
	assert int(1 - u) == 2
	assert (u + Unsigned.from_int(1, width=9)).width == 9
	assert int(u.resize(9) + 1) == 256
	for operation in [operator.add, operator.sub, operator.mul]:
		with pytest.raises(OverflowError):
			operation(u, 256)
		with pytest.raises(OverflowError):
			operation(256, u)
	s = Signed.from_int(127, width=8)
	assert int(s + 1) == -128
	assert int(-Signed.from_int(-128, width=8)) == -128
	assert int(abs(Signed.from_int(-128, width=8))) == -128
	assert int(s.resize(4)) == 7
	assert str(s[3:0]) == "1111"
	with pytest.raises(TypeError):
		operator.add(s, u)
	with pytest.raises(TypeError):
		operator.floordiv(s, 2)
	with pytest.raises(TypeError):
		operator.pow(s, 2)


def test_unsupported_operands() -> None:
	"""Mixed signedness and nonnumeric comparisons/concatenation require explicit conversion."""
	value = Signed.from_int(-1, width=8)
	for other in [Unsigned.from_int(1, width=8), LogicArray("00000001"), None, 1.0]:
		for compare in [operator.eq, operator.ne, operator.lt]:
			with pytest.raises(TypeError):
				compare(value, other)
		with pytest.raises(TypeError):
			value.concat(cast(Any, other))


def test_division_and_scalar_quirks() -> None:
	"""Division, rem, and mod have independent signs and operation-specific scalar paths."""
	a, b = Signed.from_int(-7, width=8), Signed.from_int(3, width=4)
	assert int(a / b) == -2 and (a / b).width == 8
	assert int(a.rem(b)) == -1 and a.rem(b).width == 4
	assert int(a.mod(b)) == int(a % b) == 2
	assert int(a / 3) == -2 and int(a.rem(3)) == -1 and int(a % 3) == 2
	assert int(7 / b) == 2 and int(b.rrem(-7)) == -1 and int(-7 % b) == 2
	minimum = Signed.from_int(-8, width=4)
	assert int(minimum / 8) == 0
	assert int(minimum / Signed.from_int(8, width=5)) == -1
	with pytest.warns(NumericStdWarning, match="truncated"):
		assert int(25 / Signed.from_int(1, width=4)) == 1
	with pytest.warns(NumericStdWarning, match="truncated"):
		assert int(Signed.from_int(7, width=4) % -129) == -2
	assert int(Signed(LogicArray("H011")) % Signed.from_int(3, width=4)) == 2
	assert int(Signed(LogicArray("1011")) % Signed.from_int(3, width=4)) == 1
	for function in [operator.truediv, operator.mod, lambda x, y: x.rem(y)]:
		with pytest.raises(ZeroDivisionError):
			function(a, 0)


@pytest.mark.parametrize("setting", ["ZEROS", "ONES", "RANDOM", "error"])
def test_meta_values(setting: str, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Numeric operations and explicit conversion ignore cocotb's resolution environment."""
	monkeypatch.setenv("COCOTB_RESOLVE_X", setting)
	x = Signed(LogicArray("U01X"))
	with pytest.raises(ValueError, match="unresolved"):
		int(x)
	for result in [x + 0, x - 0, x * 0, -x, abs(x), operator.truediv(x, 0), operator.mod(x, 0)]:
		assert set(str(result)) == {"X"}
	assert int(Signed(LogicArray("HLLH"))) == -7
	assert str(x & Logic("0")) == "0000"
	assert str(Logic("1") | x) == "1111"
	with pytest.warns(NumericStdWarning, match="metavalue"):
		assert operator.eq(x, x) is False
	with pytest.warns(NumericStdWarning, match="metavalue"):
		assert operator.ne(x, x) is True
	for compare in [operator.lt, operator.le, operator.gt, operator.ge]:
		with pytest.warns(NumericStdWarning):
			assert not compare(x, 1 << 100)
	assert str(x.match_lt(0)) == "X"
	assert str(x.match_eq(Signed(LogicArray("----")))) == "1"
	assert str(Signed(LogicArray("U0")).match_eq(Signed(LogicArray("U1")))) == "U"
	with warnings.catch_warnings():
		warnings.simplefilter("error", NumericStdWarning)
		with pytest.raises(NumericStdWarning):
			_ = x == 0


def test_shifts_logic_and_nulls() -> None:
	"""Raw logic states survive movement; numeric and logical nulls have distinct ranges."""
	x = Signed(LogicArray("HUX1", Range(3, "to", 6)))
	assert str(x >> 2) == "HHHU"
	assert str(x.srl(2)) == "00HU"
	assert str(x.sll(-2)) == "00HU"
	assert str(x.sla(-2)) == "HHHU"
	assert str(x << 2) == "X100"
	assert str(x.rol(-1)) == "1HUX"
	assert str(x.ror(-1)) == "UX1H"
	assert str(x.rotate_left(6)) == "X1HU"
	assert (x >> 0).range.left == 3
	assert x.shift_right(1).range.left == 3  # Four-bit result is 3 downto 0.
	assert x.shift_right(1).range.direction == "downto"
	assert int(Unsigned.from_int(3, width=8)) < (1 << 500)
	for method in [x.shift_left, x.shift_right, x.rotate_left, x.rotate_right, x.resize]:
		with pytest.raises(ValueError):
			method(-1)
		with pytest.raises(TypeError):
			method(cast(Any, 1.5))
	with pytest.raises(ValueError):
		x.match_lt(Signed(LogicArray("----")))
	with pytest.raises(ValueError):
		_ = x & Signed.from_int(0, width=3)
	with pytest.raises(TypeError):
		operator.and_(x, 1)
	with pytest.raises(OverflowError):
		x.match_eq(256)
	for kind in [Signed, Unsigned]:
		null = kind(LogicArray("", Range(4, "to", 3)))
		assert null.resize(3).to_int() == 0
		assert null.shift_left(4).range.left == 0
		assert (~null).range.left == -1
		assert str(null.concat(null)) == "" and null.concat(null).range.left == 4
		assert [
			str(method())
			for method in [
				null.and_reduce,
				null.nand_reduce,
				null.or_reduce,
				null.nor_reduce,
				null.xor_reduce,
				null.xnor_reduce,
			]
		] == ["1", "0", "0", "1", "0", "1"]
		with pytest.warns(NumericStdWarning):
			assert str(null.match_eq(null)) == "X"
		with pytest.raises(ValueError):
			_ = null + Logic("1")
	with pytest.raises(ValueError, match="length mismatch"):
		Unsigned.from_int(0, width=0).rrem(1)
	with pytest.raises(ValueError, match="length mismatch"):
		Unsigned.from_int(1, width=1).rrem(7)

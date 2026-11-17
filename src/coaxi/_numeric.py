# _numeric.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""VHDL-2008 numeric_std values with checked Python-integer input conversions."""

from __future__ import annotations

import operator
import warnings
from collections.abc import Iterator
from typing import ClassVar, Self, overload

from cocotb.types import Logic, LogicArray, Range

from ._bits import _Bits


class NumericStdWarning(UserWarning):
	"""A warning corresponding to a VHDL numeric_std package diagnostic."""


def _warn(operation: str, reason: str) -> None:
	warnings.warn(f"numeric_std {operation}: {reason}", NumericStdWarning, stacklevel=4)


def _integer(value: int) -> int:
	if not isinstance(value, int):
		raise TypeError("expected a Python integer")
	return value


def _natural(value: int) -> int:
	_integer(value)
	if value < 0:
		raise ValueError("expected a non-negative integer")
	return value


def _number(text: str, signed: bool) -> int:
	bits = text.translate(str.maketrans("LH", "01"))
	value = int(bits, 2)
	if signed and bits[0] == "1":
		value -= 1 << len(bits)
	return value


_COMPARE = {
	"=": operator.eq,
	"/=": operator.ne,
	"<": operator.lt,
	"<=": operator.le,
	">": operator.gt,
	">=": operator.ge,
}
_LOGICAL = {"and": operator.and_, "or": operator.or_, "xor": operator.xor}


def _match(left: str, right: str) -> Logic:
	"""Scalar LRM matching equality; '-' matches every state."""
	if "-" in (left, right):
		return Logic("1")
	if "U" in (left, right):
		return Logic("U")
	if left not in "01LH" or right not in "01LH":
		return Logic("X")
	return Logic(int(Logic(left)) == int(Logic(right)))


class _Numeric(_Bits):
	"""Share numeric_std algorithms without coupling them to bus scheduling."""

	__slots__ = ()
	_signed: ClassVar[bool] = False

	def __init__(self, value: LogicArray | Signed | Unsigned) -> None:
		"""Copy the bits and index range of value, reinterpreting signedness."""
		if hasattr(self, "_text"):
			raise AttributeError("numeric values are immutable")
		if isinstance(value, _Numeric):
			text, bounds = value._text, value._bounds
		elif isinstance(value, LogicArray):
			text = str(value)
			bounds = (value.range.left, value.range.direction, value.range.right)
		else:
			raise TypeError("expected LogicArray, Signed, or Unsigned; use from_int for Python integers")
		if text and (bounds[0] < 0 or bounds[2] < 0):
			raise ValueError("numeric_std non-null vectors require non-negative indices")
		object.__setattr__(self, "_text", text)
		object.__setattr__(self, "_bounds", bounds)

	@property
	def width(self) -> int:
		"""Number of bits, including zero for a null value."""
		return len(self._text)

	@property
	def range(self) -> Range:
		"""Independent cocotb index range, including its direction."""
		return Range(*self._bounds)

	@property
	def is_resolvable(self) -> bool:
		"""Whether every bit is 0, 1, L, or H."""
		return all(bit in "01LH" for bit in self._text)

	@classmethod
	def _null(cls) -> Self:
		return cls._new("", Range(0, "downto", 1))

	@classmethod
	def _wrapped(cls, value: int, width: int) -> Self:
		return cls._new(format(value & ((1 << width) - 1), f"0{width}b")) if width else cls._null()

	@classmethod
	def from_int(cls, value: int, *, width: int) -> Self:
		"""Convert a Python integer, checking its range unless width is zero."""
		_integer(value)
		_natural(width)
		if not cls._signed:
			_natural(value)
		if width == 0:
			return cls._null()
		lower = -(1 << (width - 1)) if cls._signed else 0
		upper = (1 << (width - int(cls._signed))) - 1
		if not lower <= value <= upper:
			raise OverflowError(f"{value} does not fit {cls.__name__} with width {width}")
		return cls._wrapped(value, width)

	def to_int(self) -> int:
		"""Convert to a Python integer; reject unresolved bits independently of cocotb settings."""
		if not self.width:
			_warn("to_int", "null argument detected, returning 0")
			return 0
		if not self.is_resolvable:
			raise ValueError(f"cannot convert unresolved {type(self).__name__} {self._text} to an integer")
		return _number(self._text, self._signed)

	def to_logic_array(self) -> LogicArray:
		"""Return an independent cocotb array with the same bits and range."""
		return self._array()

	def as_signed(self) -> Signed:
		"""Interpret the same bits and range as Signed."""
		return Signed(self)

	def as_unsigned(self) -> Unsigned:
		"""Interpret the same bits and range as Unsigned."""
		return Unsigned(self)

	def __int__(self) -> int:
		"""Perform the same explicit conversion as to_int."""
		return self.to_int()

	def __bool__(self) -> bool:
		"""Reject implicit truth testing; use a comparison."""
		raise TypeError("numeric vectors have no implicit truth value; use a comparison")

	def __len__(self) -> int:
		"""Return the number of bits."""
		return self.width

	def __str__(self) -> str:
		"""Return logic characters from the most significant bit to the least."""
		return self._text

	def __repr__(self) -> str:
		"""Show the numeric type, bits, and index range."""
		return f"{type(self).__name__}({self._array()!r})"

	def __iter__(self) -> Iterator[Logic]:
		"""Iterate from the leftmost bit to the rightmost."""
		return (Logic(bit) for bit in self._text)

	@overload
	def __getitem__(self, item: int) -> Logic: ...

	@overload
	def __getitem__(self, item: slice) -> Self: ...

	def __getitem__(self, item: int | slice) -> Logic | Self:
		"""Index or slice using cocotb's inclusive HDL indices."""
		if isinstance(item, slice) and item == slice(None) and not self.width:
			return type(self)._new(self._text, self.range)
		value = self._array()[item]
		return type(self)(value) if isinstance(value, LogicArray) else value

	def resize(self, width: int) -> Self:
		"""Apply VHDL resize, keeping the original sign on signed narrowing."""
		_natural(width)
		if not width:
			return type(self)._null()
		if not self.width:
			return type(self)._new("0" * width)
		if self._signed:
			low = self._text[-(width - 1) :] if width > 1 else ""
			text = self._text[0] * (width - len(low)) + low
		else:
			text = self._text[-width:].rjust(width, "0")
		return type(self)._new(text)

	def _operand(self, other: object) -> Self:
		if isinstance(other, int):
			return type(self).from_int(other, width=self.width)
		if type(other) is type(self):
			return other
		raise TypeError("operands require the same numeric type or a supported VHDL scalar overload")

	def _arithmetic(self, other: object, operation: str, reflected: bool = False) -> Self:
		if isinstance(other, Logic) and operation in ("+", "-"):
			if not self.width:
				raise ValueError("numeric_std scalar Logic arithmetic indexes bit 0 of a null vector")
			right = type(self)._new("0" * (self.width - 1) + str(other))
		elif isinstance(other, int) and operation in ("/", "rem", "mod"):
			return self._scalar_division(other, operation, reflected)
		else:
			right = self._operand(other)
		left = self
		if reflected:
			left, right = right, left
		if not left.width or not right.width:
			return type(self)._null()
		width = (
			left.width + right.width
			if operation == "*"
			else left.width
			if operation == "/"
			else right.width
			if operation in ("rem", "mod")
			else max(left.width, right.width)
		)
		if not left.is_resolvable or not right.is_resolvable:
			return type(self)._new("X" * width)
		a, b = _number(left._text, self._signed), _number(right._text, self._signed)
		if operation == "+":
			result = a + b
		elif operation == "-":
			result = a - b
		elif operation == "*":
			result = a * b
		else:
			if not b:
				raise ZeroDivisionError(f"numeric_std {operation} by zero")
			quotient = abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)
			remainder = abs(a) % abs(b)
			if operation == "/":
				result = quotient
			elif operation == "rem":
				result = -remainder if a < 0 else remainder
			elif not self._signed:
				result = remainder
			else:
				# numeric_std tests the raw dividend sign against literal '1'.
				negative = left._text[0] == "1"
				if b < 0 and negative:
					result = -remainder
				elif b < 0 and remainder:
					result = remainder - abs(b)
				elif negative and remainder:
					result = abs(b) - remainder
				else:
					result = remainder
		return type(self)._wrapped(result, width)

	def _scalar_division(self, other: int, operation: str, reflected: bool) -> Self:
		if not self._signed:
			_natural(other)
		if not self.width:
			if reflected and operation == "rem" and not self._signed:
				raise ValueError("numeric_std integer rem null unsigned: array length mismatch")
			return type(self)._null()
		bits = max(1, ((~other).bit_length() if other < 0 else other.bit_length()) + int(self._signed))
		width = max(self.width, bits)
		if operation == "/" and not reflected and width > self.width:
			return type(self)._new("0" * self.width)
		scalar = type(self).from_int(other, width=width)
		left, right = (scalar, self) if reflected else (self, scalar)
		result = left._arithmetic(right, operation)
		# A.30 evaluates vector rem before the unconstrained array assignment.
		# Resolved zero division must therefore precede the length error.
		if reflected and operation == "rem" and not self._signed and width > self.width:
			raise ValueError("numeric_std integer rem unsigned: array length mismatch")
		result = result.resize(width)
		if width > self.width and result._text[-1] != "X":
			fill = result._text[-self.width] if self._signed else "0"
			if result._text[: -self.width] != fill * (width - self.width):
				_warn(operation, "arithmetic result truncated")
		return result.resize(self.width)

	def __add__(self, other: Self | int | Logic) -> Self:
		"""Add using VHDL operand conversions and result width."""
		return self._arithmetic(other, "+")

	def __radd__(self, other: int | Logic) -> Self:
		"""Add a scalar left operand using VHDL rules."""
		return self._arithmetic(other, "+", True)

	def __sub__(self, other: Self | int | Logic) -> Self:
		"""Subtract using VHDL operand conversions and result width."""
		return self._arithmetic(other, "-")

	def __rsub__(self, other: int | Logic) -> Self:
		"""Subtract from a scalar left operand using VHDL rules."""
		return self._arithmetic(other, "-", True)

	def __mul__(self, other: Self | int) -> Self:
		"""Multiply, producing the sum of the converted operand widths."""
		return self._arithmetic(other, "*")

	def __rmul__(self, other: int) -> Self:
		"""Multiply by an integer left operand using VHDL rules."""
		return self._arithmetic(other, "*", True)

	def __truediv__(self, other: Self | int) -> Self:
		"""Divide, truncating the quotient towards zero."""
		return self._arithmetic(other, "/")

	def __rtruediv__(self, other: int) -> Self:
		"""Divide an integer left operand using VHDL rules."""
		return self._arithmetic(other, "/", True)

	def __mod__(self, other: Self | int) -> Self:
		"""Calculate VHDL mod, following the divisor's sign."""
		return self._arithmetic(other, "mod")

	def __rmod__(self, other: int) -> Self:
		"""Calculate an integer left operand's VHDL mod."""
		return self._arithmetic(other, "mod", True)

	def mod(self, other: Self | int) -> Self:
		"""Calculate VHDL mod; equivalent to the % operator."""
		return self._arithmetic(other, "mod")

	def rem(self, other: Self | int) -> Self:
		"""Calculate VHDL rem, following the dividend's sign."""
		return self._arithmetic(other, "rem")

	def rrem(self, other: int) -> Self:
		"""Calculate other rem self using the integer/vector overload."""
		return self._arithmetic(other, "rem", True)

	def _compare(self, other: object, operation: str) -> bool:
		if isinstance(other, int):
			if not self._signed:
				_natural(other)
			right = None
		elif type(other) is type(self):
			right = other
		else:
			raise TypeError("comparison requires the same numeric type or a Python integer")
		if not self.width or (right is not None and not right.width):
			_warn(operation, "null argument detected")
			return operation == "/="
		if not self.is_resolvable or (right is not None and not right.is_resolvable):
			_warn(operation, "metavalue detected")
			return operation == "/="
		b = _number(right._text, self._signed) if right is not None else other
		return _COMPARE[operation](_number(self._text, self._signed), b)

	def __eq__(self, other: object) -> bool:
		"""Compare numerically; null or unresolved operands warn and return False."""
		return self._compare(other, "=")

	def __ne__(self, other: object) -> bool:
		"""Compare numerically; null or unresolved operands warn and return True."""
		return self._compare(other, "/=")

	def __lt__(self, other: Self | int) -> bool:
		"""Compare numerically; null or unresolved operands warn and return False."""
		return self._compare(other, "<")

	def __le__(self, other: Self | int) -> bool:
		"""Compare numerically; null or unresolved operands warn and return False."""
		return self._compare(other, "<=")

	def __gt__(self, other: Self | int) -> bool:
		"""Compare numerically; null or unresolved operands warn and return False."""
		return self._compare(other, ">")

	def __ge__(self, other: Self | int) -> bool:
		"""Compare numerically; null or unresolved operands warn and return False."""
		return self._compare(other, ">=")

	def _matching(self, other: Self | int, operation: str) -> Logic:
		right = self._operand(other)
		if not self.width or not right.width:
			_warn("?" + operation, "null argument detected, returning X")
			return Logic("X")
		if operation not in ("=", "/="):
			if "-" in self._text or "-" in right._text:
				raise ValueError("numeric_std matching ordering: '-' found in compare string")
			if not self.is_resolvable or not right.is_resolvable:
				return Logic("X")
			return Logic(self._compare(right, operation))
		width = max(self.width, right.width)
		result = Logic(operation == "=")
		for a, b in zip(reversed(self.resize(width)._text), reversed(right.resize(width)._text), strict=True):
			bit = _match(a, b)
			if operation == "/=":
				bit = ~bit
			if str(bit) == "U":
				return bit
			if str(bit) == "X" or str(result) == "X":
				result = Logic("X")
			else:
				result = result & bit if operation == "=" else result | bit
		return result

	def match_eq(self, other: Self | int) -> Logic:
		"""Apply VHDL ?=, including '-' wildcards and U/X propagation."""
		return self._matching(other, "=")

	def match_ne(self, other: Self | int) -> Logic:
		"""Apply VHDL ?/=, including '-' wildcards and U/X propagation."""
		return self._matching(other, "/=")

	def match_lt(self, other: Self | int) -> Logic:
		"""Apply VHDL ?<; '-' is an error and unresolved values produce X."""
		return self._matching(other, "<")

	def match_le(self, other: Self | int) -> Logic:
		"""Apply VHDL ?<=; '-' is an error and unresolved values produce X."""
		return self._matching(other, "<=")

	def match_gt(self, other: Self | int) -> Logic:
		"""Apply VHDL ?>; '-' is an error and unresolved values produce X."""
		return self._matching(other, ">")

	def match_ge(self, other: Self | int) -> Logic:
		"""Apply VHDL ?>=; '-' is an error and unresolved values produce X."""
		return self._matching(other, ">=")

	def _logical(self, other: Self | Logic, operation: str) -> Self:
		if isinstance(other, Logic):
			text = str(other) * self.width
		elif type(other) is type(self):
			text = other._text
			if self.width != other.width:
				raise ValueError("numeric_std logical operands must have equal lengths")
		else:
			raise TypeError("logical operands require the same numeric type or Logic")
		base = "xor" if operation == "xnor" else operation.removeprefix("n")
		result = [_LOGICAL[base](Logic(a), Logic(b)) for a, b in zip(self._text, text, strict=True)]
		if operation in ("nand", "nor", "xnor"):
			result = [~bit for bit in result]
		bounds = Range(1, "to", self.width) if isinstance(other, Logic) else None
		return type(self)._new("".join(map(str, result)), bounds)

	def __and__(self, other: Self | Logic) -> Self:
		"""Apply IEEE logical and elementwise; a scalar Logic broadcasts."""
		return self._logical(other, "and")

	def __rand__(self, other: Logic) -> Self:
		"""Apply logical and with a scalar Logic left operand."""
		return self._logical(other, "and")

	def __or__(self, other: Self | Logic) -> Self:
		"""Apply IEEE logical or elementwise; a scalar Logic broadcasts."""
		return self._logical(other, "or")

	def __ror__(self, other: Logic) -> Self:
		"""Apply logical or with a scalar Logic left operand."""
		return self._logical(other, "or")

	def __xor__(self, other: Self | Logic) -> Self:
		"""Apply IEEE logical xor elementwise; a scalar Logic broadcasts."""
		return self._logical(other, "xor")

	def __rxor__(self, other: Logic) -> Self:
		"""Apply logical xor with a scalar Logic left operand."""
		return self._logical(other, "xor")

	def __invert__(self) -> Self:
		"""Apply IEEE logical not to each raw logic value."""
		return type(self)._new("".join(str(~Logic(bit)) for bit in self._text))

	def nand(self, other: Self | Logic) -> Self:
		"""Apply VHDL logical nand."""
		return self._logical(other, "nand")

	def nor(self, other: Self | Logic) -> Self:
		"""Apply VHDL logical nor."""
		return self._logical(other, "nor")

	def xnor(self, other: Self | Logic) -> Self:
		"""Apply VHDL logical xnor."""
		return self._logical(other, "xnor")

	def _reduce(self, operation: str) -> Logic:
		base = "xor" if operation == "xnor" else operation.removeprefix("n")
		result = Logic(base == "and")
		for bit in self._text:
			result = _LOGICAL[base](result, Logic(bit))
		return ~result if operation in ("nand", "nor", "xnor") else result

	def and_reduce(self) -> Logic:
		"""Reduce using IEEE and; a null vector produces 1."""
		return self._reduce("and")

	def nand_reduce(self) -> Logic:
		"""Reduce using IEEE nand; a null vector produces 0."""
		return self._reduce("nand")

	def or_reduce(self) -> Logic:
		"""Reduce using IEEE or; a null vector produces 0."""
		return self._reduce("or")

	def nor_reduce(self) -> Logic:
		"""Reduce using IEEE nor; a null vector produces 1."""
		return self._reduce("nor")

	def xor_reduce(self) -> Logic:
		"""Reduce using IEEE xor; a null vector produces 0."""
		return self._reduce("xor")

	def xnor_reduce(self) -> Logic:
		"""Reduce using IEEE xnor; a null vector produces 1."""
		return self._reduce("xnor")

	def _shift(self, count: int, right: bool, arithmetic: bool = False) -> Self:
		_natural(count)
		if not self.width:
			return type(self)._null()
		if right and arithmetic and self._signed and (count == 0 or self.width == 1):
			return type(self)._new(self._text, self.range)
		count = min(count, self.width)
		if right:
			fill = self._text[0] if arithmetic and self._signed else "0"
			text = fill * count + self._text[: self.width - count]
		else:
			text = self._text[count:] + "0" * count
		return type(self)._new(text)

	def shift_left(self, count: int) -> Self:
		"""Shift left by a non-negative count, filling with zero."""
		return self._shift(count, False)

	def shift_right(self, count: int) -> Self:
		"""Shift right by a non-negative count, extending the sign for Signed."""
		return self._shift(count, True, True)

	def __lshift__(self, count: int) -> Self:
		"""Apply shift_left."""
		return self.shift_left(count)

	def __rshift__(self, count: int) -> Self:
		"""Apply shift_right."""
		return self.shift_right(count)

	def sll(self, count: int) -> Self:
		"""Apply VHDL sll; a negative count shifts logically right."""
		_integer(count)
		return self._shift(abs(count), count < 0)

	def srl(self, count: int) -> Self:
		"""Apply VHDL srl; a negative count shifts left."""
		_integer(count)
		return self._shift(abs(count), count >= 0)

	def sla(self, count: int) -> Self:
		"""Apply VHDL sla; a negative count shifts right with sign extension."""
		_integer(count)
		return self._shift(abs(count), count < 0, True)

	def sra(self, count: int) -> Self:
		"""Apply VHDL sra; a negative count shifts left."""
		_integer(count)
		return self._shift(abs(count), count >= 0, True)

	def _rotate(self, count: int) -> Self:
		if not self.width:
			return type(self)._null()
		count %= self.width
		return type(self)._new(self._text[count:] + self._text[:count])

	def rotate_left(self, count: int) -> Self:
		"""Rotate left by a non-negative count."""
		_natural(count)
		return self._rotate(count)

	def rotate_right(self, count: int) -> Self:
		"""Rotate right by a non-negative count."""
		_natural(count)
		return self._rotate(-count)

	def rol(self, count: int) -> Self:
		"""Apply VHDL rol; a negative count rotates right."""
		_integer(count)
		return self._rotate(count)

	def ror(self, count: int) -> Self:
		"""Apply VHDL ror; a negative count rotates left."""
		_integer(count)
		return self._rotate(-count)

	def concat(self, other: Self | Logic) -> Self:
		"""Concatenate raw bits, placing other after this value."""
		if isinstance(other, Logic):
			text = str(other)
		elif type(other) is type(self):
			text = other._text
		else:
			raise TypeError("concatenation requires the same numeric type or Logic")
		if not self.width and not text:
			assert isinstance(other, _Numeric)
			return type(self)._new(text, other.range)
		text = self._text + text
		return type(self)._new(text, Range(0, "to", len(text) - 1))


class Signed(_Numeric):
	"""Immutable VHDL-2008 signed value, with the leftmost bit as the sign bit."""

	__slots__ = ()
	_signed = True

	def __neg__(self) -> Self:
		"""Negate at the existing width, including minimum-value wraparound."""
		if not self.width:
			return type(self)._null()
		if not self.is_resolvable:
			return type(self)._new("X" * self.width)
		return type(self)._wrapped(-_number(self._text, True), self.width)

	def __abs__(self) -> Self:
		"""Take the magnitude at the existing width, including minimum-value wraparound."""
		if not self.width:
			return type(self)._null()
		if not self.is_resolvable:
			return type(self)._new("X" * self.width)
		return type(self)._wrapped(abs(_number(self._text, True)), self.width)


class Unsigned(_Numeric):
	"""Immutable VHDL-2008 unsigned value, with the leftmost bit as the most significant."""

	__slots__ = ()

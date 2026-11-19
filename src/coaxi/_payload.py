# _payload.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Synchronous payload access, preserving HDL logic values and record fields."""

from typing import Protocol
from collections.abc import Mapping

from cocotb.types import Logic, LogicArray
from cocotb.handle import HierarchyObject, LogicArrayObject, LogicObject, SimHandleBase

type PayloadValue = int | str | Logic | LogicArray | Mapping[str, PayloadValue]
"""Default input values; reads return Logic, LogicArray or nested dictionaries.

Integers are unsigned. Use LogicArray.from_signed for signed integers. Strings
and logic values may deliberately contain meta-values for propagation tests.
"""


class Payload[T](Protocol):
	"""Synchronous payload access for an application-defined value type T.

	Bind handles in the implementation. Methods must not yield. Read must return
	an independent snapshot; clear must drive defined values to all owned leaves.
	"""

	def read(self) -> T:
		"""Return the currently driven value without numeric conversion."""
		...

	def drive(self, value: T) -> None:
		"""Drive value without yielding; validate before writing where possible."""
		...

	def clear(self) -> None:
		"""Drive a defined reset value to every owned payload leaf."""
		...


class _AbsentPayload:
	"""Represent a physically absent payload, without accessing any HDL handle."""

	def read(self) -> None:
		return None

	def drive(self, value: None) -> None:
		if value is not None:
			raise ValueError("an absent data signal requires data=None")

	def clear(self) -> None:
		pass


class HandlePayload:
	"""Access logic/vector leaves or named containers such as VHDL records.

	``handle`` is a data handle. Containers are discovered once and represented
	by exact field-name mappings. Unsupported leaf types fail at construction.
	No record packing or integer conversion is performed.
	"""

	def __init__(self, handle: SimHandleBase) -> None:
		self._handle = handle
		self._children: dict[str, HandlePayload] = {}
		if isinstance(handle, HierarchyObject):
			self._children = {child._name: HandlePayload(child) for child in handle}
			if not self._children:
				raise TypeError(f"{handle._path}: empty or inaccessible payload container")
		elif not isinstance(handle, (LogicObject, LogicArrayObject)):
			raise TypeError(f"{handle._path}: unsupported payload handle {type(handle).__name__}")

	def read(self) -> PayloadValue:
		"""Return a fresh logic value or field mapping, preserving all meta-values."""
		if self._children:
			return {name: child.read() for name, child in self._children.items()}
		if isinstance(self._handle, (LogicObject, LogicArrayObject)):
			return self._handle.value
		raise TypeError("unsupported payload handle")

	def _prepare(self, value: PayloadValue) -> list[tuple[LogicObject | LogicArrayObject, Logic | LogicArray]]:
		if value is None:
			raise TypeError(f"{self._handle._path}: None requires an absent data signal")
		if self._children:
			if not isinstance(value, Mapping) or value.keys() != self._children.keys():
				raise ValueError(f"{self._handle._path}: expected exactly these fields: {list(self._children)}")
			return [write for name, child in self._children.items() for write in child._prepare(value[name])]
		handle = self._handle
		if not isinstance(handle, (LogicObject, LogicArrayObject)):
			raise TypeError("unsupported payload handle")
		return [(handle, self._leaf_value(handle, value))]

	@staticmethod
	def _leaf_value(handle: LogicObject | LogicArrayObject, value: PayloadValue) -> Logic | LogicArray:
		if value is None:
			raise TypeError(f"{handle._path}: None requires an absent data signal")
		if isinstance(value, Mapping):
			raise TypeError(f"{handle._path}: expected a logic value, not a field mapping")
		if isinstance(value, int) and value < 0:
			raise ValueError(f"{handle._path}: integer payloads must be unsigned; use LogicArray.from_signed")
		try:
			if isinstance(handle, LogicObject):
				if isinstance(value, LogicArray):
					value = str(value)
				return Logic(value)
			if isinstance(value, (Logic, LogicArray)):
				value = str(value)
			return LogicArray(value, handle.range)
		except (ValueError, TypeError, OverflowError) as exc:
			raise type(exc)(f"{handle._path}: {exc}") from exc

	def drive(self, value: PayloadValue) -> None:
		"""Validate the entire value, then drive it without yielding.

		``value`` must match every field and leaf width. Integer leaves must be
		non-negative and fit the HDL width. Strings retain deliberate X/U/etc.
		Validation errors leave all leaves unchanged.
		"""
		handle = self._handle
		if isinstance(handle, (LogicObject, LogicArrayObject)):
			handle.set(self._leaf_value(handle, value))
		else:
			for handle, leaf in self._prepare(value):
				handle.set(leaf)

	def clear(self) -> None:
		"""Drive zero to all leaves, clearing any previously driven meta-values."""
		if self._children:
			for child in self._children.values():
				child.clear()
		elif isinstance(self._handle, (LogicObject, LogicArrayObject)):
			self._handle.set(0)


def to_unsigned(value: LogicArray) -> int:
	"""Convert value to an unsigned integer, rejecting unresolved meta-values.

	``value`` is a vector snapshot. Weak L/H values are resolvable. X/U/Z/etc.
	raise ValueError, regardless of cocotb's COCOTB_RESOLVE_X setting.
	"""
	if not value.is_resolvable:
		raise ValueError(f"cannot convert unresolved payload {value!s} to an integer")
	return value.to_unsigned()


def to_signed(value: LogicArray) -> int:
	"""Convert value as two's complement, with the same checks as to_unsigned.

	``value`` is a vector snapshot; return its signed integer interpretation.
	"""
	if not value.is_resolvable:
		raise ValueError(f"cannot convert unresolved payload {value!s} to an integer")
	return value.to_signed()

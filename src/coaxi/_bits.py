# _bits.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Immutable logic storage, independent of numeric interpretation."""

from __future__ import annotations

from typing import Self

from cocotb.types import LogicArray, Range


class _Bits:
	"""Store logic characters and range bounds without sharing mutable arrays."""

	__slots__ = ("_bounds", "_text")
	_text: str
	_bounds: tuple[int, str, int]

	def __setattr__(self, name: str, value: object) -> None:
		raise AttributeError("numeric values are immutable")

	def __delattr__(self, name: str) -> None:
		raise AttributeError("numeric values are immutable")

	@classmethod
	def _new(cls, text: str, bounds: Range | None = None) -> Self:
		if bounds is None:
			bounds = Range(len(text) - 1, "downto", 0)
		value = object.__new__(cls)
		object.__setattr__(value, "_text", text)
		object.__setattr__(value, "_bounds", (bounds.left, bounds.direction, bounds.right))
		return value

	def _array(self) -> LogicArray:
		return LogicArray(self._text, Range(*self._bounds))

# test_numeric_documentation.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check handwritten numeric operator signatures, property types, and overload typing."""

import inspect
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Self, assert_type, get_type_hints

from cocotb.types import Logic, LogicArray, Range

from coaxi import Signed, Unsigned
from tests.test_documentation import _documented_signature


def test_numeric_operator_contracts() -> None:
	"""Compare every handwritten operator contract with its implemented annotations."""
	guide = (Path(__file__).resolve().parents[1] / "docs" / "numeric.md").read_text(encoding="utf-8")
	declarations = dict(re.findall(r"^def (\w+)(\([^\n]+): \.\.\.$", guide, re.MULTILINE))
	assert len(declarations) == 34
	namespace = {"Self": Self, "Logic": Logic, "Iterator": Iterator}
	for kind in (Signed, Unsigned):
		for name, text in declarations.items():
			if name in ("__neg__", "__abs__") and kind is Unsigned:
				assert not hasattr(kind, name)
				continue
			method = getattr(kind, name)
			hints = get_type_hints(method)
			actual = inspect.signature(method)
			actual = actual.replace(
				parameters=[
					p.replace(annotation=hints[p.name]) for p in actual.parameters.values() if p.name != "self"
				],
				return_annotation=hints["return"],
			)
			assert _documented_signature(text, namespace) == actual, (kind, name)
		for name, annotation in [("width", int), ("range", Range), ("is_resolvable", bool)]:
			attribute = getattr(kind, name)
			assert isinstance(attribute, property)
			assert attribute.fset is None and attribute.fdel is None
			assert get_type_hints(attribute.fget)["return"] is annotation


def test_numeric_overload_typing() -> None:
	"""Exercise statically checked concrete return types for arithmetic and indexing."""
	s = Signed.from_int(-3, width=8)
	u = Unsigned(s)
	assert_type(s[7], Logic)
	assert_type(s[7:4], Signed)
	assert_type(u[7:4], Unsigned)
	assert_type(s + 1, Signed)
	assert_type(1 - s, Signed)
	assert_type(s * 3, Signed)
	assert_type(s / 3, Signed)
	assert_type(s.rem(3), Signed)
	assert_type(u * 3, Unsigned)
	assert_type(s & Logic("1"), Signed)
	assert_type(s.match_lt(3), Logic)
	assert_type(s.to_logic_array(), LogicArray)
	assert_type(s.as_unsigned(), Unsigned)

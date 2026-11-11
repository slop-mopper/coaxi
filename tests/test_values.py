# test_values.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Pure Python checks for explicit, environment-independent conversions."""

import pytest
from cocotb.types import LogicArray

from coaxi import to_signed, to_unsigned


@pytest.mark.parametrize("bits", ["X001", "U001", "Z001", "W001", "-001"])
def test_unresolved_conversion(bits: str) -> None:
	"""Reject unresolved bits for both numeric interpretations of bits."""
	value = LogicArray(bits)
	with pytest.raises(ValueError, match="unresolved"):
		to_unsigned(value)
	with pytest.raises(ValueError, match="unresolved"):
		to_signed(value)


def test_signed_and_unsigned() -> None:
	"""Keep numeric interpretation explicit, allowing resolved weak logic."""
	assert to_unsigned(LogicArray("1111")) == 15
	assert to_signed(LogicArray("1111")) == -1
	assert to_unsigned(LogicArray("LH01")) == 5

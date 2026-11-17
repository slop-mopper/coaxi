# numeric_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Drive and read actual numeric_std ports through explicit LogicArray conversion."""

import random

import cocotb
from cocotb.handle import HierarchyObject
from cocotb.types import LogicArray
from cocotb.triggers import Timer

from coaxi import Signed, Unsigned


@cocotb.test(timeout_time=10, timeout_unit="us")
async def numeric_values(dut: HierarchyObject) -> None:
	"""Check cocotb snapshots and drives against concurrent VHDL arithmetic."""
	if not __debug__:
		raise RuntimeError("numeric assertions require Python without optimisation")
	seed = 0x51_6E_ED
	dut._log.debug("numeric interoperation seed=%d", seed)
	random_source = random.Random(seed)
	texts = ["00000000", "11111111", "01111111", "10000000", "HUZXWL-1", "LHLH0011"]
	texts += [format(random_source.randrange(256), "08b") for _ in range(50)]
	for index, text in enumerate(texts):
		a = Signed(LogicArray(text))
		b = Signed(LogicArray(texts[(index + 1) % len(texts)]))
		u, v = Unsigned(a), Unsigned(b)
		if not a.is_resolvable:
			for value in (a, u):
				try:
					value.to_int()
				except ValueError:
					pass
				else:
					raise AssertionError("unresolved integer conversion silently resolved bits")
		dut.a.value = a.to_logic_array()
		dut.b.value = b.to_logic_array()
		dut.u.value = u.to_logic_array()
		dut.v.value = v.to_logic_array()
		await Timer(10, unit="ns")
		assert str(Signed(dut.a.value)) == str(a)
		assert str(Unsigned(dut.u.value)) == str(u)
		for handle, expected in [
			(dut.sum_s, a + b),
			(dut.product_s, a * b),
			(dut.sum_u, u + v),
			(dut.product_u, u * v),
			(dut.logic_s, a & b),
			(dut.shift_s, a >> 2),
		]:
			assert str(handle.value) == str(expected), (seed, index, handle._path, expected)

# custom_payload.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.2-sol

"""Send a frame of Python IQ samples through a VHDL record stream."""

from dataclasses import dataclass

import cocotb
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject, LogicArrayObject

from coaxi import AxiStreamBus, AxiStreamSink, AxiStreamSource, Payload, to_signed


@dataclass(frozen=True)
class IQ:
	i: int
	q: int


class IQPayload(Payload[IQ]):
	def __init__(self, bus: AxiStreamBus) -> None:
		record = bus.data
		if not isinstance(record, HierarchyObject):
			raise TypeError("IQ data must be a record")
		i, q = record["i"], record["q"]
		if not isinstance(i, LogicArrayObject) or not isinstance(q, LogicArrayObject):
			raise TypeError("IQ fields must be logic vectors")
		self._i = i
		self._q = q

	def drive(self, value: IQ) -> None:
		# Convert both fields before writing either one.
		i = LogicArray.from_signed(value.i, self._i.range)
		q = LogicArray.from_signed(value.q, self._q.range)
		self._i.set(i)
		self._q.set(q)

	def read(self) -> IQ:
		return IQ(to_signed(self._i.value), to_signed(self._q.value))

	def clear(self) -> None:
		self.drive(IQ(0, 0))


@cocotb.test(timeout_time=1000, timeout_unit="ns")
async def custom_payload(dut: HierarchyObject) -> None:
	cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start(start_high=False))
	input_bus = AxiStreamBus.bind(dut, prefix="s", last=True)
	output_bus = AxiStreamBus.bind(dut, prefix="m", last=True)
	source = AxiStreamSource(input_bus, dut.clk, payload=IQPayload(input_bus))
	sink = AxiStreamSink(output_bus, dut.clk, payload=IQPayload(output_bus))
	await source.initialise()
	await sink.initialise()

	samples = [IQ(-32768, 34), IQ(56, -78), IQ(90, 32767)]
	sending = cocotb.start_soon(source.send_frame(samples))
	frame = await sink.recv_frame(max_transfers=len(samples))
	await sending
	assert [beat.data for beat in frame] == samples
	assert [beat.last for beat in frame] == [False, False, True]

	await source.close()
	await sink.close()

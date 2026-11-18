# backpressure.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.2-sol

"""Send a frame through a one-entry register with independent pause patterns."""

from collections.abc import Iterator

import cocotb
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject
from cocotb.triggers import FallingEdge

from coaxi import AxiStreamBus, AxiStreamSink, AxiStreamSource, to_unsigned


def input_gaps() -> Iterator[bool]:
	while True:
		yield False
		yield False
		yield True


@cocotb.test(timeout_time=1000, timeout_unit="ns")
async def backpressure(dut: HierarchyObject) -> None:
	dut.wipe_registers.value = 1
	dut.allow_input.value = 0
	clock = dut.beat_clock
	cocotb.start_soon(Clock(clock, 10, unit="ns").start(start_high=False))

	source = AxiStreamSource(AxiStreamBus.bind(dut, prefix="s", last=True), clock)
	sink = AxiStreamSink(AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True), clock)
	await source.initialise()
	await sink.initialise()
	await FallingEdge(clock)
	dut.wipe_registers.value = 0
	dut.allow_input.value = 1

	source.set_pause_generator(input_gaps())
	sink.set_pause_generator([True, True, False])
	values = [10, 20, 30, 40]
	sending = cocotb.start_soon(source.send_frame(values))
	frame = await sink.recv_frame(max_transfers=len(values))
	await sending

	received = []
	for beat in frame:
		assert isinstance(beat.data, LogicArray)
		received.append(to_unsigned(beat.data))
	assert received == values
	assert int(dut.accepted.value) == int(dut.retired.value) == len(values)

	await source.close()
	await sink.close()

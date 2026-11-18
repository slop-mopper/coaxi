# no_ready.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.2-sol

"""Capture valid-only events before the test starts receiving."""

import cocotb
from cocotb.clock import Clock
from cocotb.handle import HierarchyObject

from coaxi import AxiStreamBus, AxiStreamSink, AxiStreamSource


@cocotb.test(timeout_time=1000, timeout_unit="ns")
async def no_ready(dut: HierarchyObject) -> None:
	clock = dut.beat_clock
	cocotb.start_soon(Clock(clock, 10, unit="ns").start(start_high=False))
	bus = AxiStreamBus.bind(dut, valid=dut.plain_valid, data=False, ready=False)
	source = AxiStreamSource(bus, clock)
	sink = AxiStreamSink(bus, clock, buffer_capacity=3)
	await source.initialise()
	await sink.initialise()

	for _ in range(3):
		await source.send(None)

	for _ in range(3):
		event = await sink.recv()
		assert event.data is None
		assert event.last is None

	await source.close()
	await sink.close()

# stream_loopback.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Bounded usage example, run against tests/hdl/stream_dut.vhd by pytest."""

from collections.abc import Mapping

import cocotb
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject

from coaxi import AxiStreamBus, AxiStreamSink, AxiStreamSource, to_signed, to_unsigned


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def stream_loopback(dut: HierarchyObject) -> None:
	"""Demonstrate unframed vector and framed record transfers on undriven buses."""
	# Start a clock only if the testbench owns it; do not drive a DUT-owned clock.
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	bus = AxiStreamBus.bind(dut, prefix="plain", t_prefix=False)
	source = AxiStreamSource(bus, clock="beat_clock")
	sink = AxiStreamSink(bus, clock="beat_clock")
	await source.reset()
	await sink.reset()

	# A same-bus loopback needs concurrent send/receive to complete its handshake.
	sending = cocotb.start_soon(source.send(42))
	transfer = await sink.recv()
	await sending
	assert isinstance(transfer.data, LogicArray)
	assert to_unsigned(transfer.data) == 42
	assert transfer.last is None

	record_bus = AxiStreamBus.bind(
		dut,
		data="iq_word_in",
		valid="sample_available",
		ready="consumer_accepts",
		last="end_of_packet",
	)
	record_source = AxiStreamSource(record_bus, clock=dut.beat_clock)
	record_sink = AxiStreamSink(record_bus, clock=dut.beat_clock)
	await record_source.reset()
	await record_sink.reset()

	async def send_samples() -> None:
		for i, q, last in ((-12, 34, False), (56, -78, True)):
			await record_source.send(
				{"i": LogicArray.from_signed(i, 16), "q": LogicArray.from_signed(q, 16)},
				last=last,
			)

	sending_samples = cocotb.start_soon(send_samples())
	for i, q, last in ((-12, 34, False), (56, -78, True)):
		transfer = await record_sink.recv()
		assert isinstance(transfer.data, Mapping)
		i_bits, q_bits = transfer.data["i"], transfer.data["q"]
		assert isinstance(i_bits, LogicArray)
		assert isinstance(q_bits, LogicArray)
		assert to_signed(i_bits) == i
		assert to_signed(q_bits) == q
		assert transfer.last is last
	await sending_samples

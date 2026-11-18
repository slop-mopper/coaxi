# reset_recovery.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.2-sol

"""Start with reset asserted, then interrupt a stalled send with reset."""

import cocotb
from cocotb.clock import Clock
from cocotb.handle import HierarchyObject, LogicObject
from cocotb.triggers import ReadOnly, RisingEdge, FallingEdge, Timer

from coaxi import AxiStreamBus, AxiStreamSink, AxiStreamSource, TransferReset


@cocotb.test(timeout_time=1000, timeout_unit="ns")
async def reset_recovery(dut: HierarchyObject) -> None:
	clock, reset = dut.beat_clock, dut.startup_reset
	assert isinstance(clock, LogicObject)
	reset.value = 1
	await Timer(1, unit="ns")  # Let the VHDL reset write take effect.
	Clock(clock, 10, unit="ns").start(start_high=False)
	bus = AxiStreamBus.bind(dut, prefix="plain", t_prefix=False)
	source = AxiStreamSource(bus, clock, reset=reset, reset_active_high=True)
	sink = AxiStreamSink(bus, clock, reset=reset, reset_active_high=True)
	source_init = cocotb.start_soon(source.initialise())
	sink_init = cocotb.start_soon(sink.initialise())
	for _ in range(3):
		await RisingEdge(clock)
	assert not source_init.done() and not sink_init.done()
	reset.value = 0  # Release after a rising edge, before awaiting initialisation.
	await source_init
	await sink_init

	async def interrupted_send() -> None:
		try:
			await source.send(42)
		except TransferReset:
			return
		raise AssertionError("send returned without a receiver")

	stalled = cocotb.start_soon(interrupted_send())
	await FallingEdge(clock)
	await ReadOnly()
	assert int(dut.plain_valid.value) == 1
	assert int(dut.plain_ready.value) == 0

	await RisingEdge(clock)
	reset.value = 1
	await stalled
	await ReadOnly()
	assert int(dut.plain_valid.value) == 0

	await RisingEdge(clock)
	reset.value = 0
	await RisingEdge(clock)  # R0: first rising edge with reset low.
	await RisingEdge(clock)  # R1.
	await FallingEdge(clock)  # F1.
	await ReadOnly()

	sending = cocotb.start_soon(source.send(7))
	received = await sink.recv()
	await sending
	assert str(received.data) == "00000111"

	await source.close()
	await sink.close()

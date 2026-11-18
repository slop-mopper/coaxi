# interleaved.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.2-sol

"""Receive two interleaved packets in completion order."""

import cocotb
from cocotb.clock import Clock
from cocotb.types import Logic, LogicArray
from cocotb.handle import HierarchyObject

from coaxi import AxiStreamBus, AxiStreamSidebands, AxiStreamSink, AxiStreamSource, to_unsigned


def vector_int(value: Logic | LogicArray | None) -> int:
	assert isinstance(value, LogicArray)
	return to_unsigned(value)


@cocotb.test(timeout_time=1000, timeout_unit="ns")
async def interleaved(dut: HierarchyObject) -> None:
	clock = dut.beat_clock
	cocotb.start_soon(Clock(clock, 10, unit="ns").start(start_high=False))
	bus = AxiStreamBus.bind(dut, prefix="sb", last=True, id=True, keep=True, strb=True)
	source = AxiStreamSource(bus, clock)
	sink = AxiStreamSink(bus, clock)
	await source.initialise()
	await sink.initialise()

	async def send_packets() -> None:
		await source.send(0xA1A0, last=False, sidebands=AxiStreamSidebands(id=1))
		await source.send(0x00B0, last=True, sidebands=AxiStreamSidebands(id=2, keep=0b01))
		await source.send(0x00A2, last=True, sidebands=AxiStreamSidebands(id=1, keep=0b01))

	sending = cocotb.start_soon(send_packets())
	packet_b = await sink.recv_frame(max_transfers=2)
	packet_a = await sink.recv_frame(max_transfers=2)
	await sending

	assert [vector_int(beat.id) for beat in packet_b] == [2]
	assert [vector_int(beat.id) for beat in packet_a] == [1, 1]
	assert [vector_int(beat.data) for beat in packet_a] == [0xA1A0, 0x00A2]
	assert [vector_int(beat.keep) for beat in packet_a] == [0b11, 0b01]
	assert vector_int(packet_b[0].data) == 0x00B0
	assert vector_int(packet_b[0].keep) == vector_int(packet_b[0].strb) == 0b01

	await source.close()
	await sink.close()

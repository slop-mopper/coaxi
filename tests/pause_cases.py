# pause_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.2-sol

"""Cycle-level checks for repeating and one-pass AXI-Stream pauses."""

from typing import Literal
from collections.abc import Iterator

import cocotb
import pytest
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject
from cocotb.triggers import Timer

from coaxi import AxiStreamBus, AxiStreamSidebands, AxiStreamSink, AxiStreamSource, TransferReset


def _bus(dut: HierarchyObject, *, ready: Literal[False] | None = None) -> AxiStreamBus:
	return AxiStreamBus.bind(dut, prefix="sb", ready=ready, last=True, keep=True, user=True, id=True)


async def _edge(dut: HierarchyObject, high: bool) -> None:
	dut.beat_clock.value = int(high)
	await Timer(1, unit="ns")


async def _cycle(dut: HierarchyObject) -> None:
	await _edge(dut, True)
	await _edge(dut, False)


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def repeating_source_pattern(dut: HierarchyObject) -> None:
	"""Pausing gates new offers without changing a stalled beat or losing frame data."""
	bus = _bus(dut)
	source = AxiStreamSource(bus, dut.beat_clock)
	pattern = [1, 0, 1, 1, 0, 0]
	source.set_pause_generator(pattern)
	pattern[:] = [0]  # Installation copies the sequence.
	init = cocotb.start_soon(source.initialise())
	await _cycle(dut)
	await init
	assert int(bus.valid.value) == 0

	dut.sb_tready.value = 0
	sending = cocotb.start_soon(
		source.send_frame(
			[0x1234, 0x5678, 0x9ABC],
			sidebands=[
				AxiStreamSidebands(keep=3, user=5, id=7),
				AxiStreamSidebands(keep=2, user=6, id=7),
				AxiStreamSidebands(keep=1, user=7, id=7),
			],
		)
	)
	await _cycle(dut)  # Sample 1: no new offer.
	assert int(bus.valid.value) == 0
	await _cycle(dut)  # Sample 0: offer the first beat, with ready low.
	assert _offer(dut) == (1, 0x1234, 0, 3, 5, 7)
	await _cycle(dut)  # Sample 1 cannot retract or alter the offer.
	assert _offer(dut) == (1, 0x1234, 0, 3, 5, 7)
	dut.sb_tready.value = 1
	await _cycle(dut)  # Accept the first beat, then sample 1.
	assert _offer(dut) == (0, 0x1234, 0, 3, 5, 7)
	await _cycle(dut)  # Sample 0: offer the next beat.
	assert _offer(dut) == (1, 0x5678, 0, 2, 6, 7)
	await _cycle(dut)  # Sample 0: new beat on the cleanup edge.
	assert _offer(dut) == (1, 0x9ABC, 1, 1, 7, 7)
	await _cycle(dut)  # Accept the final beat; pattern wraps to 1.
	assert sending.done()
	await sending
	assert int(bus.valid.value) == 0

	sending = cocotb.start_soon(source.send(42, last=True))
	await _cycle(dut)  # Wrapped sample 0 permits the first offer.
	assert int(bus.valid.value) == 1
	await _cycle(dut)
	await sending


def _offer(dut: HierarchyObject) -> tuple[int, ...]:
	return tuple(
		int(handle.value)
		for handle in (dut.sb_tvalid, dut.sb_tdata, dut.sb_tlast, dut.sb_tkeep, dut.sb_tuser, dut.sb_tid)
	)


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def sink_generator_and_replacement(dut: HierarchyObject) -> None:
	"""A yield generator advances while idle and replacement and clearing take effect on a drive."""
	bus = _bus(dut)
	sink = AxiStreamSink(bus, dut.beat_clock)
	reads: list[bool] = []

	def pauses() -> Iterator[bool]:
		while True:
			for value in (False, True, True):
				reads.append(value)
				yield value

	def finite() -> Iterator[int]:
		yield 0
		yield 1

	sink.set_pause_generator(pauses())
	init = cocotb.start_soon(sink.initialise())
	await _cycle(dut)
	await init
	assert reads == []
	await _cycle(dut)
	assert reads == [False]
	assert int(dut.sb_tready.value) == 0  # Idle even when the sample allows traffic.

	receiving = cocotb.start_soon(sink.recv_frame())
	dut.sb_tvalid.value = "X"  # While paused, valid does not describe an accepted beat.
	await _cycle(dut)
	assert reads == [False, True]
	assert int(dut.sb_tready.value) == 0
	await _cycle(dut)
	assert reads == [False, True, True]
	assert int(dut.sb_tready.value) == 0

	sink.set_pause_generator(finite())
	dut.sb_tvalid.value = 1
	dut.sb_tdata.value = 10
	await _cycle(dut)  # Allow the first beat.
	assert int(dut.sb_tready.value) == 1
	await _cycle(dut)  # Accept first beat, then hold ready low for the next one.
	assert int(dut.sb_tready.value) == 0
	dut.sb_tlast.value = 1
	dut.sb_tdata.value = 20
	await _cycle(dut)  # The one-pass iterator finishes and unpauses.
	assert int(dut.sb_tready.value) == 1
	await _cycle(dut)
	frame = await receiving
	assert len(frame) == 2
	for transfer, data, last in zip(frame, (10, 20), (False, True), strict=True):
		assert isinstance(transfer.data, LogicArray)
		assert int(transfer.data) == data and transfer.last is last
	assert reads == [False, True, True]  # Replacement stopped the infinite generator.
	assert int(dut.sb_tready.value) == 0

	sink.set_pause_generator([True])
	receiving_one = cocotb.start_soon(sink.recv())
	await _cycle(dut)
	assert int(dut.sb_tready.value) == 0 and not receiving_one.done()
	sink.set_pause_generator(None)
	await _cycle(dut)
	assert int(dut.sb_tready.value) == 1
	await _cycle(dut)
	await receiving_one


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def simultaneous_pauses_through_register(dut: HierarchyObject) -> None:
	"""The DUT sees only handshakes allowed by the two independent patterns."""
	source = AxiStreamSource(AxiStreamBus.bind(dut, prefix="s", last=True), dut.beat_clock)
	sink = AxiStreamSink(AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True), dut.beat_clock)
	source.set_pause_generator([False, True, False])
	sink.set_pause_generator((True, False, False))
	init_source = cocotb.start_soon(source.initialise())
	init_sink = cocotb.start_soon(sink.initialise())
	await _cycle(dut)
	await init_source
	await init_sink
	dut.wipe_registers.value = 0
	dut.allow_input.value = 1
	sending = cocotb.start_soon(source.send_frame([11, 22, 33]))
	receiving = cocotb.start_soon(sink.recv_frame())

	for accepted, retired in [(0, 0), (1, 0), (1, 1), (2, 1), (2, 1), (3, 2), (3, 3)]:
		await _edge(dut, True)
		assert (int(dut.accepted.value), int(dut.retired.value)) == (accepted, retired)
		await _edge(dut, False)
	await sending
	frame = await receiving
	assert len(frame) == 3
	for transfer, data, last in zip(frame, [11, 22, 33], [False, False, True], strict=True):
		assert isinstance(transfer.data, LogicArray)
		assert int(transfer.data) == data and transfer.last is last


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def pattern_without_ready(dut: HierarchyObject) -> None:
	"""A source can insert gaps without ready, but a sink cannot stall the wire."""
	bus = _bus(dut, ready=False)
	source = AxiStreamSource(bus, dut.beat_clock)
	sink = AxiStreamSink(bus, dut.beat_clock)
	with pytest.raises(ValueError, match="requires a ready"):
		sink.set_pause_generator([False])
	sink.set_pause_generator()
	init_source = cocotb.start_soon(source.initialise())
	init_sink = cocotb.start_soon(sink.initialise())
	await _cycle(dut)
	await init_source
	await init_sink
	source.set_pause_generator([True])
	with pytest.raises(ValueError, match="must be bool, 0, or 1"):
		source.set_pause_generator([False, 2])
	sending = cocotb.start_soon(source.send(99, last=True))
	await _cycle(dut)
	assert int(bus.valid.value) == 0
	source.set_pause_generator([])
	await _cycle(dut)
	assert int(bus.valid.value) == 1
	await _cycle(dut)
	await sending
	transfer = await sink.recv()
	assert isinstance(transfer.data, LogicArray) and int(transfer.data) == 99
	assert transfer.last is True


@cocotb.test(timeout_time=2000, timeout_unit="ns")
@cocotb.parametrize(use_sink=[False, True])
async def reset_and_close(dut: HierarchyObject, use_sink: bool) -> None:
	"""Reset suspends the iterator; release resumes it, and close forgets it."""
	bus = _bus(dut)
	reset = dut.reset_lane
	reset.value = 0
	await Timer(1, unit="ns")
	source = AxiStreamSource(bus, dut.beat_clock, reset=reset, reset_active_high=True)
	sink = AxiStreamSink(bus, dut.beat_clock, reset=reset, reset_active_high=True)
	endpoint = sink if use_sink else source
	reads: list[int] = []

	def pauses() -> Iterator[bool]:
		while True:
			reads.append(len(reads))
			yield True

	async def transfer_until_reset() -> None:
		with pytest.raises(TransferReset):
			if use_sink:
				await sink.recv()
			else:
				await source.send(1, last=True)

	endpoint.set_pause_generator(pauses())
	init = cocotb.start_soon(endpoint.initialise())
	await _cycle(dut)  # R0
	await _cycle(dut)  # R1, F1
	await init
	transfer = cocotb.start_soon(transfer_until_reset())
	await _cycle(dut)
	assert reads == [0]
	reset.value = 1
	await Timer(1, unit="ns")  # Interrupt a paused operation with the clock stopped.
	assert transfer.done()
	await transfer
	await _cycle(dut)
	await _edge(dut, True)
	reset.value = 0
	await _edge(dut, False)
	await _cycle(dut)  # R0
	await _cycle(dut)  # R1, F1
	assert reads == [0]
	await _cycle(dut)  # R2
	assert reads == [0, 1]

	init = cocotb.start_soon(endpoint.initialise())
	await _cycle(dut)
	await _cycle(dut)
	await init
	assert reads == [0, 1]
	await _cycle(dut)
	assert reads == [0, 1, 2]
	closing = cocotb.start_soon(endpoint.close())
	await _cycle(dut)
	await closing
	init = cocotb.start_soon(endpoint.initialise())
	for _ in range(4):
		await _cycle(dut)
	await init
	assert reads == [0, 1, 2]


@cocotb.test(timeout_time=2000, timeout_unit="ns")
@cocotb.parametrize(active=[False, True], invalid_value=[False, True])
async def iterator_fault(dut: HierarchyObject, active: bool, invalid_value: bool) -> None:
	"""Iterator errors surface through the transfer API, including when sampled idle."""
	source = AxiStreamSource(_bus(dut), dut.beat_clock)
	dut.sb_tready.value = 1

	def broken() -> Iterator[bool | int]:
		yield True
		if invalid_value:
			yield 2
		else:
			raise RuntimeError("pause iterator failed")

	async def fail_send() -> None:
		exception, message = (
			(ValueError, "must be bool, 0, or 1") if invalid_value else (RuntimeError, "pause iterator failed")
		)
		with pytest.raises(exception, match=message):
			await source.send(1, last=True)

	source.set_pause_generator(broken())
	init = cocotb.start_soon(source.initialise())
	await _cycle(dut)
	await init
	sending = cocotb.start_soon(fail_send()) if active else None
	await _cycle(dut)
	await _cycle(dut)
	if sending is not None:
		assert sending.done()
		await sending
	await fail_send()
	assert int(dut.sb_tvalid.value) == 0

	init = cocotb.start_soon(source.initialise())
	await _cycle(dut)
	await init
	recovery = cocotb.start_soon(source.send(2, last=True))
	await _cycle(dut)
	assert int(dut.sb_tvalid.value) == 1
	await _cycle(dut)
	await recovery

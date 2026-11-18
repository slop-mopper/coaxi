# reset_pin_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Reset polarity, asynchronous safety, release gates and lifecycle ownership."""

from typing import Any
from asyncio import CancelledError
from itertools import pairwise
from collections.abc import Coroutine

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject, LogicObject, LogicArrayObject
from cocotb.simtime import get_sim_time
from cocotb.triggers import Event, Timer, ReadOnly, RisingEdge, FallingEdge

from coaxi import (
	AxiStreamBus,
	AxiStreamSink,
	AxiStreamSource,
	AxiStreamSidebands,
	AxiStreamTransfer,
	EndpointStateError,
	HandlePayload,
	PayloadValue,
	ProtocolValueError,
	SignalBindingError,
	TransferReset,
)


async def _result[T](operation: Coroutine[Any, Any, T]) -> T | Exception:
	try:
		return await operation
	except Exception as exc:
		return exc


def _pin(dut: HierarchyObject, high: bool) -> LogicObject | LogicArrayObject:
	return dut.reset_lane if high else next(child for child in dut if child._name == "\\recover-now!\\")


def _bus(dut: HierarchyObject, *, ready: bool = True) -> AxiStreamBus:
	return AxiStreamBus.bind(dut, prefix="sb", ready=None if ready else False, last=True, keep=True, user=True, id=True)


async def _setup(dut: HierarchyObject) -> None:
	dut.beat_clock.value = 0
	dut.wipe_registers.value = 1
	dut.allow_input.value = 0
	dut.sb_tvalid.value = 0
	dut.sb_tready.value = 0
	dut.plain_valid.value = 0
	dut.plain_ready.value = 0
	dut.reset_lane.value = 0
	_pin(dut, False).value = 1
	await Timer(1, unit="ns")


async def _edge(dut: HierarchyObject, high: bool) -> None:
	dut.beat_clock.value = int(high)
	await Timer(1, unit="ns")


async def _release(dut: HierarchyObject, high: bool) -> None:
	"""Deassert after a rising edge, then observe R0, R1 and F1."""
	await RisingEdge(dut.beat_clock)
	_pin(dut, high).value = int(not high)
	for _ in range(3):
		await FallingEdge(dut.beat_clock)
	await Timer(1, unit="ns")


def _number(transfer: AxiStreamTransfer[PayloadValue | None]) -> int:
	assert isinstance(transfer.data, LogicArray)
	return transfer.data.to_unsigned()


@cocotb.test(timeout_time=5000, timeout_unit="ns")
@cocotb.parametrize(high=[False, True])
async def release_gate(dut: HierarchyObject, high: bool) -> None:
	"""Held reset clears at a stopped clock; no-ready capture starts only after F1."""
	await _setup(dut)
	pin = _pin(dut, high)
	pin.value = int(high)
	dut.sb_tdata.value = 0xFFFF
	dut.sb_tvalid.value = 1
	dut.sb_tlast.value = 1
	dut.sb_tkeep.value = 3
	dut.sb_tuser.value = 4
	dut.sb_tid.value = 1
	sink = AxiStreamSink(_bus(dut, ready=False), "beat_clock", reset=pin, reset_active_high=high)
	initialising = cocotb.start_soon(sink.initialise())
	await Timer(1, unit="ns")
	assert not initialising.done()
	assert str(pin.value) == str(int(high))  # Monitoring never drives the pin.
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await _edge(dut, True)  # Last rising edge with reset held.
	pin.value = int(not high)
	await _edge(dut, False)
	await _edge(dut, True)  # R0.
	assert not initialising.done() and sink._retained == 0
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await _edge(dut, False)
	await _edge(dut, True)  # R1.
	assert not initialising.done() and sink._retained == 0
	await _edge(dut, False)  # F1: capture is armed, nothing accepted yet.
	await initialising
	assert sink._retained == 0
	await _edge(dut, True)  # R2: exactly one acceptance.
	assert sink._retained == 1
	await _edge(dut, False)
	assert _number(await sink.recv()) == 0xFFFF
	assert sink._retained == 0
	await sink.close()


@cocotb.test(timeout_time=5000, timeout_unit="ns")
@cocotb.parametrize(high=[False, True])
async def stopped_clock_assertion(dut: HierarchyObject, high: bool) -> None:
	"""Assertion interrupts stalled source and ready-backed sink without a clock edge."""
	await _setup(dut)
	clock = cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	pin = _pin(dut, high)
	source = AxiStreamSource(_bus(dut), "beat_clock", reset=pin, reset_active_high=high)
	sink = AxiStreamSink(
		AxiStreamBus.bind(dut, prefix="plain", t_prefix=False), "beat_clock", reset=pin, reset_active_high=high
	)
	await source.initialise()
	await sink.initialise()
	sending = cocotb.start_soon(_result(source.send(0xDEAD, last=True, sidebands=AxiStreamSidebands(user=7))))
	receiving = cocotb.start_soon(_result(sink.recv()))
	await FallingEdge(dut.beat_clock)
	await Timer(1, unit="ns")
	assert int(dut.sb_tvalid.value) == int(dut.plain_ready.value) == 1
	clock.cancel()
	when = get_sim_time(unit="ns")
	pin.value = int(high)
	await Timer(1, unit="ns")
	assert sending.done() and receiving.done()
	assert isinstance(await sending, TransferReset) and isinstance(await receiving, TransferReset)
	assert get_sim_time(unit="ns") == when + 1
	assert int(dut.sb_tvalid.value) == int(dut.sb_tdata.value) == int(dut.sb_tlast.value) == 0
	assert int(dut.sb_tkeep.value) == int(dut.sb_tuser.value) == int(dut.plain_ready.value) == 0
	with pytest.raises(EndpointStateError):
		await source.send(3, last=True)
	clock = cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	await _release(dut, high)
	dut.sb_tready.value = 1
	await source.send(12, last=True)
	dut.plain_valid.value = 1
	dut.plain_data.value = 34
	assert _number(await sink.recv()) == 34
	await source.close()
	await sink.close()
	clock.cancel()


@cocotb.test(timeout_time=20000, timeout_unit="ns")
async def registered_full_rate(dut: HierarchyObject) -> None:
	"""Pin-aware edge races must still sample before registered HDL updates, every cycle."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	source = AxiStreamSource(
		AxiStreamBus.bind(dut, prefix="s", last=True), "beat_clock", reset="wipe_registers", reset_active_high=True
	)
	sink = AxiStreamSink(
		AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True),
		"beat_clock",
		reset=dut.wipe_registers,
		reset_active_high=True,
	)
	start_source = cocotb.start_soon(source.initialise())
	start_sink = cocotb.start_soon(sink.initialise())
	await RisingEdge(dut.beat_clock)
	dut.wipe_registers.value = 0
	await start_source
	await start_sink
	dut.allow_input.value = 1
	inputs: list[int] = []
	outputs: list[int] = []
	values = list(range(128))

	async def monitor() -> None:
		while True:
			await RisingEdge(dut.beat_clock)
			if int(dut.s_tvalid.value) and int(dut.s_tready.value):
				inputs.append(int(get_sim_time(unit="ns")))
			if int(dut.m_valid.value) and int(dut.m_ready.value):
				outputs.append(int(get_sim_time(unit="ns")))

	async def transmit() -> None:
		for index in range(0, 128, 8):
			await source.send_frame(values[index : index + 8])

	async def receive() -> list[int]:
		result: list[int] = []
		for _ in range(16):
			frame = await sink.recv_frame()
			assert [transfer.last for transfer in frame] == [False] * 7 + [True]
			result.extend(_number(transfer) for transfer in frame)
		return result

	monitor_task = cocotb.start_soon(monitor())
	sending = cocotb.start_soon(transmit())
	assert await receive() == values
	await sending
	monitor_task.cancel()
	assert len(inputs) == len(outputs) == 128
	assert all(b - a == 10 for a, b in pairwise(inputs)), inputs
	assert all(b - a == 10 for a, b in pairwise(outputs)), outputs
	assert int(dut.accepted.value) == int(dut.retired.value) == 128
	await source.close()
	await sink.close()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(high=[False, True])
async def capture_fault_and_recovery(dut: HierarchyObject, high: bool) -> None:
	"""Pin cycles discard backlog but do not acknowledge overflow or subsequent reset faults."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	pin = _pin(dut, high)
	sink = AxiStreamSink(_bus(dut, ready=False), "beat_clock", buffer_capacity=1, reset=pin, reset_active_high=high)
	await sink.initialise()
	dut.sb_tkeep.value = 3
	dut.sb_tlast.value = 1
	dut.sb_tvalid.value = 1
	for _ in range(3):
		await FallingEdge(dut.beat_clock)
	with pytest.raises(OverflowError) as first:
		await sink.recv()
	dut.sb_tvalid.value = 0
	pin.value = "X"
	await Timer(1, unit="ns")
	with pytest.raises(OverflowError) as again:
		await sink.recv()
	assert again.value is first.value
	pin.value = int(high)
	await Timer(1, unit="ns")
	assert sink._retained == 0
	await _release(dut, high)
	with pytest.raises(OverflowError):
		await sink.recv()
	await sink.initialise()
	dut.sb_tdata.value = 43
	dut.sb_tvalid.value = 1
	await RisingEdge(dut.beat_clock)
	await FallingEdge(dut.beat_clock)
	dut.sb_tvalid.value = 0
	assert _number(await sink.recv()) == 43
	await sink.close()
	pin.value = int(high)
	await Timer(1, unit="ns")
	await _release(dut, high)
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await sink.initialise()
	await sink.close()


@cocotb.test(timeout_time=1000, timeout_unit="ns")
async def initial_reset_write_pending(dut: HierarchyObject) -> None:
	"""A queued VHDL write cannot hide an unresolved initial reset sample."""
	pin = dut.startup_reset
	assert str(pin.value) == "U"
	source = AxiStreamSource(_bus(dut), "beat_clock", reset=pin, reset_active_high=True)
	Clock(dut.beat_clock, 10, unit="ns").start(start_high=False)
	pin.value = 1
	with pytest.raises(ProtocolValueError, match="startup_reset.*got U") as first:
		await source.initialise()

	await Timer(1, unit="ns")
	assert str(pin.value) == "1"
	await RisingEdge(dut.beat_clock)
	pin.value = 0
	for _ in range(3):
		await FallingEdge(dut.beat_clock)
	with pytest.raises(ProtocolValueError) as again:
		await source.send(1, last=True)
	assert again.value is first.value

	await source.initialise()
	await source.close()


@cocotb.test(timeout_time=5000, timeout_unit="ns")
@cocotb.parametrize(value=["X", "U", "L", "H", "Z"])
async def invalid_pin(dut: HierarchyObject, value: str) -> None:
	"""Nonliteral reset values latch a protocol error and require manual recovery."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	source = AxiStreamSource(_bus(dut), "beat_clock", reset="\\recover-now!\\")
	await source.initialise()
	_pin(dut, False).value = value
	await Timer(1, unit="ns")
	with pytest.raises(ProtocolValueError, match="reset"):
		await source.send(1, last=True)
	await _release(dut, False)
	with pytest.raises(ProtocolValueError):
		await source.send(1, last=True)
	await source.initialise()
	await source.close()


@cocotb.test(timeout_time=5000, timeout_unit="ns")
async def readonly_and_cancelled_initialise(dut: HierarchyObject) -> None:
	"""Deferred clearing schedules progress with a stopped clock and survives cancellation."""
	await _setup(dut)
	pin = _pin(dut, False)
	pin.value = 0
	dut.sb_tvalid.value = 1
	dut.sb_tdata.value = 0xFFFF
	source = AxiStreamSource(_bus(dut), "beat_clock", reset=pin)
	await ReadOnly()
	initialising = cocotb.start_soon(source.initialise())
	await Timer(2, unit="step")
	assert int(dut.sb_tvalid.value) == int(dut.sb_tdata.value) == 0
	assert not initialising.done()
	with pytest.raises(EndpointStateError):
		await source.initialise()
	with pytest.raises(EndpointStateError):
		await source.close()
	initialising.cancel()
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	await _release(dut, False)
	with pytest.raises(EndpointStateError):
		await source.send(1, last=True)
	await source.initialise()
	await source.close()


@cocotb.test(timeout_time=5000, timeout_unit="ns")
async def binding_validation(dut: HierarchyObject) -> None:
	"""Validate reset handles and polarity without driving any signals."""
	await _setup(dut)
	bus = _bus(dut)
	for reset in ("no-such-signal", "beat_clock", "sb_tvalid", "sb_tdata"):
		with pytest.raises(SignalBindingError):
			AxiStreamSource(bus, "beat_clock", reset=reset)
	with pytest.raises(TypeError):
		AxiStreamSink(bus, "beat_clock", reset_active_high=1)  # type: ignore[bad-argument-type]
	assert not hasattr(AxiStreamSource(bus, "beat_clock"), "reset")


@cocotb.test(timeout_time=5000, timeout_unit="ns")
@cocotb.parametrize(after_r1=[False, True])
async def reassert_during_release(dut: HierarchyObject, after_r1: bool) -> None:
	"""An obsolete gate cannot enable capture or source valid after reassertion."""
	await _setup(dut)
	pin = _pin(dut, False)
	pin.value = 0
	source = AxiStreamSource(_bus(dut), "beat_clock", reset=pin)
	sink = AxiStreamSink(_bus(dut, ready=False), "beat_clock", reset=pin)
	initialising_source = cocotb.start_soon(source.initialise())
	initialising_sink = cocotb.start_soon(sink.initialise())
	await _edge(dut, True)
	pin.value = 1
	await _edge(dut, False)
	await _edge(dut, True)  # R0 of the obsolete release.
	if after_r1:
		await _edge(dut, False)
		await _edge(dut, True)  # R1 of the obsolete release.
	pin.value = 0
	await _edge(dut, False)
	await _edge(dut, True)
	await _edge(dut, False)  # Past the obsolete release's F1.
	assert not initialising_source.done() and not initialising_sink.done()
	assert int(dut.sb_tvalid.value) == 0 and sink._retained == 0
	with pytest.raises(EndpointStateError):
		await source.send(1, last=True)
	await _edge(dut, True)
	pin.value = 1
	await _edge(dut, False)
	await _edge(dut, True)  # Replacement R0.
	assert not initialising_source.done() and not initialising_sink.done()
	await _edge(dut, False)
	await _edge(dut, True)  # Replacement R1.
	assert not initialising_source.done() and not initialising_sink.done()
	await _edge(dut, False)
	await initialising_source
	await initialising_sink
	assert sink._retained == 0 and int(dut.sb_tvalid.value) == 0
	await sink.close()
	closing = cocotb.start_soon(source.close())
	await _edge(dut, True)
	await _edge(dut, False)
	await closing
	# Neither stale gates nor later pin transitions may reopen a closed source.
	pin.value = 0
	await _edge(dut, True)
	pin.value = 1
	for _ in range(3):
		await _edge(dut, False)
		await _edge(dut, True)
	with pytest.raises(EndpointStateError):
		await source.send(2, last=True)


@cocotb.test(timeout_time=5000, timeout_unit="ns")
@cocotb.parametrize(ready=[False, True])
async def interruption_after_acceptance(dut: HierarchyObject, ready: bool) -> None:
	"""Accepted A is interrupted before cleanup; only replacement B is later delivered."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	pin = _pin(dut, False)
	source = AxiStreamSource(_bus(dut, ready=ready), "beat_clock", reset=pin)
	sink = AxiStreamSink(_bus(dut, ready=ready), "beat_clock", reset=pin, buffer_capacity=None if ready else 1)
	await source.initialise()
	await sink.initialise()
	accepted: list[int] = []
	observed = Event()

	async def monitor() -> None:
		while True:
			await RisingEdge(dut.beat_clock)
			if int(dut.sb_tvalid.value) and (not ready or int(dut.sb_tready.value)):
				accepted.append(int(dut.sb_tdata.value))
				observed.set()

	watching = cocotb.start_soon(monitor())
	sending = cocotb.start_soon(_result(source.send(11, last=True)))
	receiving = cocotb.start_soon(_result(sink.recv()))
	await observed.wait()
	await Timer(1, unit="ns")  # Accepted, but not yet cleaned up/published.
	assert accepted == [11]
	pin.value = 0
	await Timer(1, unit="ns")
	assert isinstance(await sending, TransferReset)
	assert isinstance(await receiving, TransferReset)
	assert sink._retained == 0 and not sink._packets
	await _release(dut, False)
	sending_b = cocotb.start_soon(source.send(77, last=True))
	assert _number(await sink.recv()) == 77
	await sending_b
	assert accepted == [11, 77]  # A was neither undone nor replayed.
	assert sink._retained == 0
	watching.cancel()
	await source.close()
	await sink.close()


@cocotb.test(timeout_time=5000, timeout_unit="ns")
async def prior_cancellation_and_clear_fault(dut: HierarchyObject) -> None:
	"""Cancellation and a first latched fault survive pin cycles and adapter-clear failures."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	pin = _pin(dut, False)

	class SwitchPayload:
		def __init__(self) -> None:
			self.fail = False
			self.handle = HandlePayload(dut.sb_tdata)

		def drive(self, value: int) -> None:
			self.handle.drive(value)

		def read(self) -> int:
			return int(dut.sb_tdata.value)

		def clear(self) -> None:
			if self.fail:
				raise RuntimeError("injected clear failure")
			self.handle.clear()

	payload = SwitchPayload()
	source = AxiStreamSource(_bus(dut), "beat_clock", reset=pin, payload=payload)
	await source.initialise()
	sending = cocotb.start_soon(source.send(8, last=True))
	await FallingEdge(dut.beat_clock)
	await Timer(1, unit="ns")
	sending.cancel()
	with pytest.raises(CancelledError):
		await sending
	pin.value = 0
	await Timer(1, unit="ns")
	await _release(dut, False)
	with pytest.raises(EndpointStateError):
		await source.send(9, last=True)
	await source.initialise()
	# Invalid pin is the first latched fault; subsequent clear failures cannot replace it.
	pin.value = "X"
	await Timer(1, unit="ns")
	with pytest.raises(ProtocolValueError) as first:
		await source.send(10, last=True)
	payload.fail = True
	dut.sb_tvalid.value = 1
	dut.sb_tlast.value = 1
	dut.sb_tuser.value = 15
	pin.value = 0
	await Timer(1, unit="ns")
	assert int(dut.sb_tvalid.value) == int(dut.sb_tlast.value) == int(dut.sb_tuser.value) == 0
	await _release(dut, False)
	with pytest.raises(ProtocolValueError) as again:
		await source.send(11, last=True)
	assert again.value is first.value
	payload.fail = False
	await source.initialise()
	dut.sb_tready.value = 1
	await source.send(12, last=True)
	await source.close()


@cocotb.test(timeout_time=5000, timeout_unit="ns")
async def stale_foreground_operation(dut: HierarchyObject) -> None:
	"""A delayed old source resumes only after a new generation owns distinctive outputs."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	pin = _pin(dut, False)
	parked = Event()
	release_old = Event()

	class DelayedSource(AxiStreamSource[PayloadValue | None]):
		park = True

		async def _start_edge(self) -> None:
			await super()._start_edge()
			if self.park:
				self.park = False
				parked.set()
				await release_old.wait()

	source = DelayedSource(_bus(dut), "beat_clock", reset=pin)
	await source.initialise()
	old = cocotb.start_soon(_result(source.send(11, last=True)))
	await parked.wait()
	pin.value = 0
	await Timer(1, unit="ns")
	await _release(dut, False)
	new = cocotb.start_soon(source.send(77, last=True, sidebands=AxiStreamSidebands(user=5)))
	await FallingEdge(dut.beat_clock)
	await Timer(1, unit="ns")
	assert int(dut.sb_tvalid.value) == 1 and int(dut.sb_tdata.value) == 77
	release_old.set()
	assert isinstance(await old, TransferReset)
	assert not new.done()
	assert int(dut.sb_tvalid.value) == 1 and int(dut.sb_tdata.value) == 77 and int(dut.sb_tuser.value) == 5
	dut.sb_tready.value = 1
	await new
	await source.close()


@cocotb.test(timeout_time=5000, timeout_unit="ns")
@cocotb.parametrize(high=[False, True], after_acceptance=[False, True])
async def collector_observes_reset_first(dut: HierarchyObject, high: bool, after_acceptance: bool) -> None:
	"""Collector-first pin observation must discard state and wake a receiver without self-cancellation."""
	await _setup(dut)
	pin = _pin(dut, high)
	watch_allowed = Event()

	class DelayedWatcher(AxiStreamSink[PayloadValue | None]):
		async def _watch_reset(self, generation: object) -> None:
			# Force the collector's real pin-observation fallback before the
			# watcher can handle the same change, independently of callback order.
			await watch_allowed.wait()
			await super()._watch_reset(generation)

	sink = DelayedWatcher(_bus(dut, ready=False), "beat_clock", reset=pin, reset_active_high=high)
	initialising = cocotb.start_soon(sink.initialise())
	await Timer(1, unit="ns")
	for level in (True, False, True, False):  # Initial R0, R1 and F1.
		await _edge(dut, level)
	await initialising

	dut.sb_tkeep.value = 3
	dut.sb_tdata.value = 11
	dut.sb_tid.value = 1
	dut.sb_tlast.value = 0
	dut.sb_tvalid.value = 1
	packet = cocotb.start_soon(_result(sink.recv_frame()))
	await _edge(dut, True)
	await _edge(dut, False)
	assert not packet.done()
	assert sink._retained == 1 and len(sink._packets[(1, 0)]) == 1

	dut.sb_tdata.value = 22
	if after_acceptance:
		await _edge(dut, True)
		assert sink._retained == 2  # One prefix plus one unpublished snapshot.
	pin.value = int(high)
	await _edge(dut, not after_acceptance)
	# Stop the clock here and hold reset. No later pin edge may mask a lost
	# notification, stale prefix or failure to schedule the reset-cycle task.
	await Timer(2, unit="ns")
	assert packet.done(), "collector-first assertion did not wake the pending packet receive"
	assert isinstance(await packet, TransferReset)
	assert not sink._packets and not sink._queue and sink._retained == 0
	assert sink._capture_task is None and sink._capture_generation is None
	assert sink._fault is None
	with pytest.raises(EndpointStateError):
		await sink.recv()

	dut.sb_tvalid.value = 0
	watch_allowed.set()
	await _edge(dut, True)
	pin.value = int(not high)
	for level in (False, True, False, True, False):  # Replacement R0, R1 and F1.
		await _edge(dut, level)
	dut.sb_tdata.value = 77
	dut.sb_tlast.value = 1
	dut.sb_tvalid.value = 1
	await _edge(dut, True)
	await _edge(dut, False)
	dut.sb_tvalid.value = 0
	assert [_number(beat) for beat in await sink.recv_frame()] == [77]
	assert sink._retained == 0
	await sink.close()


@cocotb.test(timeout_time=5000, timeout_unit="ns")
async def stopped_no_ready_packet(dut: HierarchyObject) -> None:
	"""Pin assertion wakes a clock-stopped packet receive and discards its retained prefix."""
	await _setup(dut)
	clock = cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	pin = _pin(dut, False)
	source = AxiStreamSource(_bus(dut, ready=False), "beat_clock", reset=pin)
	sink = AxiStreamSink(_bus(dut, ready=False), "beat_clock", reset=pin, buffer_capacity=2)
	await source.initialise()
	await sink.initialise()
	packet = cocotb.start_soon(_result(sink.recv_frame()))
	await source.send(11, last=False, sidebands=AxiStreamSidebands(id=1))
	await Timer(1, unit="ns")
	assert not packet.done()
	assert sink._retained == 1 and len(sink._packets[(1, 0)]) == 1
	clock.cancel()
	pin.value = 0
	await Timer(1, unit="ns")
	assert packet.done() and isinstance(await packet, TransferReset)
	assert not sink._packets and not sink._queue and sink._retained == 0
	clock = cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	await _release(dut, False)
	sending = cocotb.start_soon(source.send(77, last=True, sidebands=AxiStreamSidebands(id=1)))
	assert [_number(beat) for beat in await sink.recv_frame()] == [77]
	await sending
	assert sink._retained == 0
	await sink.close()
	await source.close()
	clock.cancel()

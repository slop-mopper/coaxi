# audit_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Static-review and coverage-guided regressions with observable failure contracts."""

from typing import Any, cast
from asyncio import CancelledError
from collections.abc import Coroutine

import cocotb
import pytest
import coaxi._stream as stream_module
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject
from cocotb.triggers import Timer, ReadOnly, NullTrigger, RisingEdge, FallingEdge

from coaxi import (
	AxiStreamBus,
	AxiStreamSink,
	AxiStreamSource,
	AxiStreamSidebands,
	EndpointStateError,
	HandlePayload,
	SignalBindingError,
)


async def _result[T](operation: Coroutine[Any, Any, T]) -> T | Exception:
	try:
		return await operation
	except Exception as exc:
		return exc


async def _setup(dut: HierarchyObject) -> None:
	dut.beat_clock.value = 0
	dut.reset_lane.value = 0
	dut.sb_tvalid.value = 0
	dut.sb_tready.value = 0
	dut.wipe_registers.value = 1
	await Timer(1, unit="ns")


def _bus(dut: HierarchyObject) -> AxiStreamBus:
	return AxiStreamBus.bind(dut, prefix="sb", last=True, keep=True, strb=True, user=True, id=True, dest=True)


@cocotb.test(timeout_time=1000, timeout_unit="ns")
async def immutable_reset_rejected(dut: HierarchyObject) -> None:
	"""Reject a reset that cannot arm ValueChange before starting any background task."""
	await _setup(dut)
	assert dut.fixed_reset.is_const
	for endpoint in (AxiStreamSource, AxiStreamSink):
		with pytest.raises(SignalBindingError, match="reset.*(mutable|immutable|constant)"):
			endpoint(_bus(dut), dut.beat_clock, reset=dut.fixed_reset)


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def watcher_fault_delivered_to_initialise(dut: HierarchyObject) -> None:
	"""A failed trigger registration must reach the awaiting caller, not kill cocotb."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	source = AxiStreamSource(_bus(dut), dut.beat_clock, reset=dut.reset_lane, reset_active_high=True)
	failure = RuntimeError("injected reset callback registration failure")

	def broken_trigger(handle: object) -> Any:
		raise failure

	with pytest.MonkeyPatch.context() as patch:
		patch.setattr(stream_module, "ValueChange", broken_trigger)
		with pytest.raises(RuntimeError) as caught:
			await source.initialise()
		assert caught.value is failure
		with pytest.raises(RuntimeError) as again:
			await source.send(1, last=True)
		assert again.value is failure
	# The watcher stopped on failure. Restoring the hook and cycling the pin
	# must not acknowledge the fault; initialise() must restart monitoring.
	await Timer(1, unit="step")
	dut.reset_lane.value = 1
	await Timer(1, unit="ns")
	dut.reset_lane.value = 0
	for _ in range(4):
		await FallingEdge(dut.beat_clock)
	with pytest.raises(RuntimeError) as after:
		await source.send(1, last=True)
	assert after.value is failure
	await source.initialise()
	await source.wait_available()
	dut.sb_tready.value = 1
	await source.send(73, last=True)
	await source.close()


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def record_validation_is_atomic_and_identifies_leaf(dut: HierarchyObject) -> None:
	"""A bad second field reports its path and leaves every field unchanged."""
	await _setup(dut)
	payload = HandlePayload(dut.iq_word_in)
	payload.drive({"i": 123, "q": 456})
	await Timer(1, unit="ns")
	before = payload.read()
	for invalid, exception in ((1 << 16, ValueError), ("X", ValueError), (-1, ValueError), (None, TypeError)):
		with pytest.raises(exception, match=r"iq_word_in.q") as failure:
			payload.drive({"i": 999, "q": cast(Any, invalid)})
		assert type(failure.value) is exception
		if invalid == 1 << 16 or invalid == "X":
			assert type(failure.value.__cause__) is exception
		await Timer(1, unit="ns")
		assert payload.read() == before
	# A valid signed record still uses independent LogicArray snapshots.
	payload.drive({"i": LogicArray.from_signed(-12, 16), "q": LogicArray.from_signed(34, 16)})
	await Timer(1, unit="ns")
	assert payload.read() == {"i": LogicArray.from_signed(-12, 16), "q": LogicArray.from_signed(34, 16)}
	assert before == {"i": LogicArray.from_unsigned(123, 16), "q": LogicArray.from_unsigned(456, 16)}


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def sideband_errors_identify_signal(dut: HierarchyObject) -> None:
	"""Conversion errors identify metadata rather than resembling payload width errors."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	source = AxiStreamSource(_bus(dut), dut.beat_clock)
	await source.initialise()
	for value in (32, "X", -1):
		with pytest.raises(ValueError, match="user.*sb_tuser") as failure:
			await source.send(42, last=True, sidebands=AxiStreamSidebands(user=value))
		assert type(failure.value) is ValueError
		if value != -1:
			assert type(failure.value.__cause__) is ValueError
		assert str(dut.sb_tvalid.value) == "0"
	with pytest.raises(TypeError, match="sidebands"):
		await source.send(42, last=True, sidebands=cast(Any, 42))
	dut.sb_tready.value = 1
	await source.send(42, last=True)
	await source.close()


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def mutable_logic_sidebands_are_snapshots(dut: HierarchyObject) -> None:
	"""LogicArray metadata is copied at drive/read, independent of subsequent caller mutation."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	bus = _bus(dut)
	source, sink = AxiStreamSource(bus, dut.beat_clock), AxiStreamSink(bus, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	user = LogicArray("XU01Z")
	metadata = AxiStreamSidebands(keep=LogicArray("XU"), user=user)
	sending = cocotb.start_soon(source.send(42, last=True, sidebands=metadata))
	transfer = await sink.recv()
	await sending
	user[4] = "1"  # Mutating after the operation finishes is explicitly permitted.
	assert str(transfer.user) == "XU01Z" and str(transfer.keep) == "XU"
	assert str(dut.sb_tuser.value) == "XU01Z"
	sending = cocotb.start_soon(source.send(43, last=True, sidebands=metadata))
	next_transfer = await sink.recv()
	await sending
	assert str(next_transfer.user) == "1U01Z"
	assert str(transfer.user) == "XU01Z"
	await source.close()
	await sink.close()


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def frame_identity_error_identifies_entry(dut: HierarchyObject) -> None:
	"""Changing packet identity after an accepted prefix reports the entry and needs recovery."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	bus = _bus(dut)
	source = AxiStreamSource(bus, dut.beat_clock)
	await source.initialise()
	dut.sb_tready.value = 1
	accepted: list[tuple[int, str]] = []

	async def monitor() -> None:
		while True:
			await RisingEdge(dut.beat_clock)
			if str(dut.sb_tvalid.value) == "1":
				accepted.append((int(dut.sb_tdata.value), str(dut.sb_tlast.value)))

	watching = cocotb.start_soon(monitor())
	with pytest.raises(ValueError, match=r"entry 1.*\(1, 0\).*\(2, 0\)"):
		await source.send_frame([11, 22], sidebands=[AxiStreamSidebands(id=1), AxiStreamSidebands(id=2)])
	for _ in range(3):
		await RisingEdge(dut.beat_clock)
	assert accepted == [(11, "0")]
	with pytest.raises(EndpointStateError):
		await source.send(33, last=True)
	watching.cancel()
	await source.initialise()
	await source.send(44, last=True)
	await source.close()


@cocotb.test(timeout_time=4000, timeout_unit="ns")
@cocotb.parametrize(unresolved=[False, True])
async def mixed_receive_capacity_conservation(dut: HierarchyObject, unresolved: bool) -> None:
	"""Raw disposal frees exactly its retained prefix, or all prefixes for unknown identity."""
	await _setup(dut)
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	bus = AxiStreamBus.bind(dut, prefix="sb", ready=False, last=True, id=True)
	source = AxiStreamSource(bus, dut.beat_clock)
	sink = AxiStreamSink(bus, dut.beat_clock, buffer_capacity=5)
	await source.initialise()
	await sink.initialise()
	for value, identifier, last in ((11, 1, False), (21, 2, False), (31, 3, True)):
		await source.send(value, last=last, sidebands=AxiStreamSidebands(id=identifier))
	await Timer(1, unit="ns")
	assert [int(str(t.data), 2) for t in await sink.recv_frame()] == [31]
	assert sink._retained == 2
	await source.send(12, last=True, sidebands=AxiStreamSidebands(id="X0000000000" if unresolved else 1))
	await Timer(1, unit="ns")
	assert int(str((await sink.recv()).data), 2) == 12
	retained = 0 if unresolved else 1
	assert sink._retained == retained
	assert set(sink._packets) == (set() if unresolved else {(2, 0)})
	for value in range(5 - retained):
		await source.send(40 + value, last=True, sidebands=AxiStreamSidebands(id=3))
	await Timer(1, unit="ns")
	assert sink._retained == 5 and sink._fault is None
	await source.send(99, last=True)
	await Timer(1, unit="ns")
	with pytest.raises(OverflowError):
		await sink.recv()
	await sink.initialise()
	assert sink._retained == 0 and not sink._packets
	await source.send(123, last=True)
	assert int(str((await sink.recv()).data), 2) == 123
	await sink.close()
	await source.close()


@cocotb.test(timeout_time=4000, timeout_unit="ns")
async def stale_pin_cycle_cannot_clear_replacement(dut: HierarchyObject) -> None:
	"""Exercise ownership guards independently of normal task cancellation."""
	await _setup(dut)
	clock = cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	source = AxiStreamSource(_bus(dut), dut.beat_clock, reset=dut.reset_lane, reset_active_high=True)
	await source.initialise()
	await source.wait_available()
	clock.cancel()
	old_generation, old_cycle = source._monitor_generation, source._pin_cycle
	assert old_generation is not None and old_cycle is not None
	# Deliberately unregistered replay: real pin transitions cancel their own
	# task, but this one tests the post-await ownership guard independently.
	replay = cocotb.start_soon(source._settle_reset(old_generation, old_cycle, True))
	await Timer(1, unit="ns")
	dut.reset_lane.value = 1
	await Timer(1, unit="ns")
	assert source._pin_cycle is not old_cycle
	dut.beat_clock.value = 1
	await Timer(1, unit="ns")
	assert replay.done()
	await replay
	assert not source._pin_ready
	with pytest.raises(EndpointStateError):
		await source.send(12, last=True)
	dut.reset_lane.value = 0
	clock = cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	await source.initialise()
	await source.wait_available()
	sending = cocotb.start_soon(source.send(0xDEAD, last=True, sidebands=AxiStreamSidebands(user=7)))
	await FallingEdge(dut.beat_clock)
	await Timer(1, unit="ns")
	clock.cancel()
	assert int(dut.sb_tvalid.value) == 1
	assert int(dut.sb_tdata.value) == 0xDEAD and int(dut.sb_tuser.value) == 7
	# This stale replay must return before its first clear, without any edge.
	replay = cocotb.start_soon(source._settle_reset(old_generation, old_cycle, True))
	await Timer(1, unit="ns")
	assert replay.done() and not sending.done()
	await replay
	assert int(dut.sb_tvalid.value) == 1
	assert int(dut.sb_tdata.value) == 0xDEAD and int(dut.sb_tuser.value) == 7
	dut.sb_tready.value = 1
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	await sending
	await source.close()


@cocotb.test(timeout_time=4000, timeout_unit="ns")
async def cancelled_initialise_keeps_deferred_safety_clear(dut: HierarchyObject) -> None:
	"""Cancelling before a ReadOnly safety clear must not cancel the armed monitor."""
	await _setup(dut)
	dut.reset_lane.value = 1
	dut.sb_tvalid.value = 1
	dut.sb_tdata.value = "X" * 16
	source = AxiStreamSource(_bus(dut), dut.beat_clock, reset=dut.reset_lane, reset_active_high=True)
	await ReadOnly()
	initialising = cocotb.start_soon(source.initialise())
	await NullTrigger()
	initialising.cancel()
	with pytest.raises(CancelledError):
		await initialising
	await Timer(1, unit="ns")
	assert int(dut.sb_tvalid.value) == int(dut.sb_tdata.value) == 0
	dut.reset_lane.value = 0
	await Timer(1, unit="ns")
	# Reassert at the still-stopped clock with fault-injected output sentinels.
	# A surviving deferred clear alone cannot satisfy this second assertion:
	# the watcher itself must remain armed after cancellation.
	dut.sb_tvalid.value = 1
	dut.sb_tdata.value = 0xDEAD
	await Timer(1, unit="ns")
	dut.reset_lane.value = 1
	await Timer(1, unit="ns")
	assert int(dut.sb_tvalid.value) == int(dut.sb_tdata.value) == 0
	dut.reset_lane.value = 0
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	for _ in range(4):
		await FallingEdge(dut.beat_clock)
	with pytest.raises(EndpointStateError):
		await source.send(1, last=True)
	await source.initialise()
	await source.wait_available()
	dut.sb_tready.value = 1
	await source.send(2, last=True)
	await source.close()

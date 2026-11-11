# omission_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Optional data/ready, continuous capture, capacity and capture lifetime."""

from typing import Any
from asyncio import CancelledError
from collections.abc import Coroutine

import cocotb
import pytest
from cocotb.task import Task
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject
from cocotb.simtime import get_sim_time
from cocotb.triggers import Event, Timer, RisingEdge, FallingEdge

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


async def _setup(dut: HierarchyObject) -> Task[None]:
	clock_task = cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	await FallingEdge(dut.beat_clock)
	dut.wipe_registers.value = 1
	dut.allow_input.value = 0
	dut.s_tvalid.value = 0
	dut.m_ready.value = 0
	dut.sb_tvalid.value = 0
	dut.sb_tready.value = 0
	dut.plain_valid.value = 0
	dut.plain_ready.value = 0
	dut.sample_available.value = 0
	dut.consumer_accepts.value = 0
	await FallingEdge(dut.beat_clock)
	dut.wipe_registers.value = 0
	return clock_task


def _bus(dut: HierarchyObject, *, data: bool = True, ready: bool = False) -> AxiStreamBus:
	return AxiStreamBus.bind(
		dut,
		prefix="sb",
		data=None if data else False,
		ready=None if ready else False,
		last=True,
		keep=True,
		user=True,
		id=True,
		dest=True,
	)


async def _result[T](operation: Coroutine[Any, Any, T]) -> T | Exception:
	try:
		return await operation
	except Exception as exc:
		return exc


async def _wire(dut: HierarchyObject, values: list[tuple[int, bool, int]], *, keep: int = 3) -> None:
	"""Drive an independent no-ready peer, one new value on each falling edge."""
	for data, last, identity in values:
		await FallingEdge(dut.beat_clock)
		dut.sb_tdata.value = data
		dut.sb_tlast.value = int(last)
		dut.sb_tid.value = identity
		dut.sb_tdest.value = 0
		dut.sb_tuser.value = data & 15
		dut.sb_tkeep.value = keep
		dut.sb_tvalid.value = 1
	await FallingEdge(dut.beat_clock)
	dut.sb_tvalid.value = 0


def _number(transfer: AxiStreamTransfer[PayloadValue | None]) -> int:
	assert isinstance(transfer.data, LogicArray)
	return transfer.data.to_unsigned()


@cocotb.test(timeout_time=20000, timeout_unit="ns")
@cocotb.parametrize(data=[False, True], ready=[False, True])
async def presence_combinations(dut: HierarchyObject, data: bool, ready: bool) -> None:
	"""Support all data/ready combinations without making optional signals mandatory."""
	await _setup(dut)
	bus = _bus(dut, data=data, ready=ready)
	assert (bus.data is not None) is data and (bus.ready is not None) is ready
	source = AxiStreamSource(bus, "beat_clock")
	sink = AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()
	dut.sb_tdata.value = 0xCAFE
	dut.sb_tready.value = int(not ready)
	samples = list(range(64)) if data else [None] * 64
	accepted: list[int] = []

	async def monitor() -> None:
		for cycle in range(100):
			await RisingEdge(dut.beat_clock)
			if str(dut.sb_tvalid.value) == "1" and (not ready or str(dut.sb_tready.value) == "1"):
				accepted.append(cycle)
				if len(accepted) == len(samples):
					return
		raise AssertionError("burst did not complete")

	monitoring = cocotb.start_soon(monitor())
	sending = cocotb.start_soon(source.send_frame(samples))
	frame = await sink.recv_frame()
	await sending
	await monitoring
	assert accepted == list(range(accepted[0], accepted[0] + len(samples)))
	assert [item.last for item in frame] == [False] * 63 + [True]
	assert all(str(item.keep) == "11" for item in frame)
	if data:
		assert [_number(item) for item in frame] == samples
	else:
		assert all(item.data is None for item in frame)
		assert int(dut.sb_tdata.value) == 0xCAFE
		sending = cocotb.start_soon(source.send(None, last=True, sidebands=AxiStreamSidebands(keep=0)))
		value = await sink.recv()
		await sending
		assert value.data is None and value.last is True and str(value.keep) == "00"
	if not ready:
		assert str(dut.sb_tready.value) == "1"
	await sink.close()


@cocotb.test(timeout_time=3000, timeout_unit="ns")
async def omission_validation(dut: HierarchyObject) -> None:
	"""Use explicit selectors; keep without data defines its own lane width."""
	await _setup(dut)
	bus = AxiStreamBus.bind(dut, prefix="not_present", valid=dut.sb_tvalid, data=False, ready=False)
	assert bus.data is None and bus.ready is None
	assert AxiStreamBus(None, dut.sb_tvalid, None).data is None
	for role in ("data", "ready"):
		with pytest.raises(SignalBindingError):
			AxiStreamBus.bind(dut, prefix="not_present", **{role: True})
	with pytest.raises(SignalBindingError, match="strb requires"):
		AxiStreamBus.bind(dut, prefix="sb", data=False, strb=True)
	with pytest.raises(SignalBindingError):
		AxiStreamBus.bind(dut, prefix="sb", data=False, keep=dut.iq_word_in)
	adapter = HandlePayload(dut.sb_tdata)
	for endpoint in (AxiStreamSource, AxiStreamSink):
		with pytest.raises(ValueError, match="adapter requires"):
			endpoint(bus, "beat_clock", payload=adapter)
	for capacity in (0, -1):
		with pytest.raises(ValueError):
			AxiStreamSink(bus, "beat_clock", buffer_capacity=capacity)
	for capacity in (True, 1.5):
		with pytest.raises(TypeError):
			AxiStreamSink(bus, "beat_clock", buffer_capacity=capacity)  # type: ignore
	with pytest.raises(ValueError, match="without ready"):
		AxiStreamSink(_bus(dut, ready=True), "beat_clock", buffer_capacity=1)
	source = AxiStreamSource(bus, "beat_clock")
	await source.reset()
	with pytest.raises(ValueError, match="requires data=None"):
		await source.send(1)
	with pytest.raises(EndpointStateError):
		await source.send(None)
	await source.reset()
	await source.send(None)


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def idle_capture_and_live_timing(dut: HierarchyObject) -> None:
	"""Drain backlog in one step, but complete a waiting live read at cleanup."""
	await _setup(dut)
	sink = AxiStreamSink(_bus(dut), "beat_clock")
	await _wire(dut, [(99, True, 0)])
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await sink.reset()
	values = [(7, False, 0), (7, False, 1), (9, True, 0), (10, True, 1)]
	await _wire(dut, values)
	await Timer(1, unit="ns")
	start = get_sim_time(unit="step")
	raw = [await sink.recv() for _ in values]
	assert get_sim_time(unit="step") == start
	assert [_number(item) for item in raw] == [7, 7, 9, 10]
	assert [int(str(item.id), 2) for item in raw] == [0, 1, 0, 1]

	async def live() -> None:
		value = await sink.recv()
		assert _number(value) == 21
		assert str(dut.beat_clock.value) == "0"
		assert int(get_sim_time(unit="ns")) % 10 == 0

	receiving = cocotb.start_soon(live())
	await _wire(dut, [(21, True, 0)])
	await receiving
	receiving = cocotb.start_soon(live())
	await Timer(31, unit="ns")
	assert not receiving.done()
	await _wire(dut, [(21, True, 0)])
	await receiving
	await sink.close()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def registered_idle_capture(dut: HierarchyObject) -> None:
	"""Snapshot pre-update registered data on every valid edge while Python is idle."""
	await _setup(dut)
	source = AxiStreamSource(AxiStreamBus.bind(dut, prefix="s", last=True), "beat_clock")
	sink = AxiStreamSink(AxiStreamBus.bind(dut, prefix="m", t_prefix=False, ready=False, last=True), "beat_clock")
	await source.reset()
	await sink.reset()
	dut.m_ready.value = 1
	dut.allow_input.value = 1
	values = list(range(128))
	await source.send_frame(values)
	await Timer(11, unit="ns")
	start = get_sim_time(unit="step")
	frame = await sink.recv_frame()
	assert get_sim_time(unit="step") == start
	assert [_number(item) for item in frame] == values
	assert [item.last for item in frame] == [False] * 127 + [True]
	await sink.close()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def capacity_and_interleaving(dut: HierarchyObject) -> None:
	"""Capacity covers queued and partial packets, releasing only on delivery."""
	await _setup(dut)
	bus = _bus(dut)
	for capacity in (2, 3):
		sink = AxiStreamSink(bus, "beat_clock", buffer_capacity=capacity)
		await sink.reset()
		receiving = cocotb.start_soon(_result(sink.recv_frame()))
		await _wire(dut, [(1, False, 0), (2, False, 1), (3, True, 0)])
		result = await receiving
		if capacity == 2:
			assert isinstance(result, OverflowError), result
			with pytest.raises(OverflowError):
				await sink.recv()
		else:
			assert isinstance(result, list)
			assert [_number(item) for item in result] == [1, 3]
			await _wire(dut, [(4, True, 1), (5, True, 2)])
			assert [_number(item) for item in await sink.recv_frame()] == [2, 4]
			assert [_number(item) for item in await sink.recv_frame()] == [5]
		await sink.close()
	sink = AxiStreamSink(bus, "beat_clock", buffer_capacity=2)
	await sink.reset()
	await _wire(dut, [(11, True, 0), (12, True, 0)])
	await Timer(1, unit="ns")
	assert _number(await sink.recv()) == 11
	await _wire(dut, [(13, True, 0), (14, True, 0)])
	await Timer(1, unit="ns")
	with pytest.raises(OverflowError):
		await sink.recv_frame()
	await sink.reset()
	await _wire(dut, [(15, True, 0)])
	await Timer(1, unit="ns")
	assert _number(await sink.recv()) == 15
	await sink.close()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def queued_packet_mixing_and_limits(dut: HierarchyObject) -> None:
	"""Reconcile raw/frame APIs and limits with an independent capture lifetime."""
	await _setup(dut)
	sink = AxiStreamSink(_bus(dut), "beat_clock", buffer_capacity=6)
	await sink.reset()
	await _wire(dut, [(1, False, 0), (2, True, 1), (3, True, 0), (4, True, 0)])
	await Timer(1, unit="ns")
	assert [_number(item) for item in await sink.recv_frame()] == [2]
	assert _number(await sink.recv()) == 3
	assert [_number(item) for item in await sink.recv_frame()] == [4]
	await _wire(dut, [(5, False, 0), (6, False, 0), (7, True, 0)])
	await Timer(1, unit="ns")
	with pytest.raises(ValueError, match="did not end"):
		await sink.recv_frame(max_transfers=2)
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await sink.reset()
	await _wire(dut, [(8, False, 0), (9, True, 0)])
	await Timer(1, unit="ns")
	assert len(await sink.recv_frame(max_transfers=2)) == 2
	await sink.close()


class _FailingPayload:
	def __init__(self, dut: HierarchyObject) -> None:
		self.access = HandlePayload(dut.sb_tdata)
		self.fail = False
		self.reads = 0

	def read(self) -> PayloadValue:
		self.reads += 1
		if self.fail:
			raise RuntimeError("injected capture read failure")
		return self.access.read()

	def drive(self, value: PayloadValue) -> None:
		self.access.drive(value)

	def clear(self) -> None:
		self.access.clear()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(fault=["valid", "last", "qualifiers", "adapter"], waiting=[False, True])
async def capture_faults(dut: HierarchyObject, fault: str, waiting: bool) -> None:
	"""Latch background failures for error-first delivery, with or without a waiter."""
	await _setup(dut)
	bus = AxiStreamBus.bind(dut, prefix="sb", ready=False, last=True, keep=True, strb=True)
	adapter = _FailingPayload(dut)
	sink = AxiStreamSink(bus, "beat_clock", payload=adapter)
	await sink.reset()
	dut.sb_tstrb.value = 3
	await _wire(dut, [(1, True, 0)])
	await Timer(1, unit="ns")
	if waiting:
		assert str((await sink.recv()).data) == f"{1:016b}"
		receiving = cocotb.start_soon(_result(sink.recv()))
	else:
		receiving = None
	await FallingEdge(dut.beat_clock)
	dut.sb_tvalid.value = "X" if fault == "valid" else 1
	dut.sb_tlast.value = "U" if fault == "last" else 1
	dut.sb_tkeep.value = 0 if fault == "qualifiers" else 3
	adapter.fail = fault == "adapter"
	await Timer(31, unit="ns")
	expected = RuntimeError if fault == "adapter" else ProtocolValueError
	if receiving is not None:
		assert isinstance(await receiving, expected)
	with pytest.raises(expected):
		await sink.recv()
	with pytest.raises(expected):
		await sink.recv_frame()
	reads = adapter.reads
	await Timer(20, unit="ns")
	assert adapter.reads == reads
	await FallingEdge(dut.beat_clock)
	dut.sb_tvalid.value = 0
	adapter.fail = False
	await sink.reset()
	dut.sb_tstrb.value = 3
	await _wire(dut, [(2, True, 0)])
	await Timer(1, unit="ns")
	assert str((await sink.recv()).data) == f"{2:016b}"
	await sink.close()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def close_reset_and_cancellation(dut: HierarchyObject) -> None:
	"""Stop/restart capture, wake pending reads, and leave cancelled resets stopped."""
	await _setup(dut)
	adapter = _FailingPayload(dut)
	sink = AxiStreamSink(_bus(dut), "beat_clock", payload=adapter)
	await sink.reset()
	pending = cocotb.start_soon(_result(sink.recv()))
	await Timer(1, unit="ns")
	with pytest.raises(EndpointStateError):
		await sink.recv()
	with pytest.raises(ValueError):
		await sink.recv_frame(max_transfers=0)
	await sink.close()
	assert isinstance(await pending, TransferReset)
	await sink.close()
	reads = adapter.reads
	await _wire(dut, [(1, True, 0)])
	assert adapter.reads == reads
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await sink.reset()
	pending = cocotb.start_soon(sink.recv())
	await Timer(1, unit="ns")
	pending.cancel()
	with pytest.raises(CancelledError):
		await pending
	await _wire(dut, [(2, True, 0)])
	assert adapter.reads == reads
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await sink.reset()
	pending = cocotb.start_soon(_result(sink.recv()))
	await Timer(1, unit="ns")
	resetting = cocotb.start_soon(sink.reset())
	await Timer(1, unit="ns")
	assert isinstance(await pending, TransferReset)
	with pytest.raises(EndpointStateError):
		await sink.close()
	resetting.cancel()
	with pytest.raises(CancelledError):
		await resetting
	await _wire(dut, [(3, True, 0)])
	assert adapter.reads == reads
	await sink.reset()
	await _wire(dut, [(4, True, 0)])
	await Timer(1, unit="ns")
	assert str((await sink.recv()).data) == f"{4:016b}"
	await sink.close()


class _GatedSink(AxiStreamSink[PayloadValue | None]):
	def __init__(self, bus: AxiStreamBus) -> None:
		super().__init__(bus, "beat_clock", buffer_capacity=1)
		self.entered = Event()
		self.release = Event()
		self.hold = True

	async def _recv_one(self, token: object) -> AxiStreamTransfer[PayloadValue | None]:
		value = await super()._recv_one(token)
		if self.hold:
			self.hold = False
			self.entered.set()
			await self.release.wait()
		return value


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def in_flight_capacity_and_stale_task(dut: HierarchyObject) -> None:
	"""In-flight snapshots count; an old receive cannot deliver/decrement new state."""
	await _setup(dut)
	sink = _GatedSink(_bus(dut))
	await sink.reset()
	pending = cocotb.start_soon(_result(sink.recv()))
	await _wire(dut, [(1, True, 0)])
	await sink.entered.wait()
	await _wire(dut, [(2, True, 0)])
	await Timer(1, unit="ns")
	sink.release.set()
	assert isinstance(await pending, OverflowError)
	await sink.reset()
	sink.hold = True
	sink.entered.clear()
	sink.release.clear()
	pending = cocotb.start_soon(_result(sink.recv_frame()))
	await _wire(dut, [(3, True, 0)])
	await sink.entered.wait()
	await sink.close()
	await sink.reset()
	new = cocotb.start_soon(_result(sink.recv()))
	await _wire(dut, [(4, True, 0)])
	sink.release.set()
	assert isinstance(await pending, TransferReset)
	replacement = await new
	assert isinstance(replacement, AxiStreamTransfer) and _number(replacement) == 4
	await _wire(dut, [(5, True, 0)])
	await Timer(1, unit="ns")
	assert _number(await sink.recv()) == 5
	await sink.close()


@cocotb.test(timeout_time=3000, timeout_unit="ns")
@cocotb.parametrize(action=["reset", "close"])
async def invalidate_unpublished_capture(dut: HierarchyObject, action: str) -> None:
	"""Invalidate between acceptance and cleanup; old capture cannot leak or count."""
	await _setup(dut)
	sink = AxiStreamSink(_bus(dut), "beat_clock", buffer_capacity=1)
	await sink.reset()
	pending = cocotb.start_soon(_result(sink.recv()))
	await FallingEdge(dut.beat_clock)
	dut.sb_tvalid.value = 1
	dut.sb_tdata.value = 99
	await RisingEdge(dut.beat_clock)
	await Timer(1, unit="ns")
	shutdown = cocotb.start_soon(sink.reset() if action == "reset" else sink.close())
	await Timer(1, unit="ns")
	dut.sb_tvalid.value = 0
	assert isinstance(await pending, TransferReset)
	await shutdown
	if action == "close":
		await sink.reset()
	await _wire(dut, [(1, True, 0)])
	await Timer(1, unit="ns")
	assert _number(await sink.recv()) == 1
	await _wire(dut, [(2, True, 0)])
	await Timer(1, unit="ns")
	assert _number(await sink.recv()) == 2
	await sink.close()


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def close_without_clock(dut: HierarchyObject) -> None:
	"""Closing an empty capture wakes its receiver without another clock edge."""
	clock_task = await _setup(dut)
	sink = AxiStreamSink(_bus(dut), "beat_clock")
	await sink.reset()
	pending = cocotb.start_soon(_result(sink.recv()))
	await Timer(1, unit="ns")
	clock_task.cancel()
	await Timer(1, unit="ns")
	now = get_sim_time(unit="step")
	await sink.close()
	await sink.close()
	assert isinstance(await pending, TransferReset)
	assert get_sim_time(unit="step") == now


@cocotb.test(timeout_time=3000, timeout_unit="ns")
async def no_ready_record_snapshots(dut: HierarchyObject) -> None:
	"""Idle capture keeps record leaves independent and preserves meta-values."""
	await _setup(dut)
	bus = AxiStreamBus.bind(dut, data="iq_word_in", valid="sample_available", ready=False, last="end_of_packet")
	source = AxiStreamSource(bus, "beat_clock")
	sink = AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()
	await source.send_frame([{"i": 12, "q": 21}, {"i": "X000000000000001", "q": 0}])
	await Timer(1, unit="ns")
	now = get_sim_time(unit="step")
	frame = await sink.recv_frame()
	assert get_sim_time(unit="step") == now
	first, second = frame[0].data, frame[1].data
	assert isinstance(first, dict) and isinstance(second, dict)
	assert int(str(first["i"]), 2) == 12 and int(str(first["q"]), 2) == 21
	assert str(second["i"]) == "X000000000000001"
	await sink.close()


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def none_requires_absent_data(dut: HierarchyObject) -> None:
	"""Nullable default typing does not turn None into a vector meta-value."""
	await _setup(dut)
	source = AxiStreamSource(_bus(dut), "beat_clock")
	await source.reset()
	with pytest.raises(TypeError, match="None requires"):
		await source.send(None, last=True)
	await source.reset()
	assert int(dut.sb_tdata.value) == 0

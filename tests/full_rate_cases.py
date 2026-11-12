# full_rate_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Cycle-counted full-rate tests, with independent peers and writable-phase guards."""

from random import Random
from asyncio import CancelledError
from collections.abc import Mapping

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject
from cocotb.simtime import get_sim_time
from cocotb.triggers import Timer, ReadOnly, ReadWrite, RisingEdge, FallingEdge

from coaxi import (
	AxiStreamBus,
	AxiStreamSink,
	AxiStreamSource,
	AxiStreamTransfer,
	EndpointStateError,
	HandlePayload,
	PayloadValue,
	TransferReset,
	to_signed,
	to_unsigned,
)


async def _setup(dut: HierarchyObject) -> None:
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	await FallingEdge(dut.beat_clock)
	dut.wipe_registers.value = 1
	dut.allow_input.value = 0
	dut.s_tvalid.value = 0
	dut.m_ready.value = 0
	dut.plain_valid.value = 0
	dut.plain_ready.value = 0
	dut.sample_available.value = 0
	dut.consumer_accepts.value = 0
	await FallingEdge(dut.beat_clock)
	await FallingEdge(dut.beat_clock)
	dut.wipe_registers.value = 0


def _record(dut: HierarchyObject) -> AxiStreamBus:
	return AxiStreamBus.bind(
		dut, data="iq_word_in", valid="sample_available", ready="consumer_accepts", last="end_of_packet"
	)


def _array(value: PayloadValue) -> LogicArray:
	assert isinstance(value, LogicArray)
	return value


def _check_rate(cycles: list[int], count: int) -> None:
	assert len(cycles) == count
	assert cycles == list(range(cycles[0], cycles[0] + count)), cycles


async def _direct_burst[T](
	dut: HierarchyObject,
	bus: AxiStreamBus,
	source: AxiStreamSource[T],
	sink: AxiStreamSink[T],
	values: list[T],
	flags: list[bool | None],
) -> list[AxiStreamTransfer[T]]:
	await source.initialise()
	await sink.initialise()
	results: list[AxiStreamTransfer[T]] = []

	async def send_all() -> None:
		for value, last in zip(values, flags, strict=True):
			await source.send(value, last=last)
			assert str(dut.beat_clock.value) == "0"

	async def recv_all() -> None:
		for _ in values:
			results.append(await sink.recv())
			assert str(dut.beat_clock.value) == "0"

	sending = cocotb.start_soon(send_all())
	receiving = cocotb.start_soon(recv_all())
	cycles = []
	for cycle in range(len(values) + 6):
		await RisingEdge(dut.beat_clock)
		if str(bus.valid.value) == str(bus.ready.value) == "1":
			cycles.append(cycle)
	assert sending.done() and receiving.done(), "endpoint inserted idle cycles"
	await sending
	await receiving
	_check_rate(cycles, len(values))
	assert [result.last for result in results] == flags
	await ReadOnly()
	assert str(bus.valid.value) == str(bus.ready.value) == "0"
	if bus.last is not None:
		assert str(bus.last.value) == "0"
	return results


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def registered_full_rate(dut: HierarchyObject) -> None:
	"""Sustain 128 consecutive handshakes on both sides of a registered DUT."""
	await _setup(dut)
	source = AxiStreamSource(AxiStreamBus.bind(dut, prefix="s", last=True), "beat_clock")
	sink = AxiStreamSink(AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True), "beat_clock")
	await source.initialise()
	await sink.initialise()
	dut.allow_input.value = 1
	values = [(index * 71, index % 7 in (0, 5, 6)) for index in range(128)]

	async def send_all() -> None:
		for value, last in values:
			await source.send(value, last=last)

	async def recv_all() -> None:
		for value, last in values:
			transfer = await sink.recv()
			assert to_unsigned(_array(transfer.data)) == value
			assert transfer.last is last

	sending = cocotb.start_soon(send_all())
	receiving = cocotb.start_soon(recv_all())
	inputs: list[tuple[int, int, bool]] = []
	outputs: list[tuple[int, int, bool]] = []
	for cycle in range(len(values) + 8):
		await RisingEdge(dut.beat_clock)
		# Snapshot before the registered HDL path updates at this edge.
		if str(dut.s_tvalid.value) == str(dut.s_tready.value) == "1":
			inputs.append((cycle, int(dut.s_tdata.value), bool(int(dut.s_tlast.value))))
		if str(dut.m_valid.value) == str(dut.m_ready.value) == "1":
			outputs.append((cycle, int(dut.m_data.value), bool(int(dut.m_last.value))))
	assert sending.done() and receiving.done(), "endpoint inserted idle cycles"
	await sending
	await receiving
	assert [(value, last) for _, value, last in inputs] == values
	assert [(value, last) for _, value, last in outputs] == values
	_check_rate([cycle for cycle, _, _ in inputs], len(values))
	_check_rate([cycle for cycle, _, _ in outputs], len(values))
	assert [cycle for cycle, _, _ in outputs] == [cycle + 1 for cycle, _, _ in inputs]
	await ReadOnly()
	assert int(dut.accepted.value) == int(dut.retired.value) == len(values)
	assert str(dut.s_tvalid.value) == str(dut.m_ready.value) == str(dut.m_valid.value) == "0"


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def vector_and_record_full_rate(dut: HierarchyObject) -> None:
	"""Keep full rate for unframed vectors and framed records, including X/U."""
	await _setup(dut)
	bus = AxiStreamBus.bind(dut, prefix="plain", t_prefix=False)
	values: list[PayloadValue] = [f"{index:08b}" for index in range(64)]
	results = await _direct_burst(
		dut, bus, AxiStreamSource(bus, "beat_clock"), AxiStreamSink(bus, "beat_clock"), values, [None] * len(values)
	)
	assert [str(result.data) for result in results] == values

	bus = _record(dut)
	values = [
		{"i": str(LogicArray.from_signed(-index, 16)), "q": "XU00000000000001" if index % 7 == 0 else f"{index:016b}"}
		for index in range(64)
	]
	results = await _direct_burst(
		dut,
		bus,
		AxiStreamSource(bus, "beat_clock"),
		AxiStreamSink(bus, "beat_clock"),
		values,
		[index % 3 != 0 for index in range(len(values))],
	)
	for result, expected in zip(results, values, strict=True):
		assert isinstance(result.data, Mapping) and isinstance(expected, Mapping)
		assert {name: str(value) for name, value in result.data.items()} == expected


class _IQPayload:
	def __init__(self, handle: HierarchyObject) -> None:
		self._raw = HandlePayload(handle)

	def read(self) -> tuple[int, int]:
		"""Return an independent pair of signed application values."""
		value = self._raw.read()
		assert isinstance(value, Mapping)
		return to_signed(_array(value["i"])), to_signed(_array(value["q"]))

	def drive(self, value: tuple[int, int]) -> None:
		"""Drive a signed IQ pair without flattening the payload."""
		self._raw.drive({"i": LogicArray.from_signed(value[0], 16), "q": LogicArray.from_signed(value[1], 16)})

	def clear(self) -> None:
		"""Clear both fields."""
		self._raw.clear()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def custom_payload_full_rate(dut: HierarchyObject) -> None:
	"""Retain the generic adapter API when transfers use consecutive cycles."""
	await _setup(dut)
	bus = _record(dut)
	handle = bus.data
	assert isinstance(handle, HierarchyObject)
	source = AxiStreamSource(bus, "beat_clock", payload=_IQPayload(handle))
	sink = AxiStreamSink(bus, "beat_clock", payload=_IQPayload(handle))
	values = [(-32768 + index, 32767 - index) for index in range(64)]
	results = await _direct_burst(dut, bus, source, sink, values, [index % 4 == 0 for index in range(len(values))])
	assert [result.data for result in results] == values


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(reset_pin=[False, True])
async def source_backpressure(dut: HierarchyObject, reset_pin: bool) -> None:
	"""An independent receiver checks stability and immediate recovery from stalls."""
	await _setup(dut)
	bus = _record(dut)
	source = AxiStreamSource(bus, "beat_clock", reset=dut.reset_lane if reset_pin else None, reset_active_high=True)
	await source.initialise()
	count = 64

	async def send_all() -> None:
		for index in range(count):
			await source.send({"i": index, "q": count - index}, last=index % 3 == 0)

	sending = cocotb.start_soon(send_all())
	seed = 91823
	dut._log.debug("source_backpressure seed=%s", seed)
	rng = Random(seed)
	accepted = 0
	started = False
	stalled: tuple[int, int, bool] | None = None
	for cycle in range(300):
		await FallingEdge(dut.beat_clock)
		ready = cycle >= 4 and (cycle % 11 >= 3) and bool(rng.getrandbits(2))
		dut.consumer_accepts.value = int(ready)
		await RisingEdge(dut.beat_clock)
		valid = str(bus.valid.value) == "1"
		current = (int(dut.iq_word_in["i"].value), int(dut.iq_word_in["q"].value), bool(int(dut.end_of_packet.value)))
		if stalled is not None:
			assert valid and current == stalled
		started = started or valid
		if started:
			assert valid, "source inserted a bubble despite another pending value"
		if valid and ready:
			assert current == (accepted, count - accepted, accepted % 3 == 0)
			accepted += 1
		stalled = current if valid and not ready else None
		if accepted == count:
			break
	assert accepted == count
	await sending
	for _ in range(3):
		await RisingEdge(dut.beat_clock)
		assert str(bus.valid.value) == "0"  # No duplicate after the final return.
	await source.close()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(reset_pin=[False, True])
async def sink_source_gaps(dut: HierarchyObject, reset_pin: bool) -> None:
	"""An independent source checks continuous ready, even across source gaps."""
	await _setup(dut)
	bus = AxiStreamBus.bind(dut, prefix="plain", t_prefix=False)
	sink = AxiStreamSink(bus, "beat_clock", reset=dut.reset_lane if reset_pin else None, reset_active_high=True)
	await sink.initialise()
	count = 96

	async def recv_all() -> None:
		for expected in range(count):
			transfer = await sink.recv()
			assert to_unsigned(_array(transfer.data)) == expected
			assert transfer.last is None

	receiving = cocotb.start_soon(recv_all())
	seed = 72119
	dut._log.debug("sink_source_gaps seed=%s", seed)
	rng = Random(seed)
	accepted = 0
	for _ in range(300):
		await FallingEdge(dut.beat_clock)
		valid = bool(rng.getrandbits(2))
		dut.plain_valid.value = int(valid)
		dut.plain_data.value = accepted
		await RisingEdge(dut.beat_clock)
		assert str(bus.ready.value) == "1", "sink inserted a ready bubble"
		if valid:
			accepted += 1
		if accepted == count:
			break
	assert accepted == count
	await FallingEdge(dut.beat_clock)
	dut.plain_valid.value = 0
	await receiving
	for _ in range(3):
		await RisingEdge(dut.beat_clock)
		assert str(bus.ready.value) == "0"
	await sink.close()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def reuse_phase_guards(dut: HierarchyObject) -> None:
	"""Never drive using a cached edge after leaving its simulator callback."""
	await _setup(dut)
	bus = AxiStreamBus.bind(dut, prefix="plain", t_prefix=False)
	source, sink = AxiStreamSource(bus, "beat_clock"), AxiStreamSink(bus, "beat_clock")
	await source.initialise()
	await sink.initialise()
	dut.plain_ready.value = 1
	for phase in ("read_only", "read_write", "delay", "later_falling"):
		await source.send(1)
		previous = get_sim_time(unit="ns")
		if phase == "read_only":
			await ReadOnly()
		elif phase == "read_write":
			await ReadWrite()
		elif phase == "later_falling":
			await FallingEdge(dut.beat_clock)
		else:
			await Timer(1, unit="ns")
		await source.send(2)
		assert get_sim_time(unit="ns") - previous == (30 if phase == "later_falling" else 20)
	await FallingEdge(dut.beat_clock)
	dut.plain_ready.value = 0
	dut.plain_valid.value = 1
	# Reset must not grant permission to reuse its clearing edge.
	await sink.initialise()
	reset_at = get_sim_time(unit="ns")
	await sink.recv()
	assert get_sim_time(unit="ns") - reset_at == 20
	for phase in ("read_only", "read_write", "delay", "later_falling"):
		await sink.recv()
		previous = get_sim_time(unit="ns")
		if phase == "read_only":
			await ReadOnly()
		elif phase == "read_write":
			await ReadWrite()
		elif phase == "later_falling":
			await FallingEdge(dut.beat_clock)
		else:
			await Timer(1, unit="ns")
		await sink.recv()
		assert get_sim_time(unit="ns") - previous == (30 if phase == "later_falling" else 20)


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def chained_failure_and_reset(dut: HierarchyObject) -> None:
	"""A failing chained drive invalidates reuse; reset still takes a fresh edge."""
	await _setup(dut)
	bus = AxiStreamBus.bind(dut, prefix="plain", t_prefix=False)
	source = AxiStreamSource(bus, "beat_clock")
	await source.initialise()
	dut.plain_ready.value = 1
	await source.send(1)
	completed = get_sim_time(unit="ns")
	with pytest.raises(ValueError):
		await source.send(256)
	assert get_sim_time(unit="ns") == completed  # The failing call used the same edge.
	with pytest.raises(EndpointStateError):
		await source.send(2)
	await source.initialise()
	assert get_sim_time(unit="ns") == completed + 10
	await source.send(3)  # Successful reset must not itself create a reusable edge.
	assert get_sim_time(unit="ns") == completed + 30
	await ReadOnly()
	assert str(bus.valid.value) == "0"
	assert int(bus.data.value) == 3


class _ReadFailure(HandlePayload):
	fail_next: bool = False

	def read(self) -> PayloadValue:
		"""Inject a one-off adapter failure on an accepted transfer."""
		if self.fail_next:
			self.fail_next = False
			raise RuntimeError("injected chained read failure")
		return super().read()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(interruption=["read_failure", "cancel", "reset"])
async def interrupted_full_rate_receive(dut: HierarchyObject, interruption: str) -> None:
	"""Recover mid-burst without undoing acceptance or discarding buffered data."""
	await _setup(dut)
	source = AxiStreamSource(AxiStreamBus.bind(dut, prefix="s", last=True), "beat_clock")
	sink_bus = AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True)
	payload = _ReadFailure(sink_bus.data)
	sink = AxiStreamSink(sink_bus, "beat_clock", payload=payload)
	await source.initialise()
	await sink.initialise()
	dut.allow_input.value = 1
	prefix = 8
	values = [(index * 71, index % 3 == 0) for index in range(prefix + 2)]
	results: list[tuple[int, bool | None]] = []
	errors: list[RuntimeError] = []

	async def send_all() -> None:
		for value, last in values:
			await source.send(value, last=last)

	async def receive_prefix() -> None:
		for _ in range(prefix):
			transfer = await sink.recv()
			results.append((to_unsigned(_array(transfer.data)), transfer.last))
		payload.fail_next = interruption == "read_failure"
		try:
			await sink.recv()
		except RuntimeError as exc:
			# Catch inside the spawned task, including TransferReset.
			errors.append(exc)

	sending = cocotb.start_soon(send_all())
	receiving = cocotb.start_soon(receive_prefix())
	cycles = []
	for cycle in range(prefix + 6):
		await RisingEdge(dut.beat_clock)
		if str(dut.m_valid.value) == str(dut.m_ready.value) == "1":
			cycles.append(cycle)
		if len(cycles) == prefix + 1:
			break
	_check_rate(cycles, prefix + 1)
	await Timer(1, unit="ns")  # Accepted, but the chained operation has not returned.
	assert results == values[:prefix]
	assert int(dut.retired.value) == prefix + 1
	assert int(dut.accepted.value) == prefix + 2  # The next value is now buffered.
	with pytest.raises(EndpointStateError):
		await sink.recv()  # Busy, or requiring reset following adapter failure.
	if interruption == "cancel":
		assert not receiving.done()
		receiving.cancel()
		with pytest.raises(CancelledError):
			await receiving
		with pytest.raises(EndpointStateError):
			await sink.recv()
	elif interruption == "reset":
		assert not receiving.done()
	else:
		assert receiving.done()
		assert len(errors) == 1 and str(errors[0]) == "injected chained read failure"
	await sink.initialise()  # Clear ready before another rising edge can accept data.
	if interruption != "cancel":
		await receiving
		if interruption == "reset":
			assert len(errors) == 1 and isinstance(errors[0], TransferReset)
	await sending
	await ReadOnly()
	assert str(sink_bus.ready.value) == "0"
	assert int(dut.retired.value) == prefix + 1
	assert int(dut.accepted.value) == prefix + 2
	transfer = await sink.recv()  # Resume with the buffered next value, not a retry.
	assert (to_unsigned(_array(transfer.data)), transfer.last) == values[-1]
	for _ in range(3):
		await RisingEdge(dut.beat_clock)
		assert str(dut.m_valid.value) == str(dut.m_ready.value) == "0"
	await ReadOnly()
	assert int(dut.accepted.value) == int(dut.retired.value) == prefix + 2

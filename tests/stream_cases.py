# stream_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Simulator cases for bindings, payloads, handshake timing and recovery."""

from typing import Any
from random import Random
from asyncio import CancelledError
from dataclasses import dataclass
from collections.abc import Coroutine, Mapping

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject, LogicArrayObject
from cocotb.triggers import Timer, ReadOnly, RisingEdge, FallingEdge

from coaxi import (
	AxiStreamBus,
	AxiStreamSink,
	AxiStreamSource,
	EndpointStateError,
	HandlePayload,
	PayloadValue,
	ProtocolValueError,
	SignalBindingError,
	TransferReset,
	to_signed,
	to_unsigned,
)


async def _capture[T](operation: Coroutine[Any, Any, T]) -> T | Exception:
	try:
		return await operation
	except Exception as exc:
		return exc


def _plain(dut: HierarchyObject) -> AxiStreamBus:
	return AxiStreamBus.bind(dut, prefix="plain", t_prefix=False)


def _record(dut: HierarchyObject) -> AxiStreamBus:
	return AxiStreamBus.bind(
		dut,
		data="iq_word_in",
		valid="sample_available",
		ready="consumer_accepts",
		last="end_of_packet",
	)


def _array(value: PayloadValue) -> LogicArray:
	assert isinstance(value, LogicArray)
	return value


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
	for _ in range(2):
		await FallingEdge(dut.beat_clock)
	dut.wipe_registers.value = 0


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def signal_bindings(dut: HierarchyObject) -> None:
	"""Bind both defaults, unrelated names, partial overrides and exact handles."""
	standard = AxiStreamBus.bind(dut, prefix="s", last=True)
	assert standard.data is dut.s_tdata
	assert standard.last is dut.s_tlast
	assert AxiStreamBus.bind(dut, prefix="s").last is None
	plain = AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True)
	assert plain.valid is dut.m_valid
	mixed = AxiStreamBus.bind(dut, prefix="s", ready="consumer_accepts")
	assert mixed.data is dut.s_tdata
	assert mixed.ready is dut.consumer_accepts
	mixed_handle = AxiStreamBus.bind(dut, prefix="s", valid=dut.sample_available, last=dut.end_of_packet)
	assert mixed_handle.valid is dut.sample_available
	assert mixed_handle.ready is dut.s_tready
	assert mixed_handle.last is dut.end_of_packet
	record = _record(dut)
	assert record.data is dut.iq_word_in
	direct = AxiStreamBus.bind(data=record.data, valid=record.valid, ready=record.ready, last=record.last)
	assert direct == record
	assert record.resolve_clock("beat_clock") is dut.beat_clock
	assert direct.resolve_clock(dut.beat_clock) is dut.beat_clock
	odd = AxiStreamBus.bind(dut, data="\\lane.payload[0]\\", valid="\\offer-now!\\", ready="\\take-it?\\")
	assert odd.data is dut["\\lane.payload[0]\\"]
	with pytest.raises(SignalBindingError, match="requires an entity"):
		direct.resolve_clock("beat_clock")
	with pytest.raises(SignalBindingError, match="no signal"):
		AxiStreamBus.bind(dut, prefix="missing")
	with pytest.raises(SignalBindingError, match="no signal"):
		AxiStreamBus.bind(dut, prefix="plain", t_prefix=False, last=True)
	with pytest.raises(SignalBindingError, match="one-bit"):
		AxiStreamBus.bind(dut, prefix="s", ready="s_tdata")
	with pytest.raises(SignalBindingError, match="different"):
		AxiStreamBus.bind(dut, prefix="s", ready="s_tvalid")
	with pytest.raises(SignalBindingError):
		AxiStreamBus.bind(dut, prefix="s", last=1)  # type: ignore[bad-argument-type]


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def registered_transfers(dut: HierarchyObject) -> None:
	"""Exercise registered pre-edge sampling, stalls and multiple frame boundaries."""
	await _setup(dut)
	source = AxiStreamSource(AxiStreamBus.bind(dut, prefix="s", last=True), "beat_clock")
	sink = AxiStreamSink(AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True), dut.beat_clock)
	await source.reset()
	await sink.reset()
	values = [(index * 71, index % 5 == 4) for index in range(30)]

	async def send_all() -> None:
		for data, last in values:
			await source.send(data, last=last)

	sending = cocotb.start_soon(send_all())
	await Timer(12, unit="ns")
	for _ in range(3):
		await RisingEdge(dut.beat_clock)
		assert int(dut.s_tvalid.value) == 1
		assert int(dut.s_tdata.value) == values[0][0]
		assert int(dut.s_tlast.value) == 0
		assert int(dut.accepted.value) == 0
	await FallingEdge(dut.beat_clock)
	dut.allow_input.value = 1
	rng = Random(73)
	for data, last in values:
		await Timer(rng.randrange(1, 35), unit="ns")
		transfer = await sink.recv()
		assert to_unsigned(_array(transfer.data)) == data
		assert transfer.last is last
	await sending
	await ReadOnly()
	assert int(dut.accepted.value) == len(values)
	assert int(dut.retired.value) == len(values)
	assert int(dut.s_tvalid.value) == 0
	assert int(dut.m_ready.value) == 0


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def unframed_transfers(dut: HierarchyObject) -> None:
	"""Keep unframed last absent and enforce explicit framing arguments."""
	await _setup(dut)
	bus = _plain(dut)
	source, sink = AxiStreamSource(bus, "beat_clock"), AxiStreamSink(bus, "beat_clock")
	with pytest.raises(EndpointStateError):
		await source.send(1)
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await source.reset()
	await sink.reset()
	with pytest.raises(ValueError, match="bound last"):
		await source.send(1, last=False)
	framed = AxiStreamSource(_record(dut), "beat_clock")
	with pytest.raises(ValueError, match="explicit|requires"):
		await framed.send({"i": 0, "q": 0})
	for value in (0, 255, 42):
		task = cocotb.start_soon(source.send(value))
		result = await sink.recv()
		await task
		assert to_unsigned(_array(result.data)) == value
		assert result.last is None
		await ReadOnly()
		assert str(bus.valid.value) == "0"
		assert str(bus.ready.value) == "0"


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def record_payloads(dut: HierarchyObject) -> None:
	"""Transfer IQ_t directly as fields, preserving signed values and X/U bits."""
	await _setup(dut)
	bus = _record(dut)
	source, sink = AxiStreamSource(bus, "beat_clock"), AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()
	values: list[PayloadValue] = [
		{"i": LogicArray.from_signed(-321, 16), "q": LogicArray.from_signed(123, 16)},
		{"i": "XU00000000000001", "q": "00000000000000UZ"},
	]
	snapshots = []
	for value in values:
		task = cocotb.start_soon(source.send(value, last=True))
		result = await sink.recv()
		await task
		assert result.last is True
		assert isinstance(result.data, Mapping)
		snapshots.append(result.data)
	assert to_signed(_array(snapshots[0]["i"])) == -321
	assert to_signed(_array(snapshots[0]["q"])) == 123
	assert str(snapshots[1]["i"]) == "XU00000000000001"
	assert str(snapshots[1]["q"]) == "00000000000000UZ"
	with pytest.raises(ValueError, match="unresolved"):
		to_unsigned(_array(snapshots[1]["i"]))
	await source.reset()
	await ReadOnly()
	assert int(dut.iq_word_in["i"].value) == 0
	assert int(dut.iq_word_in["q"].value) == 0
	assert str(snapshots[1]["i"]) == "XU00000000000001"


@dataclass(frozen=True)
class _IQ:
	i: int
	q: int


class _IQPayload:
	def __init__(self, handle: HierarchyObject) -> None:
		self._raw = HandlePayload(handle)

	def read(self) -> _IQ:
		"""Read a signed application value using explicit numeric conversion."""
		value = self._raw.read()
		assert isinstance(value, Mapping)
		return _IQ(to_signed(_array(value["i"])), to_signed(_array(value["q"])))

	def drive(self, value: _IQ) -> None:
		"""Drive value's fields without flattening the record."""
		self._raw.drive({"i": LogicArray.from_signed(value.i, 16), "q": LogicArray.from_signed(value.q, 16)})

	def clear(self) -> None:
		"""Clear both record fields."""
		self._raw.clear()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def application_payload(dut: HierarchyObject) -> None:
	"""Use a typed application value without changing the handshake implementation."""
	await _setup(dut)
	bus = _record(dut)
	handle = bus.data
	assert isinstance(handle, HierarchyObject)
	source = AxiStreamSource(bus, "beat_clock", payload=_IQPayload(handle))
	sink = AxiStreamSink(bus, "beat_clock", payload=_IQPayload(handle))
	await source.reset()
	await sink.reset()
	task = cocotb.start_soon(source.send(_IQ(-32768, 32767), last=False))
	result = await sink.recv()
	await task
	assert result.data == _IQ(-32768, 32767)
	assert result.last is False


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def meta_controls(dut: HierarchyObject) -> None:
	"""Reject unresolved/weak control bits while preserving deliberate payload X/U."""
	await _setup(dut)
	bus = _plain(dut)
	source, sink = AxiStreamSource(bus, "beat_clock"), AxiStreamSink(bus, "beat_clock")
	for meta in ("X", "U", "Z", "W", "L", "H", "-"):
		await source.reset()
		dut.plain_ready.value = meta
		with pytest.raises(ProtocolValueError, match="ready"):
			await source.send("XU000001")
		with pytest.raises(EndpointStateError):
			await source.send(0)
		await source.reset()
		await ReadOnly()
		assert int(dut.plain_data.value) == 0
		await FallingEdge(dut.beat_clock)
		dut.plain_valid.value = meta
		await sink.reset()
		with pytest.raises(ProtocolValueError, match="valid"):
			await sink.recv()
		await FallingEdge(dut.beat_clock)
		dut.plain_valid.value = 0
	framed = AxiStreamSink(_record(dut), "beat_clock")
	await framed.reset()
	dut.sample_available.value = 1
	dut.end_of_packet.value = "X"
	with pytest.raises(ProtocolValueError, match="last"):
		await framed.recv()
	await FallingEdge(dut.beat_clock)
	dut.sample_available.value = 0
	await framed.reset()
	task = cocotb.start_soon(framed.recv())
	await Timer(22, unit="ns")  # Last X is irrelevant while valid is zero.
	assert not task.done()
	await FallingEdge(dut.beat_clock)
	dut.end_of_packet.value = 1
	dut.sample_available.value = 1
	result = await task
	assert result.last is True


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def reset_and_busy(dut: HierarchyObject) -> None:
	"""Reset pending operations, reject overlap and recover without stale state."""
	await _setup(dut)
	bus = _plain(dut)
	source, sink = AxiStreamSource(bus, "beat_clock"), AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()
	task = cocotb.start_soon(_capture(source.send("XU000001")))
	await Timer(12, unit="ns")
	with pytest.raises(EndpointStateError, match="one transfer"):
		await source.send(1)
	await source.reset()
	assert isinstance(await task, TransferReset)
	await ReadOnly()
	assert int(dut.plain_data.value) == 0
	assert str(dut.plain_valid.value) == "0"
	pending = cocotb.start_soon(_capture(sink.recv()))
	await Timer(12, unit="ns")
	with pytest.raises(EndpointStateError, match="one transfer"):
		await sink.recv()
	resetting = cocotb.start_soon(sink.reset())
	await Timer(1, unit="ns")
	with pytest.raises(EndpointStateError, match="already active"):
		await sink.reset()
	await resetting
	assert isinstance(await pending, TransferReset)
	task = cocotb.start_soon(source.send(72))
	assert to_unsigned(_array((await sink.recv()).data)) == 72
	await task


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def cancellation_and_errors(dut: HierarchyObject) -> None:
	"""Cancellation and payload failures require explicit, defined recovery."""
	await _setup(dut)
	bus = _plain(dut)
	source, sink = AxiStreamSource(bus, "beat_clock"), AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()
	sending = cocotb.start_soon(source.send("XXXXXXXX"))
	await Timer(12, unit="ns")
	sending.cancel()
	with pytest.raises(CancelledError):
		await sending
	with pytest.raises(EndpointStateError):
		await source.send(0)
	await source.reset()
	await ReadOnly()
	assert int(dut.plain_data.value) == 0
	assert str(dut.plain_valid.value) == "0"
	receiving = cocotb.start_soon(sink.recv())
	await Timer(12, unit="ns")
	receiving.cancel()
	with pytest.raises(CancelledError):
		await receiving
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await sink.reset()
	await ReadOnly()
	assert str(dut.plain_ready.value) == "0"
	with pytest.raises(ValueError):
		await source.send(256)
	with pytest.raises(EndpointStateError):
		await source.send(0)
	await source.reset()
	task = cocotb.start_soon(source.send(9))
	assert to_unsigned(_array((await sink.recv()).data)) == 9
	await task


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def payload_validation(dut: HierarchyObject) -> None:
	"""Validate full records before writes and reject unsupported handles."""
	await _setup(dut)
	raw = HandlePayload(dut.iq_word_in)
	await FallingEdge(dut.beat_clock)
	raw.drive({"i": 7, "q": 8})
	await ReadOnly()
	for invalid in ({"i": 3}, {"i": 3, "q": 65536}, {"i": 3, "q": 4, "other": 0}):
		with pytest.raises(ValueError):
			raw.drive(invalid)
	assert int(dut.iq_word_in["i"].value) == 7
	assert int(dut.iq_word_in["q"].value) == 8
	with pytest.raises(TypeError, match="unsupported"):
		HandlePayload(dut.accepted)
	vector = HandlePayload(dut.plain_data)
	for invalid_vector in (-1, 256, "101", {"field": 1}):
		with pytest.raises((ValueError, TypeError)):
			vector.drive(invalid_vector)
	assert isinstance(dut.plain_data, LogicArrayObject)

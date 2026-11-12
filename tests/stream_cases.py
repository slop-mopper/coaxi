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
	await source.initialise()
	await sink.initialise()
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
	await source.initialise()
	await sink.initialise()
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
	await source.initialise()
	await sink.initialise()
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
	await source.initialise()
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
	await source.initialise()
	await sink.initialise()
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
		await source.initialise()
		dut.plain_ready.value = meta
		with pytest.raises(ProtocolValueError, match="ready"):
			await source.send("XU000001")
		with pytest.raises(EndpointStateError):
			await source.send(0)
		await source.initialise()
		await ReadOnly()
		assert int(dut.plain_data.value) == 0
		await FallingEdge(dut.beat_clock)
		dut.plain_valid.value = meta
		await sink.initialise()
		with pytest.raises(ProtocolValueError, match="valid"):
			await sink.recv()
		await FallingEdge(dut.beat_clock)
		dut.plain_valid.value = 0
	framed = AxiStreamSink(_record(dut), "beat_clock")
	await framed.initialise()
	dut.sample_available.value = 1
	dut.end_of_packet.value = "X"
	with pytest.raises(ProtocolValueError, match="last"):
		await framed.recv()
	await FallingEdge(dut.beat_clock)
	dut.sample_available.value = 0
	await framed.initialise()
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
	await source.initialise()
	await sink.initialise()
	task = cocotb.start_soon(_capture(source.send("XU000001")))
	await Timer(12, unit="ns")
	with pytest.raises(EndpointStateError, match="one operation"):
		await source.send(1)
	await source.initialise()
	assert isinstance(await task, TransferReset)
	await ReadOnly()
	assert int(dut.plain_data.value) == 0
	assert str(dut.plain_valid.value) == "0"
	pending = cocotb.start_soon(_capture(sink.recv()))
	await Timer(12, unit="ns")
	with pytest.raises(EndpointStateError, match="one operation"):
		await sink.recv()
	resetting = cocotb.start_soon(sink.initialise())
	await Timer(1, unit="ns")
	with pytest.raises(EndpointStateError, match="already active"):
		await sink.initialise()
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
	await source.initialise()
	await sink.initialise()
	sending = cocotb.start_soon(source.send("XXXXXXXX"))
	await Timer(12, unit="ns")
	sending.cancel()
	with pytest.raises(CancelledError):
		await sending
	with pytest.raises(EndpointStateError):
		await source.send(0)
	await source.initialise()
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
	await sink.initialise()
	await ReadOnly()
	assert str(dut.plain_ready.value) == "0"
	with pytest.raises(ValueError):
		await source.send(256)
	with pytest.raises(EndpointStateError):
		await source.send(0)
	await source.initialise()
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


async def _reset_registered_path(dut: HierarchyObject) -> None:
	await FallingEdge(dut.beat_clock)
	dut.wipe_registers.value = 1
	dut.allow_input.value = 1
	await RisingEdge(dut.beat_clock)
	await FallingEdge(dut.beat_clock)
	dut.wipe_registers.value = 0


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def interruptions_after_acceptance(dut: HierarchyObject) -> None:
	"""Preserve wire acceptance when reset/cancellation interrupts cleanup."""
	await _setup(dut)
	source_bus = AxiStreamBus.bind(dut, prefix="s", last=True)
	sink_bus = AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True)
	source, sink = AxiStreamSource(source_bus, "beat_clock"), AxiStreamSink(sink_bus, "beat_clock")
	for target in ("source", "sink"):
		for interruption in ("cancel", "reset"):
			await source.initialise()
			await sink.initialise()
			await _reset_registered_path(dut)
			value = 0x1234
			if target == "source":
				pending = cocotb.start_soon(_capture(source.send(value, last=True)))
			else:
				# Fill the registered DUT while the sink keeps ready low.
				await source.send(value, last=True)
				pending = cocotb.start_soon(_capture(sink.recv()))
			await Timer(1, unit="ns")
			await FallingEdge(dut.beat_clock)
			await RisingEdge(dut.beat_clock)
			await Timer(1, unit="ns")  # Accepted, but falling-edge cleanup is pending.
			assert not pending.done()
			assert int(dut.accepted.value) == 1
			assert int(dut.retired.value) == (1 if target == "sink" else 0)
			endpoint = source if target == "source" else sink
			if interruption == "cancel":
				pending.cancel()
				with pytest.raises(CancelledError):
					await pending
				with pytest.raises(EndpointStateError):
					if target == "source":
						await source.send(0, last=False)
					else:
						await sink.recv()
				await endpoint.initialise()
			else:
				await endpoint.initialise()
				assert isinstance(await pending, TransferReset)
			await ReadOnly()
			assert int(dut.accepted.value) == 1  # Recovery cannot undo acceptance.
			assert int(dut.retired.value) == (1 if target == "sink" else 0)
			if target == "source":
				assert str(source_bus.valid.value) == "0"
				assert str(source_bus.last.value) == "0"
				assert int(source_bus.data.value) == 0
				buffered = await sink.recv()
				assert to_unsigned(_array(buffered.data)) == value
				assert buffered.last is True
				await ReadOnly()
				assert int(dut.accepted.value) == 1
				assert int(dut.retired.value) == 1
			else:
				assert str(sink_bus.ready.value) == "0"
			# Coordinate local recovery with DUT reset, then send a distinct value.
			await source.initialise()
			await sink.initialise()
			await _reset_registered_path(dut)
			sending = cocotb.start_soon(source.send(0x5678, last=False))
			result = await sink.recv()
			await sending
			assert to_unsigned(_array(result.data)) == 0x5678
			assert result.last is False
			await ReadOnly()
			assert int(dut.accepted.value) == 1
			assert int(dut.retired.value) == 1


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def cancelled_resets(dut: HierarchyObject) -> None:
	"""A cancelled clearing edge leaves reset required and permits recovery."""
	await _setup(dut)
	bus = _record(dut)
	source, sink = AxiStreamSource(bus, "beat_clock"), AxiStreamSink(bus, "beat_clock")
	await source.initialise()
	await sink.initialise()
	for target, cancel_transfer in (("source", True), ("sink", True), ("source", False), ("sink", False)):
		if target == "source":
			pending = cocotb.start_soon(_capture(source.send({"i": "X" * 16, "q": "U" * 16}, last=True)))
		else:
			pending = cocotb.start_soon(_capture(sink.recv()))
		await Timer(1, unit="ns")
		await FallingEdge(dut.beat_clock)
		await Timer(1, unit="ns")
		if cancel_transfer:
			pending.cancel()
			with pytest.raises(CancelledError):
				await pending
		endpoint = source if target == "source" else sink
		resetting = cocotb.start_soon(endpoint.initialise())
		await Timer(1, unit="ns")  # Cancel before the next falling edge can clear outputs.
		resetting.cancel()
		with pytest.raises(CancelledError):
			await resetting
		if not cancel_transfer:
			assert isinstance(await pending, TransferReset)
		with pytest.raises(EndpointStateError):
			if target == "source":
				await source.send({"i": 0, "q": 0}, last=False)
			else:
				await sink.recv()
		if target == "source":
			assert str(bus.valid.value) == "1"
			assert str(bus.last.value) == "1"
			assert str(dut.iq_word_in["i"].value) == "X" * 16
			assert str(dut.iq_word_in["q"].value) == "U" * 16
		else:
			assert str(bus.ready.value) == "1"
		await endpoint.initialise()
		await ReadOnly()
		if target == "source":
			assert str(bus.valid.value) == "0"
			assert str(bus.last.value) == "0"
			assert int(dut.iq_word_in["i"].value) == 0
			assert int(dut.iq_word_in["q"].value) == 0
		else:
			assert str(bus.ready.value) == "0"
	sending = cocotb.start_soon(source.send({"i": 7, "q": 8}, last=True))
	result = await sink.recv()
	await sending
	assert isinstance(result.data, Mapping)
	assert to_unsigned(_array(result.data["i"])) == 7
	assert to_unsigned(_array(result.data["q"])) == 8
	assert result.last is True


class _FaultPayload:
	def __init__(self, handle: LogicArrayObject) -> None:
		self._raw = HandlePayload(handle)
		self.failure: str | None = None

	def read(self) -> PayloadValue:
		"""Raise on demand before reading an accepted payload."""
		if self.failure == "read":
			raise RuntimeError("injected read failure")
		return self._raw.read()

	def drive(self, value: PayloadValue) -> None:
		"""Raise on demand after writing, to model a partially failed adapter."""
		self._raw.drive(value)
		if self.failure == "drive":
			raise RuntimeError("injected drive failure")

	def clear(self) -> None:
		"""Raise on demand before clearing, leaving previous data on the wire."""
		if self.failure == "clear":
			raise RuntimeError("injected clear failure")
		self._raw.clear()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def healthy_reset_failures(dut: HierarchyObject) -> None:
	"""An unsuccessful reset invalidates even a previously healthy endpoint."""
	await _setup(dut)
	bus = _plain(dut)
	payload = _FaultPayload(dut.plain_data)
	source = AxiStreamSource(bus, "beat_clock", payload=payload)
	sink = AxiStreamSink(bus, "beat_clock")
	await source.initialise()
	await sink.initialise()
	for target in ("source", "sink"):
		endpoint = source if target == "source" else sink
		resetting = cocotb.start_soon(endpoint.initialise())
		await Timer(1, unit="ns")  # Healthy and idle; reset has begun but cannot finish.
		resetting.cancel()
		with pytest.raises(CancelledError):
			await resetting
		with pytest.raises(EndpointStateError):
			if target == "source":
				await source.send(1)
			else:
				await sink.recv()
		await endpoint.initialise()
	payload.failure = "clear"
	with pytest.raises(RuntimeError, match="injected clear"):
		await source.initialise()
	with pytest.raises(EndpointStateError):
		await source.send(2)
	payload.failure = None
	await source.initialise()
	sending = cocotb.start_soon(source.send(3))
	assert to_unsigned(_array((await sink.recv()).data)) == 3
	await sending


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def adapter_failures(dut: HierarchyObject) -> None:
	"""Propagate adapter failures and require recovery without claiming rollback."""
	await _setup(dut)
	bus = _plain(dut)
	source_payload = _FaultPayload(dut.plain_data)
	sink_payload = _FaultPayload(dut.plain_data)
	source = AxiStreamSource(bus, "beat_clock", payload=source_payload)
	sink = AxiStreamSink(bus, "beat_clock", payload=sink_payload)
	await source.initialise()
	await sink.initialise()
	source_payload.failure = "drive"
	with pytest.raises(RuntimeError, match="injected drive"):
		await source.send("XU000001")
	with pytest.raises(EndpointStateError):
		await source.send(0)
	source_payload.failure = "clear"
	with pytest.raises(RuntimeError, match="injected clear"):
		await source.initialise()
	with pytest.raises(EndpointStateError):
		await source.send(0)
	await ReadOnly()
	assert str(dut.plain_data.value) == "XU000001"
	assert str(bus.valid.value) == "0"
	source_payload.failure = None
	await source.initialise()
	await ReadOnly()
	assert int(dut.plain_data.value) == 0

	sink_payload.failure = "read"
	sending = cocotb.start_soon(source.send(21))
	with pytest.raises(RuntimeError, match="injected read"):
		await sink.recv()
	await sending
	with pytest.raises(EndpointStateError):
		await sink.recv()
	# The sink owns only ready: reset must not invoke the payload clear hook.
	sink_payload.failure = "clear"
	await sink.initialise()
	await ReadOnly()
	assert str(bus.ready.value) == "0"
	assert int(dut.plain_data.value) == 21
	sink_payload.failure = None
	sending = cocotb.start_soon(source.send(88))
	assert to_unsigned(_array((await sink.recv()).data)) == 88
	await sending

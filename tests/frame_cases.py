# frame_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Frame ownership, full-rate timing, optional limits and destructive recovery."""

from typing import cast, overload
from random import Random
from asyncio import CancelledError
from collections.abc import Mapping, Sequence

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.types import LogicArray
from cocotb.handle import HierarchyObject
from cocotb.simtime import get_sim_time
from cocotb.triggers import Event, Timer, ReadOnly, ReadWrite, RisingEdge, FallingEdge

from coaxi import (
	AxiStreamBus,
	AxiStreamSink,
	AxiStreamSource,
	AxiStreamTransfer,
	EndpointStateError,
	HandlePayload,
	PayloadValue,
	ProtocolValueError,
	TransferReset,
	to_signed,
)


async def _setup(dut: HierarchyObject) -> AxiStreamBus:
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
	dut.wipe_registers.value = 0
	return AxiStreamBus.bind(
		dut, data="iq_word_in", valid="sample_available", ready="consumer_accepts", last="end_of_packet"
	)


def _value(index: int) -> PayloadValue:
	return {"i": index, "q": 300 - index}


def _snapshot(dut: HierarchyObject) -> tuple[int, bool]:
	return int(dut.iq_word_in["i"].value), str(dut.end_of_packet.value) == "1"


async def _loopback(
	source: AxiStreamSource[PayloadValue], sink: AxiStreamSink[PayloadValue], values: Sequence[PayloadValue]
) -> list[AxiStreamTransfer[PayloadValue]]:
	sending = cocotb.start_soon(source.send_frame(values))
	results = await sink.recv_frame()
	await sending
	return results


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def registered_frames(dut: HierarchyObject) -> None:
	"""Sustain 128 beats across frames and mixed single/frame API boundaries."""
	await _setup(dut)
	source = AxiStreamSource(AxiStreamBus.bind(dut, prefix="s", last=True), "beat_clock")
	sink = AxiStreamSink(AxiStreamBus.bind(dut, prefix="m", t_prefix=False, last=True), "beat_clock")
	await source.reset()
	await sink.reset()
	dut.allow_input.value = 1
	lengths = [1, 3, 64, 1, 2, 31, 26]
	frames = []
	offset = 0
	for length in lengths:
		frames.append(list(range(offset, offset + length)))
		offset += length
	expected = [(value, index == len(frame) - 1) for frame in frames for index, value in enumerate(frame)]

	async def send_all() -> None:
		for index, frame in enumerate(frames):
			if index in (0, 3):
				await source.send(frame[0], last=True)
			else:
				await source.send_frame(frame)

	async def receive_all() -> None:
		for index, frame in enumerate(frames):
			if index in (0, 3):
				transfers = [await sink.recv()]
			else:
				transfers = await sink.recv_frame(max_transfers=len(frame) if index % 2 else None)
			assert [(int(str(t.data), 2), t.last) for t in transfers] == [
				(value, i == len(frame) - 1) for i, value in enumerate(frame)
			]

	sending = cocotb.start_soon(send_all())
	receiving = cocotb.start_soon(receive_all())
	inputs: list[tuple[int, int, bool]] = []
	outputs: list[tuple[int, int, bool]] = []
	for cycle in range(offset + 8):
		await RisingEdge(dut.beat_clock)
		if str(dut.s_tvalid.value) == str(dut.s_tready.value) == "1":
			inputs.append((cycle, int(dut.s_tdata.value), str(dut.s_tlast.value) == "1"))
		if str(dut.m_valid.value) == str(dut.m_ready.value) == "1":
			outputs.append((cycle, int(dut.m_data.value), str(dut.m_last.value) == "1"))
	assert sending.done() and receiving.done(), "frame operations inserted idle cycles"
	await sending
	await receiving
	for beats in (inputs, outputs):
		assert [(value, last) for _, value, last in beats] == expected
		assert [cycle for cycle, _, _ in beats] == list(range(beats[0][0], beats[0][0] + offset))
	assert [c for c, _, _ in outputs] == [c + 1 for c, _, _ in inputs]
	await ReadOnly()
	assert int(dut.accepted.value) == int(dut.retired.value) == offset
	assert str(dut.s_tvalid.value) == str(dut.m_ready.value) == "0"


class _IQPayload:
	def __init__(self, handle: HierarchyObject) -> None:
		self._raw = HandlePayload(handle)

	def read(self) -> tuple[int, int]:
		"""Return independent signed values."""
		value = self._raw.read()
		assert isinstance(value, Mapping)
		i, q = value["i"], value["q"]
		assert isinstance(i, LogicArray) and isinstance(q, LogicArray)
		return to_signed(i), to_signed(q)

	def drive(self, value: tuple[int, int]) -> None:
		"""Drive each signed record field."""
		self._raw.drive({"i": LogicArray.from_signed(value[0], 16), "q": LogicArray.from_signed(value[1], 16)})

	def clear(self) -> None:
		"""Clear the record."""
		self._raw.clear()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def structured_frames(dut: HierarchyObject) -> None:
	"""Preserve record snapshots, X/U and custom payload types across frames."""
	bus = await _setup(dut)
	source = AxiStreamSource(bus, "beat_clock")
	sink = AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()
	values: list[PayloadValue] = [{"i": "XU00000000000001", "q": f"{index:016b}"} for index in range(8)]
	results = await _loopback(source, sink, values)
	assert [t.last for t in results] == [False] * 7 + [True]
	for result, expected in zip(results, values, strict=True):
		assert isinstance(result.data, Mapping) and isinstance(expected, Mapping)
		assert {name: str(value) for name, value in result.data.items()} == expected
	await source.reset()
	# Clearing the wire and driving another frame cannot mutate earlier snapshots.
	await _loopback(source, sink, [_value(42)])
	assert isinstance(results[0].data, Mapping)
	assert str(results[0].data["i"]) == "XU00000000000001"
	assert str(results[0].data["q"]) == "0000000000000000"
	assert isinstance(bus.data, HierarchyObject)
	custom_source = AxiStreamSource(bus, "beat_clock", payload=_IQPayload(bus.data))
	custom_sink = AxiStreamSink(bus, "beat_clock", payload=_IQPayload(bus.data))
	await custom_source.reset()
	await custom_sink.reset()
	pairs = [(-32768 + index, 32767 - index) for index in range(32)]
	sending = cocotb.start_soon(custom_source.send_frame(pairs))
	frame = await custom_sink.recv_frame(max_transfers=32)
	await sending
	assert [t.data for t in frame] == pairs
	assert [t.last for t in frame] == [False] * 31 + [True]


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def frame_backpressure(dut: HierarchyObject) -> None:
	"""An independent receiver stalls every final beat and checks no bubbles."""
	bus = await _setup(dut)
	source = AxiStreamSource(bus, "beat_clock")
	await source.reset()
	lengths = [1, 5, 2, 9]
	expected = [
		(i, j == length - 1) for i, (length, j) in enumerate((length, j) for length in lengths for j in range(length))
	]

	async def send_all() -> None:
		offset = 0
		for length in lengths:
			await source.send_frame([_value(i) for i in range(offset, offset + length)])
			offset += length

	sending = cocotb.start_soon(send_all())
	seed = 61283
	dut._log.debug("frame_backpressure seed=%s", seed)
	rng = Random(seed)
	accepted = 0
	stalled: tuple[int, bool] | None = None
	final_stalls: set[int] = set()
	stall_requested: set[int] = set()
	started = False
	for cycle in range(200):
		await FallingEdge(dut.beat_clock)
		force_final_stall = expected[accepted][1] and accepted not in stall_requested
		if force_final_stall and started:
			stall_requested.add(accepted)
		ready = cycle >= 3 and not force_final_stall and bool(rng.getrandbits(2))
		dut.consumer_accepts.value = int(ready)
		await RisingEdge(dut.beat_clock)
		valid = str(bus.valid.value) == "1"
		current = _snapshot(dut)
		if started:
			assert valid, "unwanted bubble within or between frames"
		if stalled is not None:
			assert valid and current == stalled
		if valid:
			started = True
			assert current == expected[accepted]
			stalled = None if ready else current
			if current[1] and not ready:
				final_stalls.add(accepted)
			if ready:
				accepted += 1
				if accepted == len(expected):
					break
	assert accepted == len(expected)
	assert len(final_stalls) == len(lengths)
	await sending
	await ReadOnly()
	assert str(bus.valid.value) == str(dut.end_of_packet.value) == "0"


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def frame_source_gaps(dut: HierarchyObject) -> None:
	"""An independent source checks ready across source gaps and frame boundaries."""
	bus = await _setup(dut)
	sink = AxiStreamSink(bus, "beat_clock")
	await sink.reset()
	results: list[list[AxiStreamTransfer[PayloadValue]]] = []

	async def receive_all() -> None:
		for _ in range(3):
			results.append(await sink.recv_frame(max_transfers=3))

	receiving = cocotb.start_soon(receive_all())
	accepted = 0
	started = False
	for cycle in range(60):
		await FallingEdge(dut.beat_clock)
		dut.sample_available.value = int(cycle % 5 >= 2)
		dut.iq_word_in["i"].value = accepted
		dut.iq_word_in["q"].value = 0
		dut.end_of_packet.value = int(accepted % 3 == 2)
		await RisingEdge(dut.beat_clock)
		ready = str(bus.ready.value) == "1"
		if started:
			assert ready, "unwanted ready gap"
		started |= ready
		if ready and str(bus.valid.value) == "1":
			accepted += 1
			if accepted == 9:
				break
	await receiving
	assert accepted == 9 and [len(frame) for frame in results] == [3, 3, 3]
	assert [t.last for frame in results for t in frame] == [False, False, True] * 3
	for i, transfer in enumerate(t for frame in results for t in frame):
		assert isinstance(transfer.data, Mapping)
		assert int(str(transfer.data["i"]), 2) == i
	for _ in range(3):
		await RisingEdge(dut.beat_clock)
		assert str(bus.ready.value) == "0"  # No unsolicited consumption.


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def frame_validation(dut: HierarchyObject) -> None:
	"""Reject invalid preflight arguments without poisoning healthy endpoints."""
	bus = await _setup(dut)
	source = AxiStreamSource(bus, "beat_clock")
	sink = AxiStreamSink(bus, "beat_clock")
	with pytest.raises(EndpointStateError):
		await source.send_frame([_value(1)])
	with pytest.raises(EndpointStateError):
		await sink.recv_frame()
	await source.reset()
	await sink.reset()
	start = get_sim_time(unit="step")
	with pytest.raises(ValueError, match="at least one"):
		await source.send_frame([])
	with pytest.raises(TypeError, match="sequence"):
		await source.send_frame(cast(Sequence[PayloadValue], iter([1, 2])))
	for limit in (0, -1):
		with pytest.raises(ValueError, match="positive"):
			await sink.recv_frame(max_transfers=limit)
	for limit in (True, 1.0, "2"):
		with pytest.raises(TypeError, match="integer"):
			await sink.recv_frame(max_transfers=cast(int, limit))
	unframed = AxiStreamBus.bind(dut, prefix="plain", t_prefix=False)
	with pytest.raises(ValueError, match="bound last"):
		await AxiStreamSource(unframed, "beat_clock").send_frame([1])
	with pytest.raises(ValueError, match="bound last"):
		await AxiStreamSink(unframed, "beat_clock").recv_frame()
	assert get_sim_time(unit="step") == start
	assert [t.last for t in await _loopback(source, sink, [_value(7)])] == [True]


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def frame_limit(dut: HierarchyObject) -> None:
	"""Limit failure cleans up without accepting beat N+1 or draining."""
	bus = await _setup(dut)
	sink = AxiStreamSink(bus, "beat_clock")
	await sink.reset()
	dut.sample_available.value = 1
	dut.end_of_packet.value = 0
	dut.iq_word_in["i"].value = 12
	errors: list[ValueError] = []
	failed_at: list[int] = []

	async def limited() -> None:
		try:
			await sink.recv_frame(max_transfers=2)
		except ValueError as exc:
			errors.append(exc)
			failed_at.append(int(get_sim_time(unit="ns")))
			assert str(dut.beat_clock.value) == "0"
			await ReadOnly()
			assert str(bus.ready.value) == "0"

	receiving = cocotb.start_soon(limited())
	accepted = 0
	accepted_at = 0
	for _ in range(8):
		await RisingEdge(dut.beat_clock)
		if str(bus.ready.value) == "1":
			accepted += 1
			accepted_at = int(get_sim_time(unit="ns"))
		if receiving.done():
			break
	await receiving
	assert accepted == 2 and len(errors) == 1
	assert "max_transfers=2" in str(errors[0])
	assert failed_at == [accepted_at + 5]
	for _ in range(3):
		await RisingEdge(dut.beat_clock)
		assert str(bus.ready.value) == "0"
	with pytest.raises(EndpointStateError):
		await sink.recv()
	with pytest.raises(EndpointStateError):
		await sink.recv_frame()
	await sink.reset()
	# A local reset does not drain/re-align: the remaining frame is still here.
	dut.end_of_packet.value = 1
	assert [t.last for t in await sink.recv_frame(max_transfers=1)] == [True]


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def frame_remainder(dut: HierarchyObject) -> None:
	"""Individual receive followed by frame receive returns the remaining suffix."""
	bus = await _setup(dut)
	source = AxiStreamSource(bus, "beat_clock")
	sink = AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()
	sending = cocotb.start_soon(source.send_frame([_value(i) for i in range(3)]))
	first = await sink.recv()
	assert first.last is False
	frame = await sink.recv_frame()
	await sending
	assert [t.last for t in frame] == [False, True]
	assert [int(str(t.data["i"]), 2) for t in frame if isinstance(t.data, Mapping)] == [1, 2]


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(direction=["send", "recv"])
async def frame_ownership(dut: HierarchyObject, direction: str) -> None:
	"""Reject overlapping single/frame calls while stalled, between beats and at cleanup."""
	bus = await _setup(dut)
	source = AxiStreamSource(bus, "beat_clock")
	sink = AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()

	async def reject_overlap() -> None:
		with pytest.raises(EndpointStateError, match="one operation"):
			if direction == "send":
				await source.send(_value(99), last=True)
			else:
				await sink.recv()
		with pytest.raises(EndpointStateError, match="one operation"):
			if direction == "send":
				await source.send_frame([_value(99)])
			else:
				await sink.recv_frame()

	if direction == "send":
		task = cocotb.start_soon(source.send_frame([_value(1), _value(2)]))
	else:
		task = cocotb.start_soon(sink.recv_frame())
	await FallingEdge(dut.beat_clock)
	await Timer(1, unit="ns")
	await reject_overlap()
	await FallingEdge(dut.beat_clock)
	if direction == "send":
		dut.consumer_accepts.value = 1
	dut.sample_available.value = 1
	dut.end_of_packet.value = 0
	await RisingEdge(dut.beat_clock)
	await Timer(1, unit="ns")
	await reject_overlap()
	await FallingEdge(dut.beat_clock)
	if direction == "recv":
		dut.end_of_packet.value = 1
	await RisingEdge(dut.beat_clock)
	await Timer(1, unit="ns")
	assert not task.done()
	await reject_overlap()
	await task


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(direction=["send", "recv"], interruption=["cancel", "reset"], final=[False, True])
async def interrupted_frame(dut: HierarchyObject, direction: str, interruption: str, final: bool) -> None:
	"""Interrupt after an intermediate/final acceptance, before cleanup, then recover."""
	bus = await _setup(dut)
	source = AxiStreamSource(bus, "beat_clock")
	sink = AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()
	dut.consumer_accepts.value = int(direction == "send")
	dut.sample_available.value = 1 if direction == "recv" else 0
	dut.end_of_packet.value = 0
	errors: list[TransferReset] = []

	async def operate() -> None:
		try:
			if direction == "send":
				await source.send_frame([_value(i) for i in range(4)])
			else:
				await sink.recv_frame()
		except TransferReset as exc:
			errors.append(exc)

	task = cocotb.start_soon(operate())
	target = 4 if final else 2
	accepted: list[tuple[int, bool]] = []
	for _ in range(10):
		await FallingEdge(dut.beat_clock)
		if direction == "recv":
			dut.iq_word_in["i"].value = len(accepted)
			dut.end_of_packet.value = int(len(accepted) == 3)
		await RisingEdge(dut.beat_clock)
		if str(bus.valid.value) == str(bus.ready.value) == "1":
			accepted.append(_snapshot(dut))
			if len(accepted) == target:
				break
	await Timer(1, unit="ns")
	assert accepted == [(i, i == 3) for i in range(target)]
	assert not task.done()
	endpoint = source if direction == "send" else sink
	if interruption == "cancel":
		task.cancel()
		with pytest.raises(CancelledError):
			await task
		with pytest.raises(EndpointStateError):
			if direction == "send":
				await source.send_frame([_value(99)])
			else:
				await sink.recv_frame()
	await endpoint.reset()
	# Recover without retransmitting the interrupted frame. A separate gated
	# regression below exercises a delayed old abort against a new active token.
	if direction == "send":
		replacement = cocotb.start_soon(source.send_frame([_value(99)]))
	else:
		dut.iq_word_in["i"].value = 99
		dut.end_of_packet.value = 1
		replacement = cocotb.start_soon(sink.recv_frame())
	if interruption == "reset":
		await task
		assert len(errors) == 1
	replaced: list[tuple[int, bool]] = []
	while not replacement.done():
		await RisingEdge(dut.beat_clock)
		if str(bus.valid.value) == str(bus.ready.value) == "1":
			replaced.append(_snapshot(dut))
	await replacement
	assert replaced == [(99, True)]
	for _ in range(2):
		await RisingEdge(dut.beat_clock)
		assert str(bus.valid.value if direction == "send" else bus.ready.value) == "0"


class _Failure(HandlePayload):
	calls: int = 0
	fail: bool = True

	def drive(self, value: PayloadValue) -> None:
		"""Fail on the second drive, leaving one accepted transfer."""
		self.calls += 1
		if self.calls == 2 and self.fail:
			raise RuntimeError("injected frame drive failure")
		super().drive(value)

	def read(self) -> PayloadValue:
		"""Fail on the second accepted read."""
		self.calls += 1
		if self.calls == 2 and self.fail:
			raise RuntimeError("injected frame read failure")
		return super().read()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(direction=["send", "recv"], failure=["adapter", "control"])
async def frame_failures(dut: HierarchyObject, direction: str, failure: str) -> None:
	"""Failed adapters or control meta-values invalidate a whole in-progress frame."""
	bus = await _setup(dut)
	payload = _Failure(bus.data)
	payload.fail = failure == "adapter"
	source = AxiStreamSource(bus, "beat_clock", payload=payload)
	sink = AxiStreamSink(bus, "beat_clock", payload=payload)
	await source.reset()
	await sink.reset()
	dut.consumer_accepts.value = int(direction == "send")
	dut.sample_available.value = 1 if direction == "recv" else 0
	dut.end_of_packet.value = 0
	errors: list[RuntimeError | ProtocolValueError] = []

	async def operate() -> None:
		try:
			if direction == "send":
				await source.send_frame([_value(i) for i in range(3)])
			else:
				await sink.recv_frame()
		except (RuntimeError, ProtocolValueError) as exc:
			errors.append(exc)

	task = cocotb.start_soon(operate())
	accepted: list[tuple[int, bool]] = []

	async def monitor_prefix() -> None:
		while not task.done():
			await RisingEdge(dut.beat_clock)
			if str(bus.valid.value) == str(bus.ready.value) == "1":
				accepted.append(_snapshot(dut))
			# Let the operation process this edge before checking completion.
			await Timer(1, unit="ns")

	monitor = cocotb.start_soon(monitor_prefix())
	while not accepted:
		await Timer(1, unit="ns")
	await FallingEdge(dut.beat_clock)
	if failure == "control":
		if direction == "send":
			dut.consumer_accepts.value = "X"
		else:
			dut.end_of_packet.value = "U"
	await task
	await monitor
	assert len(errors) == 1
	if failure == "control":
		assert isinstance(errors[0], ProtocolValueError)
	else:
		assert type(errors[0]) is RuntimeError
		assert str(errors[0]) == f"injected frame {'drive' if direction == 'send' else 'read'} failure"
		assert payload.calls == 2
	assert len(accepted) == (1 if direction == "send" else 2)
	with pytest.raises(EndpointStateError):
		if direction == "send":
			await source.send_frame([_value(9)])
		else:
			await sink.recv_frame()
	endpoint = source if direction == "send" else sink
	await endpoint.reset()
	payload.fail = False
	dut.consumer_accepts.value = 1
	dut.end_of_packet.value = 1
	if direction == "send":
		await source.send_frame([_value(9)])
	else:
		assert len(await sink.recv_frame()) == 1


class _BrokenSequence(Sequence[PayloadValue]):
	def __init__(self, *, fail_length: bool = False, fail_at: int = 0) -> None:
		self.fail_length = fail_length
		self.fail_at = fail_at

	def __len__(self) -> int:
		if self.fail_length:
			raise RuntimeError("injected frame length failure")
		return 3

	@overload
	def __getitem__(self, index: int) -> PayloadValue: ...

	@overload
	def __getitem__(self, index: slice) -> Sequence[PayloadValue]: ...

	def __getitem__(self, index: int | slice) -> PayloadValue | Sequence[PayloadValue]:
		if isinstance(index, slice):
			raise TypeError("frame sending should not slice input")
		if index == self.fail_at:
			raise RuntimeError("injected frame indexing failure")
		if not 0 <= index < 3:
			raise IndexError(index)
		return _value(index)


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def frame_sequence_failures(dut: HierarchyObject) -> None:
	"""Length preflight failure stays healthy; indexing failures preserve accepted prefixes."""
	bus = await _setup(dut)
	source = AxiStreamSource(bus, "beat_clock")
	await source.reset()
	start = get_sim_time(unit="step")
	with pytest.raises(RuntimeError, match="length failure"):
		await source.send_frame(_BrokenSequence(fail_length=True))
	assert get_sim_time(unit="step") == start
	dut.consumer_accepts.value = 1
	await source.send_frame([_value(99)])  # No reset needed after failed preflight.
	for fail_at in (0, 2):
		errors: list[RuntimeError] = []

		async def operate(sequence: Sequence[PayloadValue], failures: list[RuntimeError]) -> None:
			try:
				await source.send_frame(sequence)
			except RuntimeError as exc:
				failures.append(exc)

		task = cocotb.start_soon(operate(_BrokenSequence(fail_at=fail_at), errors))
		accepted: list[tuple[int, bool]] = []
		for _ in range(6):
			await RisingEdge(dut.beat_clock)
			if str(bus.valid.value) == "1":
				accepted.append(_snapshot(dut))
			if task.done():
				break
		await task
		assert len(errors) == 1 and str(errors[0]) == "injected frame indexing failure"
		assert accepted == [(i, False) for i in range(fail_at)]
		with pytest.raises(EndpointStateError):
			await source.send_frame([_value(99)])
		await source.reset()
		await source.send_frame([_value(99)])


class _Gate:
	def __init__(self) -> None:
		self.entered = Event()
		self.release = Event()
		self.hold = True

	async def wait_once(self) -> None:
		if self.hold:
			self.hold = False
			self.entered.set()
			await self.release.wait()


class _GatedSource(AxiStreamSource[PayloadValue]):
	def __init__(self, bus: AxiStreamBus, gate: _Gate) -> None:
		super().__init__(bus, "beat_clock")
		self.gate = gate

	async def _start_edge(self) -> None:
		await super()._start_edge()
		await self.gate.wait_once()


class _GatedSink(AxiStreamSink[PayloadValue]):
	def __init__(self, bus: AxiStreamBus, gate: _Gate) -> None:
		super().__init__(bus, "beat_clock")
		self.gate = gate

	async def _start_edge(self) -> None:
		await super()._start_edge()
		await self.gate.wait_once()


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(direction=["send", "recv"])
async def stale_frame_token(dut: HierarchyObject, direction: str) -> None:
	"""Delay an old frame until newer work owns the endpoint; its abort must be harmless."""
	bus = await _setup(dut)
	gate = _Gate()
	source = _GatedSource(bus, gate)
	sink = _GatedSink(bus, gate)
	endpoint = source if direction == "send" else sink
	await endpoint.reset()
	dut.consumer_accepts.value = int(direction == "send")
	dut.sample_available.value = int(direction == "recv")
	dut.iq_word_in["i"].value = 99
	dut.end_of_packet.value = 1
	errors: list[TransferReset] = []

	async def old_frame() -> None:
		try:
			if direction == "send":
				await source.send_frame([_value(1), _value(2)])
			else:
				await sink.recv_frame()
		except TransferReset as exc:
			errors.append(exc)

	old = cocotb.start_soon(old_frame())
	await gate.entered.wait()
	assert not old.done()
	await endpoint.reset()
	if direction == "send":
		replacement = cocotb.start_soon(source.send_frame([_value(99)]))
	else:
		replacement = cocotb.start_soon(sink.recv_frame())
	await Timer(1, unit="ns")  # Replacement has acquired ownership and is waiting for its edge.
	assert not old.done() and not replacement.done()
	with pytest.raises(EndpointStateError, match="one operation"):
		if direction == "send":
			await source.send_frame([_value(88)])
		else:
			await sink.recv_frame()
	gate.release.set()
	await old
	assert len(errors) == 1
	accepted: list[tuple[int, bool]] = []
	while not replacement.done():
		await RisingEdge(dut.beat_clock)
		if str(bus.valid.value) == str(bus.ready.value) == "1":
			accepted.append(_snapshot(dut))
	await replacement
	assert accepted == [(99, True)]
	# The old abort must not leave the replacement or subsequent work requiring reset.
	if direction == "send":
		await source.send_frame([_value(100)])
	else:
		assert len(await sink.recv_frame()) == 1


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(direction=["send", "recv"], phase=["read_only", "read_write", "delay"])
async def frame_reuse_guards(dut: HierarchyObject, direction: str, phase: str) -> None:
	"""Frame boundaries respect phase/time guards instead of reusing a stale cleanup edge."""
	bus = await _setup(dut)
	source = AxiStreamSource(bus, "beat_clock")
	sink = AxiStreamSink(bus, "beat_clock")
	await source.reset()
	await sink.reset()
	dut.consumer_accepts.value = int(direction == "send")
	dut.sample_available.value = int(direction == "recv")
	dut.end_of_packet.value = 1

	async def operate() -> None:
		for _ in range(2):
			if direction == "send":
				await source.send_frame([_value(1)])
			else:
				await sink.recv_frame()
			if phase == "read_only":
				await ReadOnly()
			elif phase == "read_write":
				await ReadWrite()
			else:
				await Timer(1, unit="ns")

	task = cocotb.start_soon(operate())
	accepted: list[int] = []
	while not task.done():
		await RisingEdge(dut.beat_clock)
		if str(bus.valid.value) == str(bus.ready.value) == "1":
			accepted.append(int(get_sim_time(unit="ns")))
	await task
	assert len(accepted) == 2
	assert accepted[1] - accepted[0] == 20

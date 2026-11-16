# reliability_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Independent wire ledgers and repeated lifecycle tests; all seeds are logged."""

import os
import sys
import json
import hashlib
from typing import Any
from random import Random
from asyncio import CancelledError
from pathlib import Path
from dataclasses import dataclass
from collections import deque
from collections.abc import Coroutine

import coaxi
import cocotb
import pytest
from cocotb.task import Task
from cocotb.clock import Clock
from cocotb.handle import HierarchyObject
from cocotb.triggers import Timer, RisingEdge, FallingEdge

from coaxi import (
	AxiStreamBus,
	AxiStreamSink,
	AxiStreamSource,
	AxiStreamSidebands,
	AxiStreamTransfer,
	EndpointStateError,
	HandlePayload,
	PayloadValue,
	TransferReset,
)


def _seeds() -> list[int]:
	values = [int(value) for value in os.environ.get("COAXI_STRESS_SEEDS", "73,2028,65537").split(",")]
	if not 1 <= len(values) <= 64:
		raise ValueError("COAXI_STRESS_SEEDS requires 1..64 comma-separated integers")
	return values


def _rounds() -> int:
	value = int(os.environ.get("COAXI_STRESS_ROUNDS", "24"))
	if not 6 <= value <= 600:
		raise ValueError("COAXI_STRESS_ROUNDS must be in 6..600")
	return value


@dataclass(frozen=True)
class _Beat:
	data: str
	last: bool
	keep: str
	strb: str
	user: str
	id: int
	dest: int

	def metadata(self) -> AxiStreamSidebands:
		return AxiStreamSidebands(keep=self.keep, strb=self.strb, user=self.user, id=self.id, dest=self.dest)


class _Ledger:
	"""Compare immutable expected traffic using wire indices, not the library's packet dictionary."""

	def __init__(self, seed: int, values: list[_Beat]) -> None:
		self.seed = seed
		self.values = values
		self.observed: list[_Beat] = []
		self.history: deque[str] = deque(maxlen=24)
		self.cursor = 0
		self.pending: list[int] = []
		self.delivered: set[int] = set()
		self.discarded: set[int] = set()

	def check(self, condition: bool, message: str) -> None:
		assert condition, f"[reliability] seed={self.seed}: {message}; recent={list(self.history)}"

	def observe(self, beat: _Beat) -> None:
		index = len(self.observed)
		self.history.append(f"accept {index}: {beat}")
		self.check(index < len(self.values), "unexpected additional acceptance")
		self.check(beat == self.values[index], f"wire mismatch at {index}: expected={self.values[index]}, got={beat}")
		self.observed.append(beat)

	def expected(self, frame: bool) -> list[_Beat]:
		selected: list[int] = []
		while self.cursor < len(self.values):
			index = self.cursor
			self.cursor += 1
			beat = self.values[index]
			key = (beat.id, beat.dest)
			if not frame:
				removed = [i for i in self.pending if (self.values[i].id, self.values[i].dest) == key]
				self.discarded.update(removed)
				self.pending = [i for i in self.pending if i not in removed]
				selected = [index]
				break
			self.pending.append(index)
			if beat.last:
				selected = [i for i in self.pending if (self.values[i].id, self.values[i].dest) == key]
				self.pending = [i for i in self.pending if i not in selected]
				break
		self.check(bool(selected), "planned receive has no terminating transfer")
		self.delivered.update(selected)
		self.history.append(f"{'frame' if frame else 'raw'} -> {selected}, discard={sorted(self.discarded)}")
		return [self.values[i] for i in selected]

	def compare(self, actual: list[AxiStreamTransfer[PayloadValue | None]], expected: list[_Beat]) -> None:
		self.check(all(type(t.last) is bool for t in actual), "bound last was not returned as bool")
		result = [
			_Beat(
				str(t.data), bool(t.last), str(t.keep), str(t.strb), str(t.user), int(str(t.id), 2), int(str(t.dest), 2)
			)
			for t in actual
		]
		self.check(result == expected, f"delivery mismatch: expected={expected}, got={result}")
		self.check(len(self.observed) >= self.cursor, "returned traffic before wire acceptance")

	def complete(self) -> None:
		self.check(self.observed == self.values, "missing accepted traffic")
		self.check(not self.pending, "unfinished model packets")
		self.check(not self.delivered & self.discarded, "a beat was delivered and discarded")
		self.check(self.delivered | self.discarded == set(range(len(self.values))), "unexplained loss or duplication")


async def _setup(dut: HierarchyObject) -> Task[None]:
	if expected := os.environ.get("COAXI_EXPECT_PACKAGE"):
		root = Path(expected).resolve()
		assert Path(coaxi.__file__).resolve().parent == root, "HARNESS: wrong package origin"
		assert Path(__file__).resolve() == root.parents[1] / "tests" / "reliability_cases.py", (
			"HARNESS: wrong test origin"
		)
		manifest = json.loads(os.environ["COAXI_EXPECT_MANIFEST"])
		for name, module in list(sys.modules.items()):
			if name == "coaxi" or name.startswith("coaxi."):
				path = Path(module.__file__).resolve()
				assert path.parent == root, f"HARNESS: wrong module origin: {name}"
				assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[path.name], (
					"HARNESS: wrong module hash"
				)
	dut.beat_clock.value = 0
	dut.wipe_registers.value = 1
	dut.sb_tvalid.value = 0
	dut.sb_tready.value = 0
	dut.plain_valid.value = 0
	dut.plain_ready.value = 0
	dut.reset_lane.value = 0
	await Timer(1, unit="ns")
	return cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))


def _bus(dut: HierarchyObject, ready: bool = True) -> AxiStreamBus:
	return AxiStreamBus.bind(
		dut, prefix="sb", ready=None if ready else False, last=True, keep=True, strb=True, user=True, id=True, dest=True
	)


def _sample(dut: HierarchyObject) -> _Beat:
	return _Beat(
		str(dut.sb_tdata.value),
		str(dut.sb_tlast.value) == "1",
		str(dut.sb_tkeep.value),
		str(dut.sb_tstrb.value),
		str(dut.sb_tuser.value),
		int(dut.sb_tid.value),
		int(dut.sb_tdest.value),
	)


def _drive(dut: HierarchyObject, beat: _Beat) -> None:
	dut.sb_tdata.value = beat.data
	dut.sb_tlast.value = int(beat.last)
	dut.sb_tkeep.value = beat.keep
	dut.sb_tstrb.value = beat.strb
	dut.sb_tuser.value = beat.user
	dut.sb_tid.value = beat.id
	dut.sb_tdest.value = beat.dest


def _traffic(rng: Random, count: int) -> list[_Beat]:
	result = []
	for index in range(count):
		keep = rng.randrange(4)
		strb = rng.randrange(4) & keep
		data = f"{0 if index % 7 == 0 else rng.randrange(65536):016b}"
		if index % 11 == 0:
			data = "XU" + data[2:]
		result.append(
			_Beat(
				data,
				rng.random() < 0.35,
				f"{keep:02b}",
				f"{strb:02b}",
				rng.choice(["XU01Z", "HL010", f"{rng.randrange(32):05b}"]),
				rng.randrange(4),
				rng.randrange(2),
			)
		)
	# Close all eight identities, so a packet receive is always bounded at the tail.
	return result + [_Beat(f"{60000 + i:016b}", True, "11", "11", "00101", i % 4, i // 4) for i in range(8)]


async def _wire(dut: HierarchyObject, values: list[_Beat], ledger: _Ledger, rng: Random, ready: bool) -> None:
	for beat in values:
		for _ in range(rng.randrange(4) if rng.random() < 0.25 else 0):
			await FallingEdge(dut.beat_clock)
			dut.sb_tvalid.value = 0
		await FallingEdge(dut.beat_clock)
		_drive(dut, beat)
		dut.sb_tvalid.value = 1
		while True:
			await RisingEdge(dut.beat_clock)
			if not ready or str(dut.sb_tready.value) == "1":
				ledger.observe(_sample(dut))
				break
	await FallingEdge(dut.beat_clock)
	dut.sb_tvalid.value = 0


@cocotb.test(timeout_time=500000, timeout_unit="ns")
@cocotb.parametrize(seed=_seeds())
async def source_wire_scoreboard(dut: HierarchyObject, seed: int) -> None:
	"""An independent stalled receiver checks every field, stability and absence of extra accepts."""
	cocotb.log.info("source wire seed=%s", seed)
	await _setup(dut)
	rng = Random(seed)
	values = _traffic(rng, _rounds() * 4)
	ledger = _Ledger(seed, values)
	source = AxiStreamSource(_bus(dut), dut.beat_clock)
	await source.initialise()

	async def transmit() -> None:
		for index, beat in enumerate(values):
			if index % 9 == 0:
				await Timer(rng.randrange(1, 25), unit="ns")
			# One-beat frames exercise mixed entry points without changing packet identity.
			if beat.last and index % 2:
				await source.send_frame([beat.data], sidebands=[beat.metadata()])
			else:
				await source.send(beat.data, last=beat.last, sidebands=beat.metadata())

	sending = cocotb.start_soon(transmit())
	peer = Random(seed ^ 0xACE)
	stalled: _Beat | None = None
	for cycle in range(len(values) * 16 + 20):
		await FallingEdge(dut.beat_clock)
		dut.sb_tready.value = int(cycle % 17 < 8 or peer.random() < 0.5)
		await RisingEdge(dut.beat_clock)
		valid, ready = str(dut.sb_tvalid.value) == "1", str(dut.sb_tready.value) == "1"
		if stalled is not None:
			ledger.check(valid and _sample(dut) == stalled, "source changed a stalled transfer")
		if valid and ready:
			ledger.observe(_sample(dut))
		stalled = _sample(dut) if valid and not ready else None
		if sending.done() and cycle > len(values) and not valid:
			break
	ledger.check(sending.done(), "source failed to finish in the cycle budget")
	await sending
	# Give a faulty cleanup another three chances to duplicate the final value.
	dut.sb_tready.value = 1
	for _ in range(3):
		await RisingEdge(dut.beat_clock)
		if str(dut.sb_tvalid.value) == "1":
			ledger.observe(_sample(dut))
	ledger.check(ledger.observed == values, "source omitted traffic")
	await source.close()


@cocotb.test(timeout_time=500000, timeout_unit="ns")
@cocotb.parametrize(seed=_seeds(), ready=[False, True])
async def sink_wire_scoreboard(dut: HierarchyObject, seed: int, ready: bool) -> None:
	"""Independent interleaved traffic is reconciled across mixed raw/packet APIs and idle gaps."""
	cocotb.log.info("sink wire seed=%s ready=%s", seed, ready)
	await _setup(dut)
	values = _traffic(Random(seed), _rounds() * 5)
	ledger = _Ledger(seed, values)
	sink = AxiStreamSink(_bus(dut, ready), dut.beat_clock, buffer_capacity=None if ready else len(values))
	await sink.initialise()
	sending = cocotb.start_soon(_wire(dut, values, ledger, Random(seed ^ 33), ready))
	rng = Random(seed ^ 0x1234)
	while ledger.cursor < len(values):
		if rng.random() < 0.3:
			await Timer(rng.randrange(1, 150), unit="ns")
		frame = rng.random() < 0.65
		expected = ledger.expected(frame)
		actual = await sink.recv_frame() if frame else [await sink.recv()]
		ledger.compare(actual, expected)
		if not ready:
			retained = len(ledger.observed) - len(ledger.delivered) - len(ledger.discarded)
			ledger.check(sink._retained == retained, f"retention mismatch: expected={retained}, got={sink._retained}")
	await sending
	ledger.complete()
	ledger.check(not sink._packets and not sink._queue and sink._retained == 0, "sink retained completed traffic")
	await sink.close()


async def _result[T](operation: Coroutine[Any, Any, T]) -> T | Exception:
	try:
		return await operation
	except Exception as exc:
		return exc


class _ReadFailure(HandlePayload):
	def __init__(self, dut: HierarchyObject) -> None:
		super().__init__(dut.sb_tdata)
		self.failure: Exception | None = None
		self.reads = 0

	def read(self) -> PayloadValue:
		self.reads += 1
		if self.failure is not None:
			raise self.failure
		return super().read()


@cocotb.test(timeout_time=1000000, timeout_unit="ns")
@cocotb.parametrize(seed=_seeds())
async def lifecycle_accounting(dut: HierarchyObject, seed: int) -> None:
	"""Repeat reset/cancel/fault/close recovery; account accepted data and retire old background tasks."""
	cocotb.log.info("lifecycle seed=%s rounds=%s", seed, _rounds())
	clock = await _setup(dut)
	rng = Random(seed)
	payload = _ReadFailure(dut)
	active_high = bool(seed & 1)
	dut.reset_lane.value = int(not active_high)
	sink = AxiStreamSink(
		_bus(dut, False),
		dut.beat_clock,
		payload=payload,
		buffer_capacity=6,
		reset=dut.reset_lane,
		reset_active_high=active_high,
	)
	accepted = delivered = discarded = 0
	for epoch in range(_rounds()):
		payload.failure = None
		await sink.initialise()
		tasks = [sink._monitor_task, sink._pin_task, sink._capture_task]
		assert all(task is not None for task in tasks)
		action = epoch % 6
		# The distinctive first value of each epoch catches old snapshot/prefix replay.
		count = 7 if action == 4 else 3
		values = [
			_Beat(f"{(epoch * 41 + i) % 65536:016b}", action in (0, 3, 4, 5), "11", "01", "00111", i % 2, 0)
			for i in range(count)
		]
		ledger = _Ledger(seed, values)
		if action in (1, 2):
			pending = cocotb.start_soon(_result(sink.recv_frame()))
		else:
			pending = None
		if action == 3:
			# Retain an older snapshot, then fail reading a newly accepted one.
			await _wire(dut, values[:1], _Ledger(seed, values[:1]), rng, False)
			payload.failure = RuntimeError(f"injected read failure epoch={epoch}")
			await _wire(dut, values[1:], _Ledger(seed, values[1:]), rng, False)
			accepted += count
		else:
			await _wire(dut, values, ledger, rng, False)
			accepted += len(ledger.observed)
		await Timer(1, unit="ns")
		expected_retained = 6 if action == 4 else 1 if action == 3 else count
		assert sink._retained == expected_retained, (
			f"[reliability] seed={seed} epoch={epoch}: retention before interruption "
			f"expected={expected_retained}, got={sink._retained}"
		)
		if pending is not None:
			assert not pending.done(), f"[reliability] seed={seed}: incomplete packet unexpectedly completed"
		if action in (0, 5):
			for value in values:
				actual = await sink.recv()
				assert str(actual.data) == value.data, f"[reliability] seed={seed} epoch={epoch}: stale delivery"
				delivered += 1
		elif action == 1:
			dut.reset_lane.value = int(active_high)
			assert pending is not None
			assert isinstance(await pending, TransferReset), f"[reliability] seed={seed}: reset not delivered"
			discarded += count
			await Timer(1, unit="ns")
			tasks.extend([sink._monitor_task, sink._pin_task, sink._capture_task])
			assert sink._retained == 0 and not sink._queue and not sink._packets
			dut.reset_lane.value = int(not active_high)
			for _ in range(4):
				await FallingEdge(dut.beat_clock)
			assert sink._initialised, f"[reliability] seed={seed}: healthy pin reset did not resume"
		elif action == 2:
			assert pending is not None
			pending.cancel()
			with pytest.raises(CancelledError):
				await pending
			discarded += count
			assert sink._retained == 0 and not sink._queue and not sink._packets
		elif action in (3, 4):
			expected_error = payload.failure if action == 3 else sink._fault
			assert isinstance(expected_error, RuntimeError if action == 3 else OverflowError)
			with pytest.raises(type(expected_error)) as caught:
				await sink.recv()
			assert caught.value is expected_error, f"[reliability] seed={seed}: background fault hidden"
			discarded += count
		if action in (2, 3, 4):
			original_fault = sink._fault
			dut.reset_lane.value = int(active_high)
			await Timer(1, unit="ns")
			tasks.extend([sink._monitor_task, sink._pin_task, sink._capture_task])
			assert sink._retained == 0 and not sink._queue and not sink._packets
			dut.reset_lane.value = int(not active_high)
			for _ in range(4):
				await FallingEdge(dut.beat_clock)
			with pytest.raises(EndpointStateError if action == 2 else type(original_fault)) as caught:
				await sink.recv()
			if action != 2:
				assert caught.value is original_fault, f"[reliability] seed={seed}: pin cycle replaced first fault"
		# Close midway through a low phase: cancelled collectors must finish
		# without requiring another edge, including when this clock is stopped.
		tasks.extend([sink._monitor_task, sink._pin_task, sink._capture_task])
		clock.cancel()
		await sink.close()
		await Timer(1, unit="ns")
		assert all(task is None or task.done() for task in tasks), (
			f"[reliability] seed={seed} epoch={epoch}: background task survived close"
		)
		assert sink._capture_task is sink._monitor_task is sink._pin_task is None
		assert sink._retained == 0 and not sink._queue and not sink._packets
		assert accepted == delivered + discarded, f"[reliability] seed={seed} epoch={epoch}: unaccounted acceptance"
		dut.reset_lane.value = int(active_high)
		await Timer(1, unit="ns")
		dut.reset_lane.value = int(not active_high)
		await sink.close()
		clock = cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
		reads = payload.reads
		# Physical traffic while capture is closed is intentionally ignored,
		# and must never call the adapter or be replayed in the next epoch.
		await _wire(dut, values[:1], _Ledger(seed, values[:1]), rng, False)
		await Timer(1, unit="ns")
		assert payload.reads == reads, f"[reliability] seed={seed}: collector read after close"
		with pytest.raises(EndpointStateError):
			await sink.recv()
	await sink.close()
	cocotb.log.info("lifecycle seed=%s accepted=%s delivered=%s discarded=%s", seed, accepted, delivered, discarded)

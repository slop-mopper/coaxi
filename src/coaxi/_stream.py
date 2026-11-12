# _stream.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Individual-transfer and frame AXI-Stream endpoints for event-driven simulation."""

import logging
from typing import cast, overload
from dataclasses import dataclass, field
from collections import deque
from collections.abc import Sequence

import cocotb
from cocotb.task import Task, current_task
from cocotb.types import Logic, LogicArray
from cocotb.simtime import get_sim_time
from cocotb.triggers import (
	Event,
	First,
	Timer,
	Trigger,
	ReadOnly,
	ValueChange,
	RisingEdge,
	FallingEdge,
	current_gpi_trigger,
)

from ._binding import Signal, _Control, _control, _resolve, AxiStreamBus, SignalBindingError
from ._payload import Payload, HandlePayload, PayloadValue, _AbsentPayload
from ._sideband import _Values, _identity, _SidebandAccess, AxiStreamSidebands

_log = logging.getLogger("coaxi.stream")


class ProtocolValueError(ValueError):
	"""A reset pin, accepted control, byte-qualifier pair or packet assembly key is invalid."""


class EndpointStateError(RuntimeError):
	"""An endpoint needs initialisation, is held in reset, or has an active operation."""


class TransferReset(RuntimeError):
	"""Pin reset, local initialisation or close invalidated work; acceptance is not undone."""


@dataclass(frozen=True)
class AxiStreamTransfer[T]:
	"""One accepted transfer, with independent payload and raw sideband snapshots.

	None denotes a physically absent signal, rather than its protocol default.
	Absent keep means all bytes present, absent strb follows effective keep,
	and absent user/id/dest have effective value zero. No byte compaction or
	application-specific interpretation is performed.
	"""

	data: T
	"""Payload captured at the accepting rising edge."""
	last: bool | None
	"""Sampled frame boundary, or None when no last signal is bound."""
	keep: Logic | LogicArray | None = None
	"""Raw byte-presence mask, or None when absent."""
	strb: Logic | LogicArray | None = None
	"""Raw data/position-byte mask, or None when absent."""
	user: Logic | LogicArray | None = None
	"""Raw application-defined metadata, or None when absent."""
	id: Logic | LogicArray | None = None
	"""Raw stream identifier, or None when absent."""
	dest: Logic | LogicArray | None = None
	"""Raw routing destination, or None when absent."""


def _bit(handle: _Control, role: str) -> bool:
	value = str(handle.value)
	if value not in ("0", "1"):
		raise ProtocolValueError(f"{role} ({handle._path}) must be 0 or 1, got {value}")
	return value == "1"


@dataclass
class _Operation:
	interrupted: Event = field(default_factory=Event)
	error: Exception = field(
		default_factory=lambda: TransferReset("endpoint interrupted work; accepted traffic is not undone")
	)


class _Endpoint[T]:
	def __init__(
		self,
		bus: AxiStreamBus,
		clock: Signal,
		payload: Payload[T] | None,
		reset: Signal | None,
		reset_active_high: bool,
	) -> None:
		self._bus = bus
		self._clock = bus.resolve_clock(clock)
		if type(reset_active_high) is not bool:
			raise TypeError("reset_active_high must be a bool")
		self._reset = None if reset is None else _control(_resolve(bus._entity, reset, "reset"), "reset")
		if self._reset is not None and self._reset.is_const:
			raise SignalBindingError(f"reset: {self._reset._path} must be mutable to monitor changes")
		if self._reset is not None and self._reset._path in {handle._path for handle in [self._clock, *bus._handles()]}:
			raise SignalBindingError("reset must be separate from the clock and stream signals")
		self._reset_active_high = reset_active_high
		if bus.data is None and payload is not None:
			raise ValueError("a payload adapter requires a data signal")
		if payload is not None:
			self._payload = payload
		else:
			default_payload = _AbsentPayload() if bus.data is None else HandlePayload(bus.data)
			self._payload = cast(Payload[T], default_payload)
		self._name = bus.valid._path
		self._sidebands = _SidebandAccess(bus)
		self._initialised = False
		self._resetting = False
		self._active: _Operation | None = None
		self._completed_at: int | None = None
		self._needs_initialise = True
		self._fault: Exception | None = None
		self._state_changed = Event()
		self._monitor_generation: object | None = None
		self._monitor_task: Task[None] | None = None
		self._pin_cycle: object | None = None
		self._pin_task: Task[None] | None = None
		self._pin_value: str | None = None
		self._pin_ready = False

	def _begin(self) -> object:
		self._observe_reset()
		if self._fault is not None:
			raise self._fault
		if not self._initialised or self._resetting:
			raise EndpointStateError("await initialise() before using this endpoint; reset may be held or releasing")
		if self._active is not None:
			raise EndpointStateError("only one operation may be active on an endpoint")
		token = _Operation()
		self._active = token
		return token

	async def _wait_edge(self, edge: Trigger, token: object | None) -> None:
		if self._reset is None or not isinstance(token, _Operation):
			await edge
		else:
			# First's waiters all run in this GPI callback, before HDL resumes.
			# Never wait for ReadOnly before taking the handshake snapshot.
			await First(edge, token.interrupted.wait())
			self._check(token)

	async def _start_edge(self) -> None:
		# Only a successful preceding transfer can share its cleanup edge. Time
		# alone is insufficient: ReadOnly/ReadWrite can occur in the same step.
		edge = FallingEdge(self._clock)
		same_time = self._completed_at == int(get_sim_time(unit="step"))
		self._completed_at = None
		if not same_time or current_gpi_trigger() is not edge:
			await self._wait_edge(edge, self._active)

	def _finish_beat(self) -> None:
		self._completed_at = int(get_sim_time(unit="step"))

	def _finish(self) -> None:
		self._active = None

	def _check(self, token: object) -> None:
		self._observe_reset()
		if self._active is not token:
			if isinstance(token, _Operation):
				raise token.error
			raise TransferReset("endpoint interrupted work; accepted traffic is not undone")
		if self._fault is not None:
			raise self._fault

	def _abort(self, token: object) -> None:
		if self._active is token:
			self._active = None
			self._initialised = False
			self._needs_initialise = True
			self._completed_at = None

	def _signal_state(self) -> None:
		self._state_changed.set()
		self._state_changed = Event()

	def _invalidate(self) -> None:
		self._initialised = False
		if self._active is not None:
			if self._fault is not None:
				self._active.error = self._fault
			self._active.interrupted.set()
		self._active = None
		self._completed_at = None
		self._signal_state()

	def _after_initialise(self) -> None:
		pass

	def _clear(self) -> None:
		raise NotImplementedError

	def _stop_monitor(self) -> None:
		# Invalidate before cancellation: an old continuation must not touch a
		# replacement operation, queue, fault or set of driven outputs.
		self._monitor_generation = None
		self._pin_cycle = None
		for task in (self._monitor_task, self._pin_task):
			if task is not None:
				task.cancel()
		self._monitor_task = None
		self._pin_task = None
		self._pin_value = None
		self._pin_ready = False

	def _observe_reset(self) -> None:
		if self._reset is None or self._monitor_generation is None:
			return
		value = str(self._reset.value)
		if value == self._pin_value:
			return
		self._pin_value = value
		self._pin_ready = False
		if value not in ("0", "1"):
			if self._fault is None:
				self._fault = ProtocolValueError(f"reset ({self._reset._path}) must be 0 or 1, got {value}")
			self._needs_initialise = True
		self._invalidate()
		if self._pin_task is not None:
			self._pin_task.cancel()
		cycle = object()
		self._pin_cycle = cycle
		inactive = value in ("0", "1") and (value == "1") != self._reset_active_high
		self._pin_task = cocotb.start_soon(self._settle_reset(self._monitor_generation, cycle, inactive))
		_log.debug("%s reset pin=%s, inactive=%s", type(self).__name__, value, inactive)

	async def _watch_reset(self, generation: object) -> None:
		assert self._reset is not None
		try:
			while self._monitor_generation is generation:
				await ValueChange(self._reset)
				if self._monitor_generation is generation:
					self._observe_reset()
		except Exception as exc:
			# Callback registration/read failures belong to the endpoint, just
			# like collector faults. Never let an unobserved task abort the test.
			if self._monitor_generation is generation:
				if self._fault is None:
					self._fault = exc
				self._needs_initialise = True
				self._invalidate()

	def _owns_pin_cycle(self, generation: object, cycle: object) -> bool:
		return self._monitor_generation is generation and self._pin_cycle is cycle

	async def _settle_reset(self, generation: object, cycle: object, inactive: bool) -> None:
		try:
			if current_gpi_trigger() is ReadOnly():
				await Timer(1, unit="step")
			if not self._owns_pin_cycle(generation, cycle):
				return
			self._clear()
			self._signal_state()
			if not inactive:
				return
			# R0 samples inactive; R1 is the following rising edge. Resume at F1
			# so the first new transfer can be accepted no earlier than R2.
			for edge in (RisingEdge(self._clock), RisingEdge(self._clock), FallingEdge(self._clock)):
				await edge
				if not self._owns_pin_cycle(generation, cycle):
					return
				assert self._reset is not None
				if str(self._reset.value) != self._pin_value:
					return
			self._pin_ready = True
			if not self._needs_initialise and self._fault is None:
				self._initialised = True
				self._after_initialise()
			self._signal_state()
			_log.debug("%s reset release complete", type(self).__name__)
		except Exception as exc:
			if self._owns_pin_cycle(generation, cycle):
				if self._fault is None:
					self._fault = exc
				self._needs_initialise = True
				self._invalidate()

	async def initialise(self) -> None:
		"""Initialise or recover local state and owned outputs; never drive reset.

		Without a reset pin, clear at the next falling edge. With one, start
		monitoring and clear as soon as writes are permitted, then wait through
		any asserted reset and its release gate: inactive sampled at R0, then
		R1, then F1. The earliest transfer acceptance is R2. Call initially,
		after errors/cancellation, or to reopen after close(). The clock must
		contain literal 0/1 from before initialisation onwards (unmonitored).
		The caller must deassert the pin synchronously; this is no synchroniser.

		Pending operations are invalidated, retained traffic is discarded, and
		accepted traffic cannot be undone. Catch TransferReset inside spawned
		operations. Overlapping initialise/close calls fail. A held reset or
		stopped clock can make this wait indefinitely. Cancellation leaves manual
		recovery required, but an armed pin monitor continues output safety.
		"""
		if self._resetting:
			raise EndpointStateError("initialise or close is already active")
		self._resetting = True
		self._needs_initialise = True
		self._fault = None
		self._invalidate()
		self._stop_monitor()
		try:
			if self._reset is None:
				await FallingEdge(self._clock)
				self._clear()
			else:
				generation = object()
				self._monitor_generation = generation
				self._observe_reset()
				self._monitor_task = cocotb.start_soon(self._watch_reset(generation))
				while not self._pin_ready:
					if self._fault is not None:
						raise self._fault
					await self._state_changed.wait()
			if self._fault is not None:
				raise self._fault
			self._needs_initialise = False
			self._initialised = True
			self._after_initialise()
			_log.debug("%s initialised", type(self).__name__)
		finally:
			self._resetting = False

	async def close(self) -> None:
		"""Stop monitoring/capture and invalidate work; initialise() explicitly reopens.

		Discard retained traffic immediately. Clear source outputs or a sink's
		ready at the next falling edge; a no-ready sink needs no clock edge.
		Repeated closes are safe; overlapping initialise/close calls fail.
		Pin changes cannot reopen a closed endpoint. Cancellation leaves the
		endpoint closed, but can leave driven outputs pending local cleanup.
		"""
		if self._resetting:
			raise EndpointStateError("initialise or close is already active")
		self._resetting = True
		self._needs_initialise = True
		self._fault = None
		self._stop_monitor()
		self._invalidate()
		try:
			if isinstance(self, AxiStreamSource) or self._bus.ready is not None:
				await FallingEdge(self._clock)
				self._clear()
		finally:
			self._resetting = False


class AxiStreamSource[T = PayloadValue | None](_Endpoint[T]):
	"""Drive individual transfers or frames, with stable data/last under backpressure.

	``bus`` supplies the handles; ``clock`` is an exact name in its entity or
	a handle. The clock must contain only literal 0/1 values from before the
	first initialisation onwards, including while idle. Weak L/H and unresolved clocks
	are unsupported; this caller precondition is not monitored.
	``payload`` defaults to HandlePayload for data-bearing buses. Default T is
	PayloadValue | None: absent data requires send(None), returns None at the
	sink, and rejects an adapter. With data present, None is rejected by the
	default adapter. Pass Payload[T] for precise application-specific types.
	Absent ready accepts every valid edge without backpressure.
	``reset`` optionally supplies an exact reset name or one-bit handle, without
	discovery or pin driving. ``reset_active_high`` defaults to False (active-low);
	True selects active-high. Literal pin 0/1 values are required. After
	initialise(), assertion clears owned outputs asynchronously and interrupts
	work. Release samples inactive at R0 and R1, enabling after R1's falling
	edge; earliest acceptance is R2. Pin-only interruptions recover automatically;
	prior faults/cancellation still require initialise(). The caller must
	deassert synchronously; the endpoint is not a reset synchroniser.

	Await initialise() before use. An optional reset monitor runs until close().
	Only one send or send_frame may be active. Falling-edge drives and pre-update rising-edge
	sampling target event-driven simulators such as nvc. Immediately consecutive
	awaits can reuse the cleanup edge and sustain one transfer per clock cycle
	when the peer is ready. No low valid pulse is required between calls.
	"""

	@overload
	def __init__(
		self: "AxiStreamSource[PayloadValue | None]",
		bus: AxiStreamBus,
		clock: Signal,
		*,
		payload: None = None,
		reset: Signal | None = None,
		reset_active_high: bool = False,
	) -> None: ...

	@overload
	def __init__(
		self,
		bus: AxiStreamBus,
		clock: Signal,
		*,
		payload: Payload[T],
		reset: Signal | None = None,
		reset_active_high: bool = False,
	) -> None: ...

	def __init__(
		self,
		bus: AxiStreamBus,
		clock: Signal,
		*,
		payload: Payload[T] | None = None,
		reset: Signal | None = None,
		reset_active_high: bool = False,
	) -> None:
		super().__init__(bus, clock, payload, reset, reset_active_high)

	def _clear(self) -> None:
		self._bus.valid.set(0)
		if self._bus.last is not None:
			self._bus.last.set(0)
		try:
			self._payload.clear()
		finally:
			self._sidebands.clear()

	async def send(self, data: T, *, last: bool | None = None, sidebands: AxiStreamSidebands | None = None) -> None:
		"""Drive data until accepted, then clear valid at the next falling edge.

		``data`` is owned by the caller but must not be mutated until this call
		finishes. ``last`` must be an explicit bool on a framed bus and None on
		an unframed bus. This method schedules cleanup at the following falling
		edge and returns there, not at acceptance. An immediately following send
		can drive its next value on that same edge, superseding valid's clearing
		write. A simulator-phase or time wait between calls can insert idle cycles.
		``sidebands`` optionally supplies metadata, independently of data.
		Omitting it selects keep=all ones, strb=effective keep and user/id/dest=0
		on bound signals. All sidebands remain stable during backpressure.
		Invalid metadata fails before wire activity without requiring initialise().
		Errors/cancellation require initialise(); a transfer may already have been
		accepted, so automatic retry can duplicate data.
		"""
		if self._bus.last is None:
			if last is not None:
				raise ValueError("last requires a bound last signal")
		elif type(last) is not bool:
			raise ValueError("a framed transfer requires last=True or last=False")
		metadata = self._sidebands.prepare(sidebands)
		token = self._begin()
		try:
			await self._send_one(token, data, last, metadata)
			self._finish()
		except BaseException:
			# No asynchronous cleanup: cancellation must be re-raised immediately.
			self._abort(token)
			raise

	async def send_frame(self, data: Sequence[T], *, sidebands: Sequence[AxiStreamSidebands] | None = None) -> None:
		"""Send a non-empty sequence, generating last on its final transfer.

		``data`` contains payloads, not AxiStreamTransfer objects. A bound last
		signal is required. The sequence and its values remain caller-owned;
		do not mutate either until this call finishes. Generators are not
		accepted. ``sidebands`` is an optional parallel sequence, with exactly
		one AxiStreamSidebands per payload. Omit it for default values on every
		beat. A packet keeps a constant effective (id, dest); use individual
		send calls to interleave different packets. Packet helpers require
		literal 0/1 identifiers; individual transfers retain meta-values.
		Non-sequence/empty input, metadata length mismatch or absent last fails
		before any wire activity, without requiring initialise().

		Reserve the endpoint for the whole frame. Transfers use send's timing,
		including full rate within and between immediately consecutive frames.
		Return None at the final transfer's falling-edge cleanup.
		Payloads are validated as they are driven, not all before transmission.
		In-progress errors or cancellation require initialise(); an accepted prefix or
		the entire frame may already have reached the peer. No rollback or retry
		is performed, and local initialisation does not restore frame alignment.
		"""
		if self._bus.last is None:
			raise ValueError("send_frame requires a bound last signal")
		if not isinstance(data, Sequence):
			raise TypeError("frame data must be a non-empty sequence")
		count = len(data)
		if count == 0:
			raise ValueError("a frame must contain at least one transfer")
		if sidebands is not None:
			if not isinstance(sidebands, Sequence):
				raise TypeError("frame sidebands must be a sequence or None")
			if len(sidebands) != count:
				raise ValueError("frame sidebands must have one entry per payload")
		token = self._begin()
		try:
			identity = None
			for index in range(count):
				metadata = self._sidebands.prepare(None if sidebands is None else sidebands[index])
				key = _identity(metadata.get("id"), metadata.get("dest"))
				if identity is not None and key != identity:
					raise ValueError(
						f"send_frame requires a constant effective (id, dest); "
						f"entry {index} (zero-based) changes identity from {identity} to {key}"
					)
				identity = key
				await self._send_one(token, data[index], index == count - 1, metadata)
			_log.debug("sent frame on %s, transfers=%s", self._name, count)
			self._finish()
		except BaseException:
			self._abort(token)
			raise

	async def _send_one(self, token: object, data: T, last: bool | None, metadata: _Values) -> None:
		await self._start_edge()
		self._check(token)
		self._payload.drive(data)
		self._sidebands.drive(metadata)
		if self._bus.last is not None:
			self._bus.last.set(int(bool(last)))
		self._bus.valid.set(1)
		while True:
			await self._wait_edge(RisingEdge(self._clock), token)
			self._check(token)
			if self._bus.ready is None or _bit(self._bus.ready, "ready"):
				break
		_log.debug("sent transfer on %s, last=%s", self._name, last)
		await self._wait_edge(FallingEdge(self._clock), token)
		self._check(token)
		self._bus.valid.set(0)
		if self._bus.last is not None:
			self._bus.last.set(0)
		self._finish_beat()


class AxiStreamSink[T = PayloadValue | None](_Endpoint[T]):
	"""Receive individual transfers or packets, with continuous capture without ready.

	``bus``, ``clock``, optional ``payload``, ``reset`` and ``reset_active_high``
	have the source's meanings,
	including its unmonitored, literal-0/1 clock precondition.
	Await initialise() before use. The sink owns only ready and never clears incoming
	payloads. Only one recv or recv_frame may be active. With ready, reception
	is call-driven; immediately consecutive awaits sustain one beat per cycle.
	Without ready, initialisation starts continuous capture, including while idle.
	``buffer_capacity`` is an optional positive count of all retained,
	undelivered transfers, including packet prefixes and in-flight snapshots.
	None is unlimited. A finite capacity is rejected on ready-backed buses.
	OverflowError or a capture exception stops capture and is raised by the
	current/next receive before older buffered values. initialise() is required.
	Backlog returns immediately without advancing simulation time; live
	snapshots become available at the falling edge after acceptance.
	Use close() to stop capture and monitoring; a later initialise() restarts both.
	"""

	@overload
	def __init__(
		self: "AxiStreamSink[PayloadValue | None]",
		bus: AxiStreamBus,
		clock: Signal,
		*,
		payload: None = None,
		buffer_capacity: int | None = None,
		reset: Signal | None = None,
		reset_active_high: bool = False,
	) -> None: ...

	@overload
	def __init__(
		self,
		bus: AxiStreamBus,
		clock: Signal,
		*,
		payload: Payload[T],
		buffer_capacity: int | None = None,
		reset: Signal | None = None,
		reset_active_high: bool = False,
	) -> None: ...

	def __init__(
		self,
		bus: AxiStreamBus,
		clock: Signal,
		*,
		payload: Payload[T] | None = None,
		buffer_capacity: int | None = None,
		reset: Signal | None = None,
		reset_active_high: bool = False,
	) -> None:
		if buffer_capacity is not None:
			if type(buffer_capacity) is not int:
				raise TypeError("buffer_capacity must be a positive integer or None")
			if buffer_capacity <= 0:
				raise ValueError("buffer_capacity must be positive")
			if bus.ready is not None:
				raise ValueError("buffer_capacity is only supported without ready")
		super().__init__(bus, clock, payload, reset, reset_active_high)
		self._capacity = buffer_capacity
		self._packets: dict[tuple[int, int], list[AxiStreamTransfer[T]]] = {}
		self._queue: deque[AxiStreamTransfer[T]] = deque()
		self._retained = 0
		self._changed = Event()
		self._capture_task: Task[None] | None = None
		self._capture_generation: object | None = None

	def _notify(self) -> None:
		self._changed.set()
		self._changed = Event()

	def _stop_capture(self) -> None:
		self._capture_generation = None
		task = self._capture_task
		self._capture_task = None
		# The collector may itself observe reset before the pin watcher. Let
		# its generation guard return rather than trying to cancel this task.
		if task is not None and task is not current_task():
			task.cancel()

	def _discard(self) -> None:
		self._packets.clear()
		self._queue.clear()
		self._retained = 0

	def _invalidate(self) -> None:
		super()._invalidate()
		self._stop_capture()
		self._discard()
		self._notify()

	def _after_initialise(self) -> None:
		if self._bus.ready is None:
			generation = object()
			self._capture_generation = generation
			self._capture_task = cocotb.start_soon(self._capture(generation))

	def _abort(self, token: object) -> None:
		if self._active is token:
			self._stop_capture()
			self._discard()
			self._notify()
		super()._abort(token)

	def _clear(self) -> None:
		if self._bus.ready is not None:
			self._bus.ready.set(0)
		self._discard()

	def _release(self, count: int) -> None:
		if self._bus.ready is None:
			self._retained -= count

	async def _capture(self, generation: object) -> None:
		try:
			while self._capture_generation is generation:
				await RisingEdge(self._clock)
				self._observe_reset()
				if self._capture_generation is not generation:
					return
				if not _bit(self._bus.valid, "valid"):
					continue
				transfer = self._read_transfer()
				if self._capacity is not None and self._retained >= self._capacity:
					raise OverflowError(f"buffer_capacity={self._capacity} exceeded; initialise() required")
				self._retained += 1
				# Count the snapshot immediately, but publish it only at cleanup.
				# A waiting receive therefore keeps the existing completion timing.
				await FallingEdge(self._clock)
				self._observe_reset()
				if self._capture_generation is not generation:
					return
				self._queue.append(transfer)
				self._notify()
		except Exception as exc:
			# Observe faults here, even if the caller is idle. The receive API
			# delivers the original exception before any older buffered values.
			if self._capture_generation is generation:
				self._fault = exc
				self._needs_initialise = True
				self._notify()
		finally:
			if self._capture_generation is generation:
				self._capture_generation = None
				self._capture_task = None

	async def recv(self) -> AxiStreamTransfer[T]:
		"""Assert ready, capture one accepted transfer, clear ready, then return.

		Sample data/last immediately at the rising edge, before clocked HDL
		updates; do not wait for ReadOnly. Payload meta-values are preserved.
		Valid and accepted last must be exactly 0 or 1 (weak L/H also fail).
		Absent last produces None. Schedule cleanup and return at the following
		falling edge. An immediately following recv can reassert ready on that
		same edge, without a low pulse; simulator-phase or time waits between
		calls can insert idle cycles. Errors and cancellation require initialise();
		accepted data is not rolled back. Bound sidebands are captured at that
		same accepting edge; absent signals remain None. Literal keep=0/strb=1
		lane pairs raise ProtocolValueError after acceptance. Meta-valued
		sidebands are preserved, without proving their protocol validity.
		No other optional sidebands are needed. Return individual transfers in
		wire order. Discard any retained prefix for this transfer's identity,
		so packet assembly cannot splice across a raw-consumed beat. If the
		identity is unresolved, discard all retained prefixes conservatively.
		Without ready, consume continuously captured traffic instead of driving.
		Backlog returns immediately; a waiting receive completes at the falling
		edge following acceptance. Capture faults take priority over backlog.
		Absent data returns None.
		"""
		token = self._begin()
		try:
			transfer = await self._recv_one(token)
			self._check(token)
			try:
				key = _identity(transfer.id, transfer.dest)
			except ValueError:
				self._release(sum(len(packet) for packet in self._packets.values()))
				self._packets.clear()
			else:
				self._release(len(self._packets.pop(key, [])))
			self._release(1)
			self._finish()
			return transfer
		except BaseException:
			self._abort(token)
			raise

	async def recv_frame(self, *, max_transfers: int | None = None) -> list[AxiStreamTransfer[T]]:
		"""Assemble the next completed packet, separately for each (id, dest).

		A bound last signal is required. ``max_transfers`` is an optional positive
		integer length limit per packet; None (the default) collects without
		a length bound. Invalid arguments fail before wire activity and do not
		require initialise(). A packet ending exactly at the limit succeeds. A packet
		reaching that length without last fails after its falling-edge cleanup,
		without deliberately accepting another transfer or draining. Without
		ready, stopping capture cannot prevent further physical acceptance.

		Return a non-empty list of snapshots in packet-completion order.
		Other streams' incomplete packets are retained for subsequent calls.
		Absent id/dest have effective value zero. Assembly requires literal 0/1
		identifiers; use recv() for raw meta-valued identifiers. The limit also
		applies to retained packets, not just transfers read during this call.
		There is no bound on the number of unfinished streams. Collection starts
		at the next accepted transfer; earlier individual receives are not
		replayed, so mixing APIs can return packet suffixes.
		The whole call reserves the endpoint and preserves full-rate timing.

		Use a simulation-time timeout for stalled traffic. The default has no
		memory bound if last never arrives. Length errors, in-progress failures
		and cancellation require initialise() and return no partial list; accepted
		traffic is not undone. Local initialisation does not restore frame alignment.
		Without ready, consume from continuous capture in wire order; backlog
		may produce a complete packet immediately. buffer_capacity includes
		unfinished prefixes and snapshots pending delivery. Capture faults take
		priority over older buffered packets.
		"""
		if self._bus.last is None:
			raise ValueError("recv_frame requires a bound last signal")
		if max_transfers is not None:
			if type(max_transfers) is not int:
				raise TypeError("max_transfers must be a positive integer or None")
			if max_transfers <= 0:
				raise ValueError("max_transfers must be positive")
		token = self._begin()
		try:
			if max_transfers is not None and any(len(packet) >= max_transfers for packet in self._packets.values()):
				raise ValueError(
					f"retained packet has already reached max_transfers={max_transfers}; initialise() required"
				)
			while True:
				transfer = await self._recv_one(token)
				self._check(token)
				try:
					key = _identity(transfer.id, transfer.dest)
				except ValueError as exc:
					raise ProtocolValueError(str(exc)) from exc
				packet = self._packets.setdefault(key, [])
				packet.append(transfer)
				if transfer.last:
					del self._packets[key]
					_log.debug("received packet on %s, identity=%s, transfers=%s", self._name, key, len(packet))
					self._release(len(packet))
					self._finish()
					return packet
				if max_transfers is not None and len(packet) >= max_transfers:
					raise ValueError(f"packet did not end within max_transfers={max_transfers}; initialise() required")
		except BaseException:
			self._abort(token)
			raise

	def _read_transfer(self) -> AxiStreamTransfer[T]:
		data = self._payload.read()
		last = None if self._bus.last is None else _bit(self._bus.last, "last")
		try:
			metadata = self._sidebands.read()
		except ValueError as exc:
			raise ProtocolValueError(str(exc)) from exc
		_log.debug("received transfer on %s, last=%s", self._name, last)
		return AxiStreamTransfer(
			data,
			last,
			metadata.get("keep"),
			metadata.get("strb"),
			metadata.get("user"),
			metadata.get("id"),
			metadata.get("dest"),
		)

	async def _recv_one(self, token: object) -> AxiStreamTransfer[T]:
		if self._bus.ready is None:
			while True:
				self._check(token)
				if self._queue:
					return self._queue.popleft()
				await self._changed.wait()
		await self._start_edge()
		self._check(token)
		self._bus.ready.set(1)
		while True:
			await self._wait_edge(RisingEdge(self._clock), token)
			self._check(token)
			if _bit(self._bus.valid, "valid"):
				transfer = self._read_transfer()
				break
		await self._wait_edge(FallingEdge(self._clock), token)
		self._check(token)
		self._bus.ready.set(0)
		self._finish_beat()
		return transfer

# _stream.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Single-transfer AXI-Stream endpoints for event-driven simulation."""

import logging
from typing import cast, overload
from dataclasses import dataclass

from cocotb.simtime import get_sim_time
from cocotb.triggers import RisingEdge, FallingEdge, current_gpi_trigger

from ._binding import Signal, _Control, AxiStreamBus
from ._payload import Payload, HandlePayload, PayloadValue

_log = logging.getLogger("coaxi.stream")


class ProtocolValueError(ValueError):
	"""A sampled valid, ready or accepted last value is not exactly 0 or 1."""


class EndpointStateError(RuntimeError):
	"""An endpoint needs reset, is resetting, or already has an active operation."""


class TransferReset(RuntimeError):
	"""Local reset invalidated a pending transfer; wire activity is not undone."""


@dataclass(frozen=True)
class AxiStreamTransfer[T]:
	"""One accepted transfer: independent data snapshot and optional last value."""

	data: T
	"""Payload captured at the accepting rising edge."""
	last: bool | None
	"""Sampled frame boundary, or None when no last signal is bound."""


def _bit(handle: _Control, role: str) -> bool:
	value = str(handle.value)
	if value not in ("0", "1"):
		raise ProtocolValueError(f"{role} ({handle._path}) must be 0 or 1, got {value}")
	return value == "1"


class _Endpoint[T]:
	def __init__(self, bus: AxiStreamBus, clock: Signal, payload: Payload[T] | None) -> None:
		self._bus = bus
		self._clock = bus.resolve_clock(clock)
		self._payload = payload if payload is not None else cast(Payload[T], HandlePayload(bus.data))
		self._initialised = False
		self._resetting = False
		self._active: object | None = None
		self._completed_at: int | None = None

	def _begin(self) -> object:
		if not self._initialised or self._resetting:
			raise EndpointStateError("await reset() before using this endpoint")
		if self._active is not None:
			raise EndpointStateError("only one transfer may be active on an endpoint")
		token = object()
		self._active = token
		return token

	async def _start_edge(self) -> None:
		# Only a successful preceding transfer can share its cleanup edge. Time
		# alone is insufficient: ReadOnly/ReadWrite can occur in the same step.
		edge = FallingEdge(self._clock)
		same_time = self._completed_at == int(get_sim_time(unit="step"))
		self._completed_at = None
		if not same_time or current_gpi_trigger() is not edge:
			await edge

	def _finish(self) -> None:
		self._completed_at = int(get_sim_time(unit="step"))
		self._active = None

	def _check(self, token: object) -> None:
		if self._active is not token:
			raise TransferReset("local reset interrupted this transfer; it may already have reached the DUT")

	def _abort(self, token: object) -> None:
		if self._active is token:
			self._active = None
			self._initialised = False
			self._completed_at = None

	def _clear(self) -> None:
		raise NotImplementedError

	async def reset(self) -> None:
		"""Invalidate pending work, then restore owned outputs at a falling edge.

		Start the clock before awaiting this method. It must contain only literal
		0/1 values from before the first reset onwards; invalid clock values are
		not monitored. Source reset clears valid, payload and last; sink reset
		clears ready. Call initially and after any failed or cancelled transfer.
		Overlapping resets are rejected.

		This is destructive local recovery, not a DUT reset or a reset-pin
		monitor. Coordinate it with the DUT's reset during active traffic.
		Transfers before the clearing edge cannot be undone. Catch TransferReset
		inside any spawned transfer coroutine: cocotb may treat an unobserved task
		exception as a test failure before reset returns. Awaiting the task only
		after reset is too late. Cancellation leaves reset required.
		"""
		if self._resetting:
			raise EndpointStateError("reset is already active")
		self._resetting = True
		self._initialised = False
		self._active = None
		self._completed_at = None
		try:
			await FallingEdge(self._clock)
			self._clear()
			self._initialised = True
			_log.debug("%s reset", type(self).__name__)
		finally:
			self._resetting = False


class AxiStreamSource[T = PayloadValue](_Endpoint[T]):
	"""Drive single transfers with stable data/last during backpressure.

	``bus`` supplies the handles; ``clock`` is an exact name in its entity or
	a handle. The clock must contain only literal 0/1 values from before the
	first reset onwards, including while idle. Weak L/H and unresolved clocks
	are unsupported; this caller precondition is not monitored.
	``payload`` defaults to HandlePayload (T = PayloadValue); pass a Payload[T]
	implementation for application-specific values.

	Await reset() before use. No background tasks or queues are started.
	Only one send may be active. Falling-edge drives and pre-update rising-edge
	sampling target event-driven simulators such as nvc. Immediately consecutive
	awaits can reuse the cleanup edge and sustain one transfer per clock cycle
	when the peer is ready. No low valid pulse is required between calls.
	"""

	@overload
	def __init__(
		self: "AxiStreamSource[PayloadValue]", bus: AxiStreamBus, clock: Signal, *, payload: None = None
	) -> None: ...

	@overload
	def __init__(self, bus: AxiStreamBus, clock: Signal, *, payload: Payload[T]) -> None: ...

	def __init__(self, bus: AxiStreamBus, clock: Signal, *, payload: Payload[T] | None = None) -> None:
		super().__init__(bus, clock, payload)

	def _clear(self) -> None:
		self._bus.valid.set(0)
		if self._bus.last is not None:
			self._bus.last.set(0)
		self._payload.clear()

	async def send(self, data: T, *, last: bool | None = None) -> None:
		"""Drive data until accepted, then clear valid at the next falling edge.

		``data`` is owned by the caller but must not be mutated until this call
		finishes. ``last`` must be an explicit bool on a framed bus and None on
		an unframed bus. This method schedules cleanup at the following falling
		edge and returns there, not at acceptance. An immediately following send
		can drive its next value on that same edge, superseding valid's clearing
		write. A simulator-phase or time wait between calls can insert idle cycles.
		Errors/cancellation require reset; a transfer may already have been
		accepted, so automatic retry can duplicate data.
		"""
		if self._bus.last is None:
			if last is not None:
				raise ValueError("last requires a bound last signal")
		elif type(last) is not bool:
			raise ValueError("a framed transfer requires last=True or last=False")
		token = self._begin()
		try:
			await self._start_edge()
			self._check(token)
			self._payload.drive(data)
			if self._bus.last is not None:
				self._bus.last.set(int(bool(last)))
			self._bus.valid.set(1)
			while True:
				await RisingEdge(self._clock)
				self._check(token)
				if _bit(self._bus.ready, "ready"):
					break
			_log.debug("sent transfer on %s, last=%s", self._bus.data._path, last)
			await FallingEdge(self._clock)
			self._check(token)
			self._bus.valid.set(0)
			if self._bus.last is not None:
				self._bus.last.set(0)
			self._finish()
		except BaseException:
			# No asynchronous cleanup: cancellation must be re-raised immediately.
			self._abort(token)
			raise


class AxiStreamSink[T = PayloadValue](_Endpoint[T]):
	"""Accept single transfers; only an active recv call asserts ready.

	``bus``, ``clock`` and optional ``payload`` have the source's meanings,
	including its unmonitored, literal-0/1 clock precondition.
	Await reset() before use. The sink owns only ready and never clears incoming
	payloads. One recv may be active; no background tasks or queues are started.
	Immediately consecutive awaits can sustain one transfer per clock cycle;
	ready need not pulse low between calls.
	"""

	@overload
	def __init__(
		self: "AxiStreamSink[PayloadValue]", bus: AxiStreamBus, clock: Signal, *, payload: None = None
	) -> None: ...

	@overload
	def __init__(self, bus: AxiStreamBus, clock: Signal, *, payload: Payload[T]) -> None: ...

	def __init__(self, bus: AxiStreamBus, clock: Signal, *, payload: Payload[T] | None = None) -> None:
		super().__init__(bus, clock, payload)

	def _clear(self) -> None:
		self._bus.ready.set(0)

	async def recv(self) -> AxiStreamTransfer[T]:
		"""Assert ready, capture one accepted transfer, clear ready, then return.

		Sample data/last immediately at the rising edge, before clocked HDL
		updates; do not wait for ReadOnly. Payload meta-values are preserved.
		Valid and accepted last must be exactly 0 or 1 (weak L/H also fail).
		Absent last produces None. Schedule cleanup and return at the following
		falling edge. An immediately following recv can reassert ready on that
		same edge, without a low pulse; simulator-phase or time waits between
		calls can insert idle cycles. Errors and cancellation require reset;
		accepted data is not rolled back. No other optional sidebands are needed.
		"""
		token = self._begin()
		try:
			await self._start_edge()
			self._check(token)
			self._bus.ready.set(1)
			while True:
				await RisingEdge(self._clock)
				self._check(token)
				if _bit(self._bus.valid, "valid"):
					data = self._payload.read()
					last = None if self._bus.last is None else _bit(self._bus.last, "last")
					break
			_log.debug("received transfer on %s, last=%s", self._bus.data._path, last)
			await FallingEdge(self._clock)
			self._check(token)
			self._bus.ready.set(0)
			self._finish()
			return AxiStreamTransfer(data, last)
		except BaseException:
			self._abort(token)
			raise

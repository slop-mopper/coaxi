# _binding.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Bind protocol roles independently of HDL naming conventions."""

from typing import Self
from dataclasses import dataclass, field

from cocotb.handle import HierarchyObject, LogicArrayObject, LogicObject, SimHandleBase

type Signal = str | SimHandleBase
"""An exact child name within an entity, or an already-bound cocotb handle."""

type _Control = LogicObject | LogicArrayObject


class SignalBindingError(ValueError):
	"""A required signal is missing, aliased, or has an unsupported control type."""


def _resolve(entity: HierarchyObject | None, signal: Signal, role: str) -> SimHandleBase:
	if isinstance(signal, SimHandleBase):
		return signal
	if not isinstance(signal, str):
		raise SignalBindingError(f"{role}: expected an HDL name or cocotb handle")
	if entity is None:
		raise SignalBindingError(f"{role}: resolving {signal!r} requires an entity")
	try:
		return entity[signal]
	except KeyError as exc:
		# Some VHPI backends cannot look up punctuation in extended identifiers.
		# Enumeration supplies their exact names without changing the caller's key.
		for child in entity:
			if child._name == signal:
				return child
		raise SignalBindingError(f"{role}: no signal named {signal!r} in {entity._path}") from exc


def _control(handle: SimHandleBase, role: str) -> _Control:
	if isinstance(handle, LogicObject) or (isinstance(handle, LogicArrayObject) and len(handle) == 1):
		return handle
	raise SignalBindingError(f"{role}: {handle._path} must be a scalar or one-bit logic signal")


@dataclass(frozen=True)
class AxiStreamBus:
	"""Bound data, valid, ready and optional last handles; no signals are driven.

	Use :meth:`bind` for names/defaults, or pass handles directly to this
	constructor. Data may be a vector or record. Valid, ready and last must be
	one-bit logic handles. Ready is required in this initial protocol subset.
	Other AXI-Stream sidebands are not yet implemented. All roles and the clock
	must refer to non-overlapping signals; do not use payload fields or bits as
	handshake controls. Only identical-handle aliases are checked automatically.
	"""

	data: SimHandleBase
	"""Payload handle, kept separate from its value representation."""
	valid: _Control
	"""Source-owned transfer-valid signal."""
	ready: _Control
	"""Sink-owned acceptance signal."""
	last: _Control | None = None
	"""Source-owned frame boundary, or None for an unframed stream."""
	_entity: HierarchyObject | None = field(default=None, repr=False, compare=False)

	def __post_init__(self) -> None:
		for role in ("valid", "ready", "last"):
			handle = getattr(self, role)
			if handle is not None:
				_control(handle, role)
		handles = [self.data, self.valid, self.ready]
		if self.last is not None:
			handles.append(self.last)
		if len({handle._path for handle in handles}) != len(handles):
			raise SignalBindingError("data, valid, ready and last must refer to different signals")

	@classmethod
	def bind(
		cls,
		entity: HierarchyObject | None = None,
		*,
		prefix: str = "",
		t_prefix: bool = True,
		data: Signal | None = None,
		valid: Signal | None = None,
		ready: Signal | None = None,
		last: bool | Signal = False,
	) -> Self:
		"""Resolve signals, using defaults only where no override is supplied.

		``entity`` contains named signals; omit it when supplying all handles.
		``prefix="foo"`` generates ``foo_tdata`` etc.; an empty prefix generates
		``tdata`` etc. ``t_prefix=False`` removes only the generated ``t``.
		``data``, ``valid`` and ``ready`` override individual defaults with exact
		child names or handles. Explicit names are never modified.
		``last=False`` omits last even if it exists; True requires its generated
		name; a name or handle binds it explicitly. No optional signal is probed.
		"""
		stem = (f"{prefix}_" if prefix else "") + ("t" if t_prefix else "")

		def required(role: str, override: Signal | None) -> SimHandleBase:
			return _resolve(entity, stem + role if override is None else override, role)

		last_handle = None
		if last is True:
			last_handle = _control(_resolve(entity, stem + "last", "last"), "last")
		elif last is not False:
			last_handle = _control(_resolve(entity, last, "last"), "last")
		return cls(
			required("data", data),
			_control(required("valid", valid), "valid"),
			_control(required("ready", ready), "ready"),
			last_handle,
			entity,
		)

	def resolve_clock(self, clock: Signal) -> _Control:
		"""Resolve an exact clock name in the binding entity, or use its handle.

		``clock`` is independent of all bus naming defaults. A string requires
		the entity supplied to :meth:`bind`. Return a one-bit logic handle.
		"""
		handle = _control(_resolve(self._entity, clock, "clock"), "clock")
		if handle in (self.data, self.valid, self.ready, self.last):
			raise SignalBindingError("clock must be separate from stream signals")
		return handle

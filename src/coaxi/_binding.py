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


def _logic(handle: SimHandleBase, role: str) -> _Control:
	if isinstance(handle, LogicObject) or (isinstance(handle, LogicArrayObject) and len(handle) > 0):
		return handle
	raise SignalBindingError(f"{role}: {handle._path} must be a non-empty logic signal")


@dataclass(frozen=True)
class AxiStreamBus:
	"""Bound AXI4-Stream signals; construction does not drive any handles.

	Use :meth:`bind` for names/defaults, or pass handles directly. Data may be a
	vector or record; valid, ready and last are one-bit logic. Data and ready
	may be absent (None); absent ready means every valid edge accepts.
	All sidebands are explicitly selected. Without data, keep defines its own
	lane count and strb is forbidden. When data is present, keep/strb require
	byte-aligned logic-vector data with one qualifier bit per byte;
	record payloads have no implicit byte layout. User/id/dest accept any
	positive logic width. All roles and the clock must be non-overlapping;
	only identical-handle aliases are checked, not payload-field/bit overlap.
	"""

	data: SimHandleBase | None
	"""Payload handle, or None for data-less transfers."""
	valid: _Control
	"""Source-owned transfer-valid signal."""
	ready: _Control | None
	"""Sink-owned acceptance signal, or None for unconditional acceptance."""
	last: _Control | None = None
	"""Source-owned frame boundary, or None for an unframed stream."""
	_entity: HierarchyObject | None = field(default=None, repr=False, compare=False)
	keep: _Control | None = field(default=None, kw_only=True)
	"""Byte-presence mask, or None when absent."""
	strb: _Control | None = field(default=None, kw_only=True)
	"""Data/position-byte mask, or None when absent."""
	user: _Control | None = field(default=None, kw_only=True)
	"""Application-defined metadata, or None when absent."""
	id: _Control | None = field(default=None, kw_only=True)
	"""Stream identifier, or None when absent."""
	dest: _Control | None = field(default=None, kw_only=True)
	"""Routing destination, or None when absent."""

	def __post_init__(self) -> None:
		for role in ("valid", "ready", "last"):
			handle = getattr(self, role)
			if handle is not None:
				_control(handle, role)
		for role in ("keep", "strb", "user", "id", "dest"):
			handle = getattr(self, role)
			if handle is not None:
				_logic(handle, role)
		if self.data is None and self.strb is not None:
			raise SignalBindingError("strb requires a data signal")
		if self.data is not None and (self.keep is not None or self.strb is not None):
			if not isinstance(self.data, LogicArrayObject) or len(self.data) == 0 or len(self.data) % 8:
				raise SignalBindingError(
					"keep/strb require byte-aligned logic-vector data; records have no byte layout"
				)
			lanes = len(self.data) // 8
			for role in ("keep", "strb"):
				handle = getattr(self, role)
				if handle is not None:
					width = 1 if isinstance(handle, LogicObject) else len(handle)
					if width != lanes:
						raise SignalBindingError(f"{role}: expected one bit per data byte ({lanes} bits)")
		handles = self._handles()
		if len({handle._path for handle in handles}) != len(handles):
			raise SignalBindingError("stream roles must refer to different signals")

	def _handles(self) -> list[SimHandleBase]:
		return [
			handle
			for role in ("data", "valid", "ready", "last", "keep", "strb", "user", "id", "dest")
			if (handle := getattr(self, role)) is not None
		]

	@classmethod
	def bind(
		cls,
		entity: HierarchyObject | None = None,
		*,
		prefix: str = "",
		t_prefix: bool = True,
		data: bool | Signal | None = None,
		valid: Signal | None = None,
		ready: bool | Signal | None = None,
		last: bool | Signal = False,
		keep: bool | Signal = False,
		strb: bool | Signal = False,
		user: bool | Signal = False,
		id: bool | Signal = False,
		dest: bool | Signal = False,
	) -> Self:
		"""Resolve signals, using defaults only where no override is supplied.

		``entity`` contains named signals; omit it when supplying all handles.
		``prefix="foo"`` generates ``foo_tdata`` etc.; an empty prefix generates
		``tdata`` etc. ``t_prefix=False`` removes only the generated ``t``.
		``data``, ``valid`` and ``ready`` override individual defaults with exact
		child names or handles. None retains each generated default; data=False
		or ready=False explicitly omits that signal (True uses its default).
		Valid is mandatory. Explicit names are never modified.
		``last``, ``keep``, ``strb``, ``user``, ``id`` and ``dest`` independently
		select optional signals: False omits, True requires the generated name,
		and a name/handle binds it exactly. No optional signal is probed.
		Byte qualifiers require byte-aligned vector data and one bit per byte.
		Without data, keep may have any positive width; strb must be absent.
		"""
		stem = (f"{prefix}_" if prefix else "") + ("t" if t_prefix else "")

		def required(role: str, override: Signal | None) -> SimHandleBase:
			return _resolve(entity, stem + role if override is None else override, role)

		def optional(role: str, selection: bool | Signal) -> _Control | None:
			if selection is False:
				return None
			return _logic(_resolve(entity, stem + role if selection is True else selection, role), role)

		data_handle = None if data is False else required("data", None if data is True else data)
		ready_handle = (
			None if ready is False else _control(required("ready", None if ready is True else ready), "ready")
		)
		return cls(
			data_handle,
			_control(required("valid", valid), "valid"),
			ready_handle,
			optional("last", last),
			entity,
			keep=optional("keep", keep),
			strb=optional("strb", strb),
			user=optional("user", user),
			id=optional("id", id),
			dest=optional("dest", dest),
		)

	def resolve_clock(self, clock: Signal) -> _Control:
		"""Resolve an exact clock name in the binding entity, or use its handle.

		``clock`` is independent of all bus naming defaults. A string requires
		the entity supplied to :meth:`bind`. Return a one-bit logic handle.
		"""
		handle = _control(_resolve(self._entity, clock, "clock"), "clock")
		if handle in self._handles():
			raise SignalBindingError("clock must be separate from stream signals")
		return handle

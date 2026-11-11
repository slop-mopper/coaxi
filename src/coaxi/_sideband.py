# _sideband.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""AXI4-Stream sideband values, independent of payload conversion and timing."""

from collections.abc import Mapping
from dataclasses import dataclass

from cocotb.types import Logic, LogicArray
from cocotb.handle import LogicObject

from ._binding import AxiStreamBus

type SidebandValue = int | str | Logic | LogicArray
"""A width-matched logic value or unsigned integer, retaining deliberate meta-values."""


@dataclass(frozen=True)
class AxiStreamSidebands:
	"""Optional source metadata for one transfer, separate from its payload.

	None selects the source default on a bound signal: keep is all ones,
	strb follows effective keep, and user/id/dest are zero. Supplying a value
	for an absent signal raises ValueError. Integers must be unsigned and fit;
	strings/logic values must match the bound width. Deliberate meta-values
	are retained, without implicit numeric conversion. Do not mutate any
	contained LogicArray until the send or frame operation finishes.
	"""

	keep: SidebandValue | None = None
	"""One presence bit per data byte; None selects all bytes."""
	strb: SidebandValue | None = None
	"""One data/position bit per byte; None follows effective keep."""
	user: SidebandValue | None = None
	"""Application-defined value; None selects zero."""
	id: SidebandValue | None = None
	"""Stream identifier; None selects zero."""
	dest: SidebandValue | None = None
	"""Routing destination; None selects zero."""


_ROLES = ("keep", "strb", "user", "id", "dest")
type _Values = dict[str, Logic | LogicArray]


def _identity(id: Logic | LogicArray | None, dest: Logic | LogicArray | None) -> tuple[int, int]:
	result = []
	for role, value in (("id", id), ("dest", dest)):
		if value is None:
			result.append(0)
		else:
			bits = str(value)
			if any(bit not in "01" for bit in bits):
				raise ValueError(f"packet assembly requires literal 0/1 {role}, got {bits}")
			result.append(int(bits, 2))
	return result[0], result[1]


class _SidebandAccess:
	def __init__(self, bus: AxiStreamBus) -> None:
		self._handles = {role: handle for role in _ROLES if (handle := getattr(bus, role)) is not None}
		self._lanes = 0
		if bus.data is not None and (bus.keep is not None or bus.strb is not None):
			self._lanes = len(bus.data) // 8
		elif bus.keep is not None:
			self._lanes = 1 if isinstance(bus.keep, LogicObject) else len(bus.keep)

	def _validate(self, values: Mapping[str, Logic | LogicArray]) -> None:
		if self._lanes:
			keep = str(values["keep"]) if "keep" in values else "1" * self._lanes
			strb = str(values["strb"]) if "strb" in values else keep
			if any(k == "0" and s == "1" for k, s in zip(keep, strb, strict=True)):
				raise ValueError("reserved byte qualifier combination: keep=0, strb=1")

	def prepare(self, metadata: AxiStreamSidebands | None) -> _Values:
		if metadata is None:
			metadata = AxiStreamSidebands()
		if not isinstance(metadata, AxiStreamSidebands):
			raise TypeError("sidebands must be AxiStreamSidebands or None")
		values: _Values = {}
		for role in _ROLES:
			handle = self._handles.get(role)
			value = getattr(metadata, role)
			if handle is None:
				if value is not None:
					raise ValueError(f"{role} requires a bound {role} signal")
				continue
			if value is None:
				if role == "keep":
					value = "1" * self._lanes
				elif role == "strb":
					value = str(values["keep"]) if "keep" in values else "1" * self._lanes
				else:
					value = 0
			if isinstance(value, int) and value < 0:
				raise ValueError(f"{role}: integer sidebands must be unsigned")
			if isinstance(value, (Logic, LogicArray)):
				value = str(value)
			values[role] = Logic(value) if isinstance(handle, LogicObject) else LogicArray(value, handle.range)
		self._validate(values)
		return values

	def drive(self, values: _Values) -> None:
		for role, value in values.items():
			self._handles[role].set(value)

	def read(self) -> _Values:
		values = {role: handle.value for role, handle in self._handles.items()}
		self._validate(values)
		return values

	def clear(self) -> None:
		for handle in self._handles.values():
			handle.set(0)

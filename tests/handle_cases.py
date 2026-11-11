# handle_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Exercise scalar payloads and one-bit vectors with non-zero HDL indices."""

from typing import Any
from itertools import pairwise
from collections.abc import Coroutine

import cocotb
import pytest
from cocotb.types import Logic, LogicArray
from cocotb.handle import HierarchyObject, LogicArrayObject, LogicObject
from cocotb.simtime import get_sim_time
from cocotb.triggers import Timer, ReadOnly, RisingEdge, FallingEdge

from coaxi import (
	AxiStreamBus,
	AxiStreamSink,
	AxiStreamSource,
	EndpointStateError,
	PayloadValue,
	ProtocolValueError,
)


async def _capture[T](operation: Coroutine[Any, Any, T]) -> T | Exception:
	try:
		return await operation
	except Exception as exc:
		return exc


async def _clock(clock: LogicArrayObject) -> None:
	# Cocotb's Clock API is typed for scalar handles; drive this vector explicitly.
	while True:
		clock.value = 0
		await Timer(5, unit="ns")
		clock.value = 1
		await Timer(5, unit="ns")


def _setup(dut: HierarchyObject, *, framed: bool = True) -> AxiStreamBus:
	clock = dut.single_clock
	assert isinstance(clock, LogicArrayObject)
	cocotb.start_soon(_clock(clock))
	bus = AxiStreamBus.bind(
		dut,
		data="scalar_value",
		valid="single_valid",
		ready="single_ready",
		last="single_last" if framed else False,
	)
	assert isinstance(bus.data, LogicObject)
	assert isinstance(bus.valid, LogicArrayObject)
	assert isinstance(bus.ready, LogicArrayObject)
	if framed:
		assert isinstance(bus.last, LogicArrayObject)
	assert bus.resolve_clock("single_clock") is clock
	return bus


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def scalar_full_rate(dut: HierarchyObject) -> None:
	"""Keep scalar snapshots/meta-values and full rate across vector-controlled frames."""
	bus = _setup(dut)
	source = AxiStreamSource(bus, clock="single_clock")
	sink = AxiStreamSink(bus, clock=dut.single_clock)
	await source.reset()
	await sink.reset()
	samples: list[PayloadValue] = [0, 1, "L", Logic("H"), LogicArray("U"), "X", Logic("Z"), "W", "-"]
	expected = [str(value) for value in samples] * 8
	observed: list[tuple[int, str, bool]] = []

	async def monitor() -> None:
		while len(observed) < len(expected):
			await RisingEdge(dut.single_clock)
			if str(bus.valid.value) == str(bus.ready.value) == "1":
				assert bus.last is not None
				observed.append((int(get_sim_time(unit="ns")), str(bus.data.value), str(bus.last.value) == "1"))

	async def send_frames() -> None:
		for _ in range(8):
			await source.send_frame(samples)

	monitoring = cocotb.start_soon(monitor())
	sending = cocotb.start_soon(send_frames())
	snapshots: list[Logic] = []
	for _ in range(8):
		frame = await sink.recv_frame()
		assert [transfer.last for transfer in frame] == [False] * 8 + [True]
		for transfer in frame:
			assert isinstance(transfer.data, Logic)
			snapshots.append(transfer.data)
	await sending
	await monitoring
	assert [bits for _, bits, _ in observed] == expected
	assert [last for _, _, last in observed] == ([False] * 8 + [True]) * 8
	assert all(right[0] - left[0] == 10 for left, right in pairwise(observed))
	await ReadOnly()
	assert str(bus.valid.value) == str(bus.ready.value) == str(dut.single_last.value) == "0"
	assert str(bus.data.value) == "-"
	await source.reset()
	await sink.reset()
	await ReadOnly()
	assert str(bus.data.value) == "0"
	assert [str(value) for value in snapshots] == expected


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def scalar_validation(dut: HierarchyObject) -> None:
	"""Reject invalid scalar leaves without changing data; reset clears deliberate X."""
	bus = _setup(dut, framed=False)
	source = AxiStreamSource(bus, clock="single_clock")
	await source.reset()
	bus.ready.value = 1
	bad_values: list[PayloadValue] = [-1, 2, "10", "?", LogicArray("11"), {}]
	for value in bad_values:
		await source.send("X")
		await ReadOnly()
		assert str(bus.data.value) == "X"
		error = await _capture(source.send(value))
		assert type(error) is (TypeError if isinstance(value, dict) else ValueError)
		await ReadOnly()
		assert str(bus.data.value) == "X"
		assert str(bus.valid.value) == "0"
		with pytest.raises(EndpointStateError, match="reset"):
			await source.send(1)
		await source.reset()
		await ReadOnly()
		assert str(bus.data.value) == str(bus.valid.value) == "0"


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def scalar_backpressure(dut: HierarchyObject) -> None:
	"""Hold a meta-valued scalar and last stable while vector ready is low."""
	bus = _setup(dut)
	source = AxiStreamSource(bus, clock="single_clock")
	await source.reset()
	bus.ready.value = 0
	sending = cocotb.start_soon(source.send(Logic("U"), last=True))
	# The first call needs its own falling edge, even immediately after reset.
	await FallingEdge(dut.single_clock)
	await ReadOnly()
	assert str(bus.valid.value) == "1"
	for _ in range(3):
		await RisingEdge(dut.single_clock)
		assert str(bus.valid.value) == str(dut.single_last.value) == "1"
		assert str(bus.ready.value) == "0"
		assert str(bus.data.value) == "U"
		assert not sending.done()
	await FallingEdge(dut.single_clock)
	bus.ready.value = 1
	await RisingEdge(dut.single_clock)
	assert str(bus.valid.value) == str(bus.ready.value) == "1"
	assert str(bus.data.value) == "U"
	await sending
	await ReadOnly()
	assert str(bus.valid.value) == str(dut.single_last.value) == "0"
	await source.reset()
	await ReadOnly()
	assert str(bus.data.value) == "0"


@cocotb.test(timeout_time=10000, timeout_unit="ns")
@cocotb.parametrize(role=["ready", "valid", "last"], bits=["U", "X", "Z", "W", "L", "H", "-"])
async def vector_control_errors(dut: HierarchyObject, role: str, bits: str) -> None:
	"""Reject weak/unresolved one-bit vector controls and clear only owned outputs."""
	bus = _setup(dut)
	if role == "ready":
		source = AxiStreamSource(bus, clock="single_clock")
		await source.reset()
		bus.ready.value = bits
		error = await _capture(source.send(1, last=True))
		assert type(error) is ProtocolValueError
		assert str(error).startswith("ready ")
		with pytest.raises(EndpointStateError, match="reset"):
			await source.send(1, last=True)
		await source.reset()
		await ReadOnly()
		assert str(bus.data.value) == str(bus.valid.value) == str(dut.single_last.value) == "0"
		assert str(bus.ready.value) == bits
	else:
		sink = AxiStreamSink(bus, clock=dut.single_clock)
		await sink.reset()
		bus.data.value = "X"  # Deliberate payload meta-value, distinct from the control fault.
		bus.valid.value = bits if role == "valid" else 1
		dut.single_last.value = bits if role == "last" else 1
		error = await _capture(sink.recv())
		assert type(error) is ProtocolValueError
		assert str(error).startswith(f"{role} ")
		with pytest.raises(EndpointStateError, match="reset"):
			await sink.recv()
		await sink.reset()
		await ReadOnly()
		assert str(bus.ready.value) == "0"
		assert str(bus.data.value) == "X"
		assert str(bus.valid.value) == (bits if role == "valid" else "1")
		assert str(dut.single_last.value) == (bits if role == "last" else "1")

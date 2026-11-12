# sideband_cases.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""AXI4 sideband binding, snapshots, byte qualifiers and interleaved packets."""

from asyncio import CancelledError

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.types import Logic
from cocotb.handle import HierarchyObject
from cocotb.simtime import get_sim_time
from cocotb.triggers import ReadOnly, RisingEdge, FallingEdge

from coaxi import (
	AxiStreamBus,
	AxiStreamSidebands,
	AxiStreamSink,
	AxiStreamSource,
	AxiStreamTransfer,
	EndpointStateError,
	PayloadValue,
	ProtocolValueError,
	SignalBindingError,
)


async def _setup(dut: HierarchyObject) -> None:
	cocotb.start_soon(Clock(dut.beat_clock, 10, unit="ns").start(start_high=False))
	await FallingEdge(dut.beat_clock)
	dut.wipe_registers.value = 1
	dut.allow_input.value = 0
	dut.s_tvalid.value = 0
	dut.m_ready.value = 0
	dut.sb_tvalid.value = 0
	dut.sb_tready.value = 0
	dut.plain_valid.value = 0
	dut.plain_ready.value = 0
	await FallingEdge(dut.beat_clock)
	dut.wipe_registers.value = 0


def _bus(dut: HierarchyObject, prefix: str = "sb") -> AxiStreamBus:
	return AxiStreamBus.bind(
		dut,
		prefix=prefix,
		t_prefix=prefix != "m",
		last=True,
		keep=True,
		strb=True,
		user=True,
		id=True,
		dest=True,
	)


def _snapshot(bus: AxiStreamBus) -> tuple[str, ...]:
	return tuple(str(getattr(bus, role).value) for role in ("data", "last", "keep", "strb", "user", "id", "dest"))


def _transfer(value: AxiStreamTransfer[PayloadValue]) -> tuple[str, ...]:
	return (
		str(value.data),
		str(int(bool(value.last))),
		str(value.keep),
		str(value.strb),
		str(value.user),
		str(value.id),
		str(value.dest),
	)


@cocotb.test(timeout_time=2000, timeout_unit="ns")
async def binding_and_simple_defaults(dut: HierarchyObject) -> None:
	"""Keep bare-bones calls unchanged; bind optional roles independently and exactly."""
	await _setup(dut)
	bare = AxiStreamBus.bind(dut, prefix="sb")
	assert all(getattr(bare, role) is None for role in ("last", "keep", "strb", "user", "id", "dest"))
	mixed = AxiStreamBus.bind(
		dut,
		prefix="sb",
		keep=dut.sb_tkeep,
		strb=True,
		user="sample_available",
		id=dut.sb_tid,
		dest=True,
	)
	assert mixed.keep is dut.sb_tkeep and mixed.strb is dut.sb_tstrb
	assert mixed.user is dut.sample_available and mixed.dest is dut.sb_tdest
	with pytest.raises(SignalBindingError):
		mixed.resolve_clock(dut.sample_available)
	with pytest.raises(SignalBindingError):
		AxiStreamBus.bind(dut, prefix="sb", id="sb_tdest", dest=True)
	with pytest.raises(SignalBindingError):
		AxiStreamBus.bind(dut, prefix="missing", data=dut.sb_tdata, valid=dut.sb_tvalid, ready=dut.sb_tready, user=True)
	with pytest.raises(SignalBindingError):
		AxiStreamBus.bind(dut, prefix="sb", user=dut.iq_word_in)
	for data in (dut.iq_word_in, dut.scalar_value, dut.short_data):
		with pytest.raises(SignalBindingError, match="byte-aligned"):
			AxiStreamBus.bind(dut, prefix="sb", data=data, keep=True)
	with pytest.raises(SignalBindingError, match="one bit per data byte"):
		AxiStreamBus.bind(dut, prefix="sb", keep=dut.byte_keep)
	with pytest.raises(SignalBindingError):
		AxiStreamBus.bind(dut, prefix="sb", keep=True, strb=dut.sb_tkeep)
	direct = AxiStreamBus(
		dut.sb_tdata,
		dut.sb_tvalid,
		dut.sb_tready,
		dut.sb_tlast,
		keep=dut.sb_tkeep,
		strb=dut.sb_tstrb,
		user=dut.sb_tuser,
		id=dut.sb_tid,
		dest=dut.sb_tdest,
	)
	assert direct.keep is dut.sb_tkeep
	source = AxiStreamSource(bare, dut.beat_clock)
	sink = AxiStreamSink(bare, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	sending = cocotb.start_soon(source.send(42))
	result = await sink.recv()
	await sending
	assert int(str(result.data), 2) == 42
	assert all(getattr(result, role) is None for role in ("last", "keep", "strb", "user", "id", "dest"))

	# Selecting sidebands does not make metadata mandatory on individual/frame calls.
	bus = _bus(dut)
	source = AxiStreamSource(bus, dut.beat_clock)
	sink = AxiStreamSink(bus, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	sending = cocotb.start_soon(source.send_frame([11, 22]))
	frame = await sink.recv_frame()
	await sending
	assert [int(str(value.data), 2) for value in frame] == [11, 22]
	for value in frame:
		assert str(value.keep) == str(value.strb) == "11"
		assert str(value.user) == "00000" and int(str(value.id), 2) == int(str(value.dest), 2) == 0


@cocotb.test(timeout_time=10000, timeout_unit="ns")
async def registered_sideband_full_rate(dut: HierarchyObject) -> None:
	"""Snapshot all fields at acceptance before HDL updates; no bubbles in 128 beats."""
	await _setup(dut)
	input_bus, output_bus = _bus(dut, "s"), _bus(dut, "m")
	source = AxiStreamSource(input_bus, dut.beat_clock)
	sink = AxiStreamSink(output_bus, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	dut.allow_input.value = 1
	expected: list[tuple[str, ...]] = []
	for index in range(128):
		keep = ("11", "10", "01", "00", "XU", "LH")[index % 6]
		strb = keep if index % 2 else "00"
		user = "XU01Z" if index % 9 == 0 else f"{index % 32:05b}"
		identifier = "X" + f"{index:010b}" if index % 7 == 0 else f"{index * 9:011b}"
		expected.append(
			(f"{index * 37:016b}", str(int(index % 11 == 10)), keep, strb, user, identifier, f"{index:09b}")
		)

	async def send_all() -> None:
		for data, last, keep, strb, user, identifier, dest in expected:
			await source.send(
				data,
				last=last == "1",
				sidebands=AxiStreamSidebands(keep=keep, strb=strb, user=user, id=identifier, dest=dest),
			)

	results = []

	async def recv_all() -> None:
		for _ in expected:
			results.append(await sink.recv())

	sending = cocotb.start_soon(send_all())
	receiving = cocotb.start_soon(recv_all())
	inputs, outputs = [], []
	for cycle in range(len(expected) + 8):
		await RisingEdge(dut.beat_clock)
		if str(input_bus.valid.value) == str(input_bus.ready.value) == "1":
			inputs.append((cycle, _snapshot(input_bus)))
		if str(output_bus.valid.value) == str(output_bus.ready.value) == "1":
			outputs.append((cycle, _snapshot(output_bus)))
	assert sending.done() and receiving.done()
	await sending
	await receiving
	assert [value for _, value in inputs] == [value for _, value in outputs] == expected
	assert [_transfer(value) for value in results] == expected
	assert [cycle for cycle, _ in inputs] == list(range(inputs[0][0], inputs[0][0] + len(expected)))
	assert [cycle for cycle, _ in outputs] == [cycle + 1 for cycle, _ in inputs]
	# Leave actual meta-values on the source wires and in the registered output.
	await source.send(
		"XU00000000000001",
		last=True,
		sidebands=AxiStreamSidebands(keep="XU", user="UX01Z", id="X0000000000", dest="H00000000"),
	)
	assert _snapshot(input_bus)[2] == "XU"
	# Sink reset owns only ready, not its incoming data or any sidebands.
	before = _snapshot(output_bus)
	assert before[2] == "XU"
	await sink.initialise()
	assert _snapshot(output_bus) == before
	await source.initialise()
	await ReadOnly()
	assert all(set(value) <= {"0"} for value in _snapshot(input_bus))
	assert _snapshot(output_bus) == before
	assert [_transfer(value) for value in results] == expected


@cocotb.test(timeout_time=4000, timeout_unit="ns")
async def scalar_qualifiers_and_omissions(dut: HierarchyObject) -> None:
	"""Support one-bit scalar/vector masks, defaults and None for physically absent roles."""
	await _setup(dut)
	for keep, strb in ((True, True), (True, False), (False, True)):
		bus = AxiStreamBus.bind(
			dut,
			prefix="plain",
			t_prefix=False,
			keep=dut.byte_keep if keep else False,
			strb=dut.byte_strb if strb else False,
		)
		source, sink = AxiStreamSource(bus, dut.beat_clock), AxiStreamSink(bus, dut.beat_clock)
		await source.initialise()
		await sink.initialise()
		metadata = AxiStreamSidebands(keep=0 if keep else None)
		sending = cocotb.start_soon(source.send(0xAB, sidebands=metadata))
		result = await sink.recv()
		await sending
		if keep:
			assert isinstance(result.keep, Logic) and str(result.keep) == "0"
		else:
			assert result.keep is None
		if strb:
			assert str(result.strb) == ("0" if keep else "1")
		else:
			assert result.strb is None
		assert result.user is result.id is result.dest is None


@cocotb.test(timeout_time=4000, timeout_unit="ns")
async def backpressure_and_preflight(dut: HierarchyObject) -> None:
	"""Hold all metadata stable under stalls; reject bad metadata without partial writes."""
	await _setup(dut)
	bus = _bus(dut)
	source = AxiStreamSource(bus, dut.beat_clock)
	await source.initialise()
	before = _snapshot(bus)
	bad = [
		AxiStreamSidebands(keep=1, strb=3),
		AxiStreamSidebands(keep=4),
		AxiStreamSidebands(user=-1),
		AxiStreamSidebands(user="X"),
		AxiStreamSidebands(id=2048),
	]
	for metadata in bad:
		with pytest.raises((ValueError, OverflowError)):
			await source.send(99, last=True, sidebands=metadata)
		assert _snapshot(bus) == before and str(bus.valid.value) == "0"
	with pytest.raises(ValueError, match="one entry"):
		await source.send_frame([1, 2], sidebands=[AxiStreamSidebands()])
	sending = cocotb.start_soon(
		source.send(
			0xCAFE,
			last=True,
			sidebands=AxiStreamSidebands(keep="XU", user="01XZU", id=345, dest=256),
		)
	)
	await RisingEdge(dut.beat_clock)
	await RisingEdge(dut.beat_clock)
	stalled = _snapshot(bus)
	assert stalled[2:4] == ("XU", "XU")
	for _ in range(4):
		await RisingEdge(dut.beat_clock)
		assert str(bus.valid.value) == "1" and _snapshot(bus) == stalled and not sending.done()
	await FallingEdge(dut.beat_clock)
	dut.sb_tready.value = 1
	await sending
	assert _snapshot(bus)[2:] == stalled[2:]

	# Source defaults replace the previous transfer; omitted strb follows this beat's keep.
	sending = cocotb.start_soon(source.send(7, last=False, sidebands=AxiStreamSidebands(keep=1)))
	await RisingEdge(dut.beat_clock)
	assert _snapshot(bus)[2:] == ("01", "01", "00000", "00000000000", "000000000")
	await sending
	bare = AxiStreamSource(AxiStreamBus.bind(dut, prefix="sb"), dut.beat_clock)
	await bare.initialise()
	with pytest.raises(ValueError, match="requires a bound"):
		await bare.send(1, sidebands=AxiStreamSidebands(user=0))
	# No reset is needed after this preflight failure.
	await bare.send(8)


@cocotb.test(timeout_time=6000, timeout_unit="ns")
async def interleaved_packets(dut: HierarchyObject) -> None:
	"""Demultiplex id AND dest; retain partial packets and return completion order at full rate."""
	await _setup(dut)
	bus = _bus(dut)
	source, sink = AxiStreamSource(bus, dut.beat_clock), AxiStreamSink(bus, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	# Same id/different dest and same dest/different id must not be merged.
	beats = [
		(11, 1, 0, False),
		(21, 1, 1, False),
		(31, 2, 0, False),
		(22, 1, 1, True),
		(12, 1, 0, False),
		(32, 2, 0, True),
		(13, 1, 0, True),
	]

	async def send_all() -> None:
		for data, identifier, dest, last in beats:
			await source.send(
				data,
				last=last,
				sidebands=AxiStreamSidebands(
					keep=0 if last else 3,
					user=data % 32,
					id=identifier,
					dest=dest,
				),
			)

	packets: list[list[AxiStreamTransfer[PayloadValue]]] = []

	async def recv_all() -> None:
		for _ in range(3):
			packets.append(await sink.recv_frame(max_transfers=3))

	sending = cocotb.start_soon(send_all())
	receiving = cocotb.start_soon(recv_all())
	cycles = []
	for cycle in range(len(beats) + 5):
		await RisingEdge(dut.beat_clock)
		if str(bus.valid.value) == str(bus.ready.value) == "1":
			cycles.append(cycle)
	await sending
	await receiving
	assert cycles == list(range(cycles[0], cycles[0] + len(beats)))
	assert [[int(str(value.data), 2) for value in packet] for packet in packets] == [[21, 22], [31, 32], [11, 12, 13]]
	for packet in packets:
		assert [value.last for value in packet] == [False] * (len(packet) - 1) + [True]
		assert len({(str(value.id), str(value.dest)) for value in packet}) == 1
		# Null final beats are retained and still terminate packets.
		assert str(packet[-1].keep) == str(packet[-1].strb) == "00"


@cocotb.test(timeout_time=6000, timeout_unit="ns")
async def frame_metadata_and_identity_errors(dut: HierarchyObject) -> None:
	"""Per-transfer frame metadata retains rate; a frame cannot change packet identity."""
	await _setup(dut)
	bus = _bus(dut)
	source, sink = AxiStreamSource(bus, dut.beat_clock), AxiStreamSink(bus, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	metadata = [
		AxiStreamSidebands(keep=3, strb=2, user="XU01Z", id=1024, dest=256),
		AxiStreamSidebands(keep=1, user=23, id=1024, dest=256),
		AxiStreamSidebands(keep=0, id=1024, dest=256),
	]
	sending = cocotb.start_soon(source.send_frame([10, 20, 30], sidebands=metadata))
	packet = await sink.recv_frame(max_transfers=3)
	await sending
	assert [str(value.keep) for value in packet] == ["11", "01", "00"]
	assert [str(value.strb) for value in packet] == ["10", "01", "00"]
	assert [str(value.user) for value in packet] == ["XU01Z", "10111", "00000"]
	assert {str(value.id) for value in packet} == {"10000000000"}
	assert {str(value.dest) for value in packet} == {"100000000"}
	dut.sb_tready.value = 1
	with pytest.raises(ValueError, match="constant"):
		await source.send_frame([1, 2], sidebands=[AxiStreamSidebands(id=1), AxiStreamSidebands(id=2)])
	with pytest.raises(EndpointStateError):
		await source.send(3, last=True)
	await source.initialise()
	with pytest.raises(ValueError, match="literal"):
		await source.send_frame([1], sidebands=[AxiStreamSidebands(id="X0000000000")])
	await source.initialise()


@cocotb.test(timeout_time=6000, timeout_unit="ns")
async def receive_faults_and_retained_limits(dut: HierarchyObject) -> None:
	"""Reject literal reserved pairs and unresolved assembly keys; retain raw individual snapshots."""
	await _setup(dut)
	bus = _bus(dut)
	source, sink = AxiStreamSource(bus, dut.beat_clock), AxiStreamSink(bus, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	meta = AxiStreamSidebands(id="X0000000000", dest="H00000000")
	sending = cocotb.start_soon(source.send(1, last=True, sidebands=meta))
	raw = await sink.recv()
	await sending
	assert str(raw.id) == "X0000000000" and str(raw.dest) == "H00000000"
	sending = cocotb.start_soon(source.send(2, last=True, sidebands=meta))
	with pytest.raises(ProtocolValueError, match="literal"):
		await sink.recv_frame()
	await sending
	await sink.initialise()

	# B completes while A has a retained prefix. Lowering the next limit must
	# reject that prefix without accepting another beat.
	async def send_prefixes() -> None:
		for data, identifier, last in ((1, 1, False), (2, 1, False), (3, 2, True)):
			await source.send(data, last=last, sidebands=AxiStreamSidebands(id=identifier))

	sending = cocotb.start_soon(send_prefixes())
	packet = await sink.recv_frame()
	await sending
	assert [int(str(value.data), 2) for value in packet] == [3]
	at_limit = get_sim_time(unit="step")
	with pytest.raises(ValueError, match="retained"):
		await sink.recv_frame(max_transfers=2)
	assert get_sim_time(unit="step") == at_limit
	await sink.initialise()
	sending = cocotb.start_soon(source.send(4, last=True, sidebands=AxiStreamSidebands(id=1)))
	packet = await sink.recv_frame()
	await sending
	assert [int(str(value.data), 2) for value in packet] == [4]

	# An independent faulty source can drive a reserved pair which the library
	# source rejects before transmission. The receive fault is after acceptance.
	await FallingEdge(dut.beat_clock)
	dut.sb_tkeep.value = "01"
	dut.sb_tstrb.value = "11"
	dut.sb_tvalid.value = 1
	with pytest.raises(ProtocolValueError, match="reserved"):
		await sink.recv()
	with pytest.raises(EndpointStateError):
		await sink.recv()
	await source.initialise()
	await sink.initialise()


@cocotb.test(timeout_time=6000, timeout_unit="ns")
async def mixed_receive_api_boundaries(dut: HierarchyObject) -> None:
	"""Never splice retained prefixes across raw-consumed beats or packet boundaries."""
	await _setup(dut)
	bus = _bus(dut)
	source, sink = AxiStreamSource(bus, dut.beat_clock), AxiStreamSink(bus, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	for raw_last, unresolved in ((True, False), (False, False), (True, True)):

		async def send_prefixes() -> None:
			for value, identifier, last in ((11, 1, False), (31, 3, False), (21, 2, True)):
				await source.send(value, last=last, sidebands=AxiStreamSidebands(id=identifier))

		sending = cocotb.start_soon(send_prefixes())
		packet = await sink.recv_frame()
		await sending
		assert [int(str(value.data), 2) for value in packet] == [21]
		metadata = AxiStreamSidebands(id="X0000000000" if unresolved else 1)
		sending = cocotb.start_soon(source.send(12, last=raw_last, sidebands=metadata))
		raw = await sink.recv()
		await sending
		assert int(str(raw.data), 2) == 12
		sending = cocotb.start_soon(source.send(13, last=True, sidebands=AxiStreamSidebands(id=1)))
		packet = await sink.recv_frame(max_transfers=2)
		await sending
		assert [int(str(value.data), 2) for value in packet] == [13]
		sending = cocotb.start_soon(source.send(32, last=True, sidebands=AxiStreamSidebands(id=3)))
		packet = await sink.recv_frame(max_transfers=2)
		await sending
		assert [int(str(value.data), 2) for value in packet] == ([32] if unresolved else [31, 32])


@cocotb.test(timeout_time=3000, timeout_unit="ns")
async def record_sidebands_and_exact_names(dut: HierarchyObject) -> None:
	"""Records carry user/id/dest naturally, without defining a byte layout."""
	await _setup(dut)
	bus = AxiStreamBus.bind(
		dut,
		data="iq_word_in",
		valid="sample_available",
		ready="consumer_accepts",
		last="end_of_packet",
		user="\\lane.payload[0]\\",
		id=dut.sb_tid,
		dest="byte_keep",
	)
	assert bus.user is dut["\\lane.payload[0]\\"]
	source, sink = AxiStreamSource(bus, dut.beat_clock), AxiStreamSink(bus, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	metadata = [AxiStreamSidebands(user="XU010101", id=1024), AxiStreamSidebands(user=127, id=1024)]
	sending = cocotb.start_soon(source.send_frame([{"i": 1, "q": 2}, {"i": 3, "q": 4}], sidebands=metadata))
	packet = await sink.recv_frame()
	await sending
	assert [value.data for value in packet] == [{"i": 1, "q": 2}, {"i": 3, "q": 4}]
	assert [str(value.user) for value in packet] == ["XU010101", "01111111"]
	assert all(str(value.id) == "10000000000" and str(value.dest) == "0" for value in packet)
	assert all(value.keep is value.strb is None for value in packet)
	await source.initialise()
	assert [str(value.user) for value in packet] == ["XU010101", "01111111"]


@cocotb.test(timeout_time=6000, timeout_unit="ns")
async def partial_packet_cancellation_and_wire_order(dut: HierarchyObject) -> None:
	"""Cancellation/reset discards retained assembly; individual recv preserves wire order."""
	await _setup(dut)
	bus = _bus(dut)
	source, sink = AxiStreamSource(bus, dut.beat_clock), AxiStreamSink(bus, dut.beat_clock)
	await source.initialise()
	await sink.initialise()
	receiving = cocotb.start_soon(sink.recv_frame())
	await source.send(11, last=False, sidebands=AxiStreamSidebands(id=1))
	await source.send(21, last=False, sidebands=AxiStreamSidebands(id=2))
	await RisingEdge(dut.beat_clock)
	receiving.cancel()
	with pytest.raises(CancelledError):
		await receiving
	await sink.initialise()
	for value, identifier in ((22, 2), (12, 1), (31, 3)):
		sending = cocotb.start_soon(source.send(value, last=True, sidebands=AxiStreamSidebands(id=identifier)))
		packet = await sink.recv_frame()
		await sending
		assert [int(str(beat.data), 2) for beat in packet] == [value]
	# Mixed identities with non-final beats remain wire-ordered for individual recv.
	for value, identifier in ((1, 2), (2, 1), (3, 2)):
		sending = cocotb.start_soon(source.send(value, last=False, sidebands=AxiStreamSidebands(id=identifier)))
		transfer = await sink.recv()
		await sending
		assert int(str(transfer.data), 2) == value and int(str(transfer.id), 2) == identifier

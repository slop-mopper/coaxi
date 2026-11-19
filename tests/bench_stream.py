# bench_stream.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.2-sol

"""Measure AXI-Stream loopback throughput with an optional cocotbext-axi comparison."""

from __future__ import annotations

import os
import sys
import json
import logging
import argparse
from time import perf_counter
from pathlib import Path
from random import Random
from struct import Struct
from cProfile import Profile
from tempfile import TemporaryDirectory
from importlib import import_module
from statistics import median
from xml.etree import ElementTree

import cocotb
from cocotb.clock import Clock
from cocotb.handle import HierarchyObject, LogicArrayObject
from cocotb.triggers import Timer, ReadOnly, RisingEdge, FallingEdge, with_timeout
from cocotb_tools.runner import get_runner

from coaxi import AxiStreamBus, AxiStreamSink, AxiStreamSource, AxiStreamTransfer, HandlePayload, PayloadValue


_FRAME_LOOPS = ("falling-loop", "rising-loop")


async def _send_frame(
	bus: AxiStreamBus,
	payload: HandlePayload,
	data: tuple[int, ...],
	rising: RisingEdge,
	falling: FallingEdge,
	*,
	rising_interior: bool,
) -> None:
	"""Enter on a falling edge and make the same deposits in either loop."""
	valid, ready, last = bus.valid, bus.ready, bus.last
	assert ready is not None and last is not None
	for index, word in enumerate(data, start=1):
		final = index == len(data)
		payload.drive(word)
		last.set(int(final))
		valid.set(1)
		while True:
			await rising
			if str(ready.get()) == "1":
				break
		if final or not rising_interior:
			await falling
		valid.set(0)
		last.set(0)


async def _recv_frame(
	bus: AxiStreamBus,
	payload: HandlePayload,
	rising: RisingEdge,
	falling: FallingEdge,
	*,
	rising_interior: bool,
) -> list[AxiStreamTransfer[PayloadValue | None]]:
	"""Enter and return on falling edges, capturing the same snapshots in either loop."""
	valid, ready, last = bus.valid, bus.ready, bus.last
	assert ready is not None and last is not None
	packet: list[AxiStreamTransfer[PayloadValue | None]] = []
	while True:
		ready.set(1)
		while True:
			await rising
			if str(valid.get()) == "1":
				break
			await falling
		final = str(last.get()) == "1"
		packet.append(AxiStreamTransfer(payload.read(), final))
		if final or not rising_interior:
			await falling
		ready.set(0)
		if final:
			return packet


def _codec(width: int) -> Struct | None:
	code = {8: "B", 16: "H", 32: "I", 64: "Q"}.get(width)
	return None if code is None else Struct("<" + code)


@cocotb.test()
async def stream_throughput(dut: HierarchyObject) -> None:
	"""Verify all payloads, frame lengths, hardware counts, and handshake spacing."""
	implementation = os.environ["BENCH_IMPLEMENTATION"]
	frame_loop = implementation in _FRAME_LOOPS
	rising_interior = implementation == "rising-loop"
	using_coaxi = not frame_loop and implementation not in ("legacy", "legacy-word")
	beats = int(os.environ["BENCH_BEATS"])
	frame_size = int(os.environ["BENCH_FRAME_SIZE"])
	reset_pin = os.environ["BENCH_RESET"] == "1"
	frame_count = beats // frame_size
	width = int(os.environ["BENCH_WIDTH"])
	stall_period = int(os.environ["BENCH_STALL_PERIOD"])
	assert len(dut.s_tdata) == len(dut.m_tdata) == width
	profile_path = os.environ.get("BENCH_PROFILE")
	profile = Profile() if profile_path else None
	logging.getLogger("coaxi.stream").setLevel(logging.WARNING)
	logging.getLogger(f"cocotb.{dut._name}").setLevel(logging.WARNING)

	clock = dut.clock
	cocotb.start_soon(Clock(clock, 10, unit="ns", impl="gpi").start(start_high=False))
	reset = dut.reset if reset_pin else None
	dut.reset.value = int(reset_pin)
	if frame_loop:
		assert not reset_pin
		source_bus = AxiStreamBus.bind(dut, prefix="s", last=True)
		sink_bus = AxiStreamBus.bind(dut, prefix="m", last=True)
		assert source_bus.data is not None and sink_bus.data is not None
		source_payload, sink_payload = HandlePayload(source_bus.data), HandlePayload(sink_bus.data)
		rising, falling = RisingEdge(clock), FallingEdge(clock)
		# Match the two sequential endpoint initialisations before coaxi timing.
		await falling
		await falling
	elif using_coaxi:

		class DirectIntegerDrive(HandlePayload):
			"""Benchmark-only adapter for the generated, in-range integer input."""

			def __init__(self, handle: LogicArrayObject) -> None:
				super().__init__(handle)
				self._vector = handle

			def drive(self, value: PayloadValue) -> None:
				assert isinstance(value, int)
				self._vector.set(value)

		if implementation == "baseline":
			baseline = Path(os.environ["BENCH_BASELINE_PATH"])
			assert Path(import_module("coaxi").__file__).resolve().parent == baseline / "coaxi"
		source = AxiStreamSource[PayloadValue | None](
			AxiStreamBus.bind(dut, prefix="s", last=True),
			clock,
			reset=reset,
			reset_active_high=True,
			payload=DirectIntegerDrive(dut.s_tdata) if implementation == "direct" else None,
		)
		sink = AxiStreamSink(AxiStreamBus.bind(dut, prefix="m", last=True), clock, reset=reset, reset_active_high=True)
		await source.initialise()
		await sink.initialise()
		dut.reset.value = 0
		await source.wait_available()
		await sink.wait_available()
	else:
		legacy = import_module("cocotbext.axi")
		byte_size = width if implementation == "legacy-word" else 8
		tx = legacy.AxiStreamSource(legacy.AxiStreamBus.from_prefix(dut, "s"), clock, reset=reset, byte_size=byte_size)
		rx = legacy.AxiStreamSink(legacy.AxiStreamBus.from_prefix(dut, "m"), clock, reset=reset, byte_size=byte_size)
		await FallingEdge(clock)
		dut.reset.value = 0
		await FallingEdge(clock)

	random = Random(2028)
	payloads = [tuple(random.getrandbits(width) for _ in range(frame_size)) for _ in range(frame_count)]
	bytes_per_beat = width // 8
	codec = _codec(width)
	encoded = []
	if implementation == "legacy":
		encoded = [b"".join(word.to_bytes(bytes_per_beat, "little") for word in data) for data in payloads]
	received: list[tuple[int, ...]] = []
	snapshots: list[list[AxiStreamTransfer[PayloadValue | None]]] = []

	def decode_coaxi(packet: list[AxiStreamTransfer[PayloadValue | None]]) -> tuple[int, ...]:
		assert len(packet) == frame_size and packet[-1].last is True
		return tuple(int(beat.data) for beat in packet)

	def decode_bytes(packet: bytes | bytearray) -> tuple[int, ...]:
		assert len(packet) == frame_size * bytes_per_beat
		if codec is not None:
			return tuple(word for (word,) in codec.iter_unpack(packet))
		return tuple(
			int.from_bytes(packet[i : i + bytes_per_beat], "little") for i in range(0, len(packet), bytes_per_beat)
		)

	async def produce() -> None:
		if frame_loop:
			# First calls wait for a fresh edge; subsequent frames reuse cleanup.
			await falling
			for data in payloads:
				await _send_frame(source_bus, source_payload, data, rising, falling, rising_interior=rising_interior)
		elif using_coaxi:
			for data in payloads:
				await source.send_frame(data)
		else:
			for data in payloads if implementation == "legacy-word" else encoded:
				await tx.send(data)
			await tx.wait()

	async def consume() -> None:
		if frame_loop:
			await falling
			for _ in range(frame_count):
				packet = await _recv_frame(sink_bus, sink_payload, rising, falling, rising_interior=rising_interior)
				received.append(decode_coaxi(packet))
		elif using_coaxi:
			for _ in range(frame_count):
				packet = await sink.recv_frame(max_transfers=frame_size)
				if implementation == "deferred":
					snapshots.append(packet)
				else:
					received.append(decode_coaxi(packet))
		else:
			for _ in range(frame_count):
				packet = await rx.recv(compact=False)
				if implementation == "legacy-word":
					assert len(packet.tdata) == frame_size
					received.append(tuple(packet.tdata))
				else:
					received.append(decode_bytes(packet.tdata))

	async def exchange() -> None:
		producer = cocotb.start_soon(produce())
		await consume()
		await producer

	start = perf_counter()
	if profile is not None:
		profile.enable()
	await with_timeout(exchange(), (beats + 32) * 30, "ns")
	if profile is not None:
		profile.disable()
	elapsed = perf_counter() - start
	await Timer(1, unit="step")
	await ReadOnly()
	if implementation == "deferred":
		received.extend(decode_coaxi(packet) for packet in snapshots)
	assert received == payloads
	assert int(dut.accepted.value) == int(dut.retired.value) == beats
	first, last = int(dut.first_cycle.value), int(dut.last_cycle.value)
	cycles = last - first + 1
	# An input stall on cycle n causes an output bubble on cycle n + 1.
	bubbles = (last - 1) // stall_period - (first - 2) // stall_period if stall_period else 0
	assert cycles == beats + bubbles, f"{beats} transfers, {bubbles} expected stalls, {cycles} cycles"
	if os.environ["BENCH_CHECK_DRIVE_PHASE"] == "1":
		assert str(dut.first_offer_high.value) == "0", "the first offer must be on a falling edge"
		assert str(dut.last_clear_high.value) == "0", "the final valid clear must be on a falling edge"
		assert str(dut.first_ready_high.value) == "0", "the first ready assertion must be on a falling edge"
		assert str(dut.last_ready_clear_high.value) == "0", "the final ready clear must be on a falling edge"
		assert str(dut.s_tvalid.value) == str(dut.s_tlast.value) == str(dut.m_tready.value) == "0"
		rising_drives = int(dut.rising_drives.value)
		assert (rising_drives > 0) == (rising_interior and frame_size > 1), f"{rising_drives} rising-edge drives"
		assert int(dut.falling_drives.value) > 0, "no falling-edge drives observed"
	if profile is not None:
		profile.dump_stats(profile_path)
	Path(os.environ["BENCH_RESULT"]).write_text(json.dumps({"seconds": elapsed, "cycles": cycles}), encoding="utf-8")


def _main() -> None:
	if not __debug__:
		raise RuntimeError("The benchmark requires assertions; run without -O or PYTHONOPTIMIZE")
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--beats", type=int, default=65536)
	parser.add_argument("--frame-size", type=int, nargs="+", default=[1, 256])
	parser.add_argument("--repeat", type=int, default=3)
	parser.add_argument("--trust-inertial", choices=["0", "1"], nargs="+", default=["0", "1"])
	parser.add_argument("--reset-pin", action="store_true")
	parser.add_argument("--width", type=int, default=16, help="payload width in bits")
	parser.add_argument("--stall-period", type=int, default=0, help="DUT blocks input every N cycles (0 disables)")
	parser.add_argument(
		"--implementation",
		choices=["coaxi", "legacy", "legacy-word", "deferred", "direct", *_FRAME_LOOPS],
		nargs="+",
		default=["coaxi", "legacy"],
	)
	parser.add_argument("--legacy-path", type=Path)
	parser.add_argument("--baseline-path", type=Path, help="also measure an older checkout's src/ directory")
	parser.add_argument("--profile", type=Path)
	parser.add_argument("--check-drive-phase", action="store_true", help="audit drive edges instead of measuring speed")
	args = parser.parse_args()
	if args.beats <= 0 or args.repeat <= 0 or any(size <= 0 or args.beats % size for size in args.frame_size):
		parser.error("use positive counts and frame sizes that divide the beat count")
	if args.width < 8 or args.width > 512 or args.width % 8:
		parser.error("--width must be a multiple of eight in 8..512")
	if args.stall_period < 0 or args.stall_period == 1:
		parser.error("--stall-period must be zero or at least two")
	implementations = list(dict.fromkeys(args.implementation))
	if args.reset_pin and set(implementations).intersection(_FRAME_LOOPS):
		parser.error("the benchmark-only frame loops do not monitor reset")
	if args.check_drive_phase and set(implementations).intersection(("legacy", "legacy-word")):
		parser.error("--check-drive-phase checks coaxi and the benchmark-only frame loops")
	if args.baseline_path:
		if not (args.baseline_path / "coaxi" / "__init__.py").is_file():
			parser.error("--baseline-path must contain the baseline coaxi package")
		os.environ["BENCH_BASELINE_PATH"] = str(args.baseline_path.resolve())
		implementations.insert(0, "baseline")
	if args.profile and len(implementations) * len(args.frame_size) * len(args.trust_inertial) * args.repeat != 1:
		parser.error("profiling requires exactly one measurement")
	if args.legacy_path:
		sys.path.append(str(args.legacy_path.resolve()))
	os.environ.pop("BENCH_PROFILE", None)

	tests = Path(__file__).resolve().parent
	with TemporaryDirectory() as name:
		scratch = Path(name)
		runner = get_runner("nvc")
		runner.build(
			sources=[tests / "hdl" / "stream_benchmark.vhd"],
			hdl_toplevel="stream_benchmark",
			build_args=["--std=2008"],
			build_dir=scratch,
		)
		for size in args.frame_size:
			for trust in args.trust_inertial:
				times: dict[str, list[float]] = {kind: [] for kind in implementations}
				cycle_counts: dict[str, set[int]] = {kind: set() for kind in implementations}
				for repeat in range(args.repeat):
					offset = repeat % len(implementations)
					kinds = implementations[offset:] + implementations[:offset]
					for kind in kinds:
						result = scratch / "timing.json"
						result.unlink(missing_ok=True)
						os.environ["COCOTB_TRUST_INERTIAL_WRITES"] = trust
						os.environ.update(
							BENCH_IMPLEMENTATION=kind,
							BENCH_BEATS=str(args.beats),
							BENCH_FRAME_SIZE=str(size),
							BENCH_RESET=str(int(args.reset_pin)),
							BENCH_WIDTH=str(args.width),
							BENCH_STALL_PERIOD=str(args.stall_period),
							BENCH_CHECK_DRIVE_PHASE=str(int(args.check_drive_phase)),
							BENCH_RESULT=str(result),
						)
						if args.profile:
							os.environ["BENCH_PROFILE"] = str(args.profile.resolve())
						if kind == "baseline":
							sys.path.insert(0, os.environ["BENCH_BASELINE_PATH"])
						try:
							xml = runner.test(
								hdl_toplevel="stream_benchmark",
								test_module="bench_stream",
								test_dir=scratch,
								parameters={
									"data_width": args.width,
									"stall_period": args.stall_period,
									"check_drive_phase": "true" if args.check_drive_phase else "false",
								},
								results_xml=str(scratch / "results.xml"),
								log_file=scratch / "run.log",
							)
						finally:
							if kind == "baseline":
								sys.path.pop(0)
						cases = ElementTree.parse(xml).findall(".//testcase")
						if (
							len(cases) != 1
							or any(cases[0].find(s) is not None for s in ("failure", "error", "skipped"))
							or not result.is_file()
						):
							raise RuntimeError((scratch / "run.log").read_text(encoding="utf-8"))
						measurement = json.loads(result.read_text(encoding="utf-8"))
						times[kind].append(measurement["seconds"])
						cycle_counts[kind].add(measurement["cycles"])
				for kind, samples in times.items():
					cycles = "/".join(map(str, sorted(cycle_counts[kind])))
					label = (
						f"{kind:8} width={args.width:3} frame={size:4} trust={trust} reset={int(args.reset_pin)} "
						f"stall={args.stall_period} {args.beats} beats / {cycles} cycles"
					)
					if args.check_drive_phase:
						print(f"{label}: drive phase checked", flush=True)
					else:
						print(
							f"{label}: {median(samples):.3f} s median ({args.beats / median(samples):.0f} beats/s), "
							f"samples: {', '.join(f'{s:.3f}' for s in samples)}",
							flush=True,
						)


if __name__ == "__main__":
	_main()

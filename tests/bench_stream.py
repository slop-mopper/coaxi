# bench_stream.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.2-sol

"""Measure AXI-Stream loopback throughput with an optional cocotbext-axi comparison."""

import os
import sys
import json
import logging
import argparse
from time import perf_counter
from pathlib import Path
from struct import pack, unpack
from cProfile import Profile
from tempfile import TemporaryDirectory
from importlib import import_module
from statistics import median
from xml.etree import ElementTree

import cocotb
from cocotb.clock import Clock
from cocotb.handle import HierarchyObject
from cocotb.triggers import Timer, ReadOnly, FallingEdge, with_timeout
from cocotb_tools.runner import get_runner


@cocotb.test()
async def stream_throughput(dut: HierarchyObject) -> None:
	"""Verify all payloads, frame lengths, hardware counts, and handshake spacing."""
	implementation = os.environ["BENCH_IMPLEMENTATION"]
	using_coaxi = implementation != "legacy"
	beats = int(os.environ["BENCH_BEATS"])
	frame_size = int(os.environ["BENCH_FRAME_SIZE"])
	reset_pin = os.environ["BENCH_RESET"] == "1"
	frame_count = beats // frame_size
	profile_path = os.environ.get("BENCH_PROFILE")
	profile = Profile() if profile_path else None
	logging.getLogger("coaxi.stream").setLevel(logging.WARNING)
	logging.getLogger(f"cocotb.{dut._name}").setLevel(logging.WARNING)

	clock = dut.clock
	cocotb.start_soon(Clock(clock, 10, unit="ns", impl="gpi").start(start_high=False))
	reset = dut.reset if reset_pin else None
	dut.reset.value = int(reset_pin)
	if using_coaxi:
		from coaxi import AxiStreamBus, AxiStreamSink, AxiStreamSource

		if implementation == "baseline":
			baseline = Path(os.environ["BENCH_BASELINE_PATH"])
			assert Path(import_module("coaxi").__file__).resolve().parent == baseline / "coaxi"
		source = AxiStreamSource(
			AxiStreamBus.bind(dut, prefix="s", last=True), clock, reset=reset, reset_active_high=True
		)
		sink = AxiStreamSink(AxiStreamBus.bind(dut, prefix="m", last=True), clock, reset=reset, reset_active_high=True)
		await source.initialise()
		await sink.initialise()
		dut.reset.value = 0
		await source.wait_available()
		await sink.wait_available()
	else:
		legacy = import_module("cocotbext.axi")
		tx = legacy.AxiStreamSource(legacy.AxiStreamBus.from_prefix(dut, "s"), clock, reset=reset)
		rx = legacy.AxiStreamSink(legacy.AxiStreamBus.from_prefix(dut, "m"), clock, reset=reset)
		await FallingEdge(clock)
		dut.reset.value = 0
		await FallingEdge(clock)

	# Repeat byte-aligned frames with a different first word on each frame.
	payloads = [tuple((first + i * 71) & 0xFFFF for i in range(frame_size)) for first in range(frame_count)]
	encoded = [pack(f"<{frame_size}H", *data) for data in payloads] if implementation == "legacy" else []
	received: list[tuple[int, ...]] = []

	async def produce() -> None:
		if using_coaxi:
			for data in payloads:
				await source.send_frame(data)
		else:
			for data in encoded:
				await tx.send(data)
			await tx.wait()

	async def consume() -> None:
		if using_coaxi:
			for _ in range(frame_count):
				packet = await sink.recv_frame(max_transfers=frame_size)
				received.append(tuple(int(beat.data) for beat in packet))
				assert packet[-1].last is True
		else:
			for _ in range(frame_count):
				packet = await rx.recv(compact=False)
				received.append(unpack(f"<{frame_size}H", packet.tdata))

	async def exchange() -> None:
		producer = cocotb.start_soon(produce())
		await consume()
		await producer

	start = perf_counter()
	if profile is not None:
		profile.enable()
	await with_timeout(exchange(), (beats + 32) * 20, "ns")
	if profile is not None:
		profile.disable()
	elapsed = perf_counter() - start
	await Timer(1, unit="step")
	await ReadOnly()
	assert received == payloads
	assert int(dut.accepted.value) == int(dut.retired.value) == beats
	cycles = int(dut.last_cycle.value) - int(dut.first_cycle.value) + 1
	assert cycles == beats, f"{beats} transfers took {cycles} cycles"
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
	parser.add_argument("--implementation", choices=["coaxi", "legacy"], nargs="+", default=["coaxi", "legacy"])
	parser.add_argument("--legacy-path", type=Path)
	parser.add_argument("--baseline-path", type=Path, help="also measure an older checkout's src/ directory")
	parser.add_argument("--profile", type=Path)
	args = parser.parse_args()
	if args.beats <= 0 or args.repeat <= 0 or any(size <= 0 or args.beats % size for size in args.frame_size):
		parser.error("use positive counts and frame sizes that divide the beat count")
	implementations = list(dict.fromkeys(args.implementation))
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
			log_file=scratch / "build.log",
		)
		for size in args.frame_size:
			for trust in args.trust_inertial:
				times: dict[str, list[float]] = {kind: [] for kind in implementations}
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
						times[kind].append(json.loads(result.read_text(encoding="utf-8"))["seconds"])
				for kind, samples in times.items():
					print(
						f"{kind:6} frame={size:4} trust={trust} reset={int(args.reset_pin)} "
						f"{args.beats} beats / {args.beats} cycles: {median(samples):.3f} s median "
						f"({args.beats / median(samples):.0f} beats/s), samples: {', '.join(f'{s:.3f}' for s in samples)}",
						flush=True,
					)


if __name__ == "__main__":
	_main()

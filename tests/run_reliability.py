# run_reliability.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Run seeded AXI4-Stream stress tests or targeted mutations in disposable source copies."""

import os
import sys
import json
import shutil
import signal
import hashlib
import argparse
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass
from xml.etree import ElementTree
from collections import Counter


@dataclass(frozen=True)
class _Mutation:
	name: str
	file: str
	before: str
	after: str
	test: str
	message: str


_MUTATIONS = [
	_Mutation(
		"drop_user",
		"_sideband.py",
		"\t\t\tself._handles[role].set(value)",
		'\t\t\tself._handles[role].set(0 if role == "user" else value)',
		"source_wire_scoreboard",
		"wire mismatch",
	),
	_Mutation(
		"duplicate_acceptance",
		"_stream.py",
		"\t\tawait self._wait_edge(self._falling_edge, token)\n\t\tself._check(token)\n\t\tself._bus.valid.set(0)",
		"\t\tawait self._wait_edge(self._rising_edge, token)\n\t\tself._check(token)\n\t\tself._bus.valid.set(0)",
		"source_wire_scoreboard",
		"wire mismatch",
	),
	_Mutation(
		"retire_one_instead_of_packet",
		"_stream.py",
		"\t\t\tself._retained -= count",
		"\t\t\tself._retained -= 1",
		"sink_wire_scoreboard",
		"retention mismatch",
	),
	_Mutation(
		"leave_collector_running",
		"_stream.py",
		"\t\t# its generation guard return rather than trying to cancel this task.\n"
		"\t\tif task is not None and task is not current_task():\n\t\t\ttask.cancel()",
		"\t\t# its generation guard return rather than trying to cancel this task.\n"
		"\t\tif task is not None and task is not current_task():\n\t\t\tpass",
		"lifecycle_accounting",
		"background task survived close",
	),
]


def _require_checks() -> None:
	if not __debug__:
		raise RuntimeError("HARNESS: Python optimisation disables safety assertions; run without -O/PYTHONOPTIMIZE")


def _hashes(root: Path) -> dict[str, str]:
	return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob("*.py")}


def _worker(root: Path, mode: str) -> list[ElementTree.Element]:
	log = root / f"worker-{mode}.log"
	with log.open("w") as output:
		process = subprocess.Popen(
			[sys.executable, "-I", "-B", str(root / "tests" / "reliability_worker.py"), str(root), mode],
			cwd=root,
			stdout=output,
			stderr=subprocess.STDOUT,
			start_new_session=True,
		)
		try:
			code = process.wait(timeout=120)
		except subprocess.TimeoutExpired as exc:
			os.killpg(process.pid, signal.SIGTERM)
			try:
				process.wait(timeout=5)
			except subprocess.TimeoutExpired:
				os.killpg(process.pid, signal.SIGKILL)
				process.wait(timeout=5)
			raise RuntimeError(f"HARNESS: worker timeout, not a mutation kill: {root.name}/{mode}") from exc
	if code:
		raise RuntimeError(f"HARNESS: worker exit {code}, not a mutation kill:\n{log.read_text()[-8000:]}")
	xml = root / f"results-{mode}.xml"
	if not xml.is_file():
		raise RuntimeError(f"HARNESS: no fresh XML: {root.name}/{mode}\n{log.read_text()[-8000:]}")
	return ElementTree.parse(xml).findall(".//testcase")


def _inventory(cases: list[ElementTree.Element]) -> set[tuple[str, str]]:
	_require_checks()
	keys = [(case.attrib["classname"], case.attrib["name"]) for case in cases]
	assert len(set(keys)) == len(keys) == 4, "HARNESS: duplicate/missing cases"
	counts = Counter(name.split("/")[0] for _, name in keys)
	assert counts == {"source_wire_scoreboard": 1, "sink_wire_scoreboard": 2, "lifecycle_accounting": 1}, counts
	assert not any(case.find("skipped") is not None or case.find("error") is not None for case in cases)
	return set(keys)


def _check_mutant(cases: list[ElementTree.Element], baseline: set[tuple[str, str]], mutation: _Mutation) -> int:
	_require_checks()
	assert _inventory(cases) == baseline, "HARNESS: inventory differs from passing baseline"
	failures = [(case, case.find("failure")) for case in cases if case.find("failure") is not None]
	assert failures, f"SURVIVED: {mutation.name}"
	for case, failure in failures:
		assert failure is not None
		text = str(failure.attrib) + (failure.text or "")
		assert (
			case.attrib["name"].startswith(mutation.test + "/")
			and failure.attrib.get("type") == "AssertionError"
			and "[reliability]" in text
			and mutation.message in text
			and "reliability_cases.py" in text
			and "HARNESS:" not in text
			and "SimTimeoutError" not in text
		), f"HARNESS: unrelated failure, not a kill: {mutation.name}: {case.attrib}: {text[:4000]}"
	return len(failures)


def _mutations(root: Path) -> None:
	_require_checks()
	(root / "reliability-results.json").unlink(missing_ok=True)
	originals = _hashes(root / "src")
	summary = []
	try:
		with tempfile.TemporaryDirectory(prefix="coaxi-mutations-") as directory:
			base = Path(directory)
			snapshot = base / "snapshot"
			shutil.copytree(root / "src", snapshot / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
			(snapshot / "tests" / "hdl").mkdir(parents=True)
			for name in ("reliability_cases.py", "reliability_worker.py"):
				shutil.copyfile(root / "tests" / name, snapshot / "tests" / name)
			shutil.copyfile(root / "tests" / "hdl" / "stream_dut.vhd", snapshot / "tests" / "hdl" / "stream_dut.vhd")
			inventories: dict[str, set[tuple[str, str]]] = {}
			for mutation in [None, *_MUTATIONS]:
				name = mutation.name if mutation else "baseline"
				variant = base / name
				shutil.copytree(snapshot, variant)
				before = _hashes(variant / "src")
				if mutation is not None:
					path = variant / "src" / "coaxi" / mutation.file
					text = path.read_text()
					assert text.count(mutation.before) == 1, f"HARNESS: ambiguous anchor: {name}"
					changed = text.replace(mutation.before, mutation.after)
					compile(changed, str(path), "exec")
					path.write_text(changed)
					assert {key for key, value in _hashes(variant / "src").items() if before[key] != value} == {
						f"coaxi/{mutation.file}"
					}
				for mode in ("0", "1"):
					cases = _worker(variant, mode)
					inventory = _inventory(cases)
					if mutation is None:
						assert not any(case.find("failure") is not None for case in cases), "HARNESS: baseline failed"
						inventories[mode] = inventory
						print(f"baseline mode={mode}: {len(cases)} cases passed", flush=True)
						continue
					failures = _check_mutant(cases, inventories[mode], mutation)
					summary.append({"mutation": name, "mode": mode, "status": "killed", "failures": failures})
					print(f"killed {name} mode={mode}: independent {mutation.test} assertion", flush=True)
	finally:
		assert _hashes(root / "src") == originals, "HARNESS: working library changed"
	(root / "reliability-results.json").write_text(json.dumps(summary, indent=2) + "\n")


def main() -> None:
	"""Run extended stress tests or four bounded mutation checks in both NVC write modes.

	--seeds selects 1..64 integer seeds; --rounds sets 6..600 lifecycle epochs
	and scales traffic per seed. --mutations instead uses seed 73 and 24 rounds
	for passing controls and four exact temporary-copy mutations. A build/import
	failure, timeout, wrong origin or unrelated exception never counts as a kill.
	"""
	_require_checks()
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--seeds", nargs="+", type=int, default=list(range(8)))
	parser.add_argument("--rounds", type=int, default=120)
	parser.add_argument("--mutations", action="store_true")
	args = parser.parse_args()
	if not 1 <= len(args.seeds) <= 64 or not 6 <= args.rounds <= 600:
		parser.error("use 1..64 seeds and 6..600 rounds")
	root = Path(__file__).resolve().parents[1]
	if args.mutations:
		_mutations(root)
		return
	environment = os.environ.copy()
	environment["COAXI_STRESS_SEEDS"] = ",".join(map(str, args.seeds))
	environment["COAXI_STRESS_ROUNDS"] = str(args.rounds)
	print(f"reliability seeds={args.seeds} rounds={args.rounds}, both write modes", flush=True)
	subprocess.run(
		[sys.executable, "-m", "pytest", "-q", "tests/test_simulation.py", "-k", "reliability", "--tb=short"],
		cwd=root,
		env=environment,
		check=True,
		timeout=300,
	)


if __name__ == "__main__":
	main()

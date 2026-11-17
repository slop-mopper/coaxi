# run_numeric_mutations.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check selected numeric faults in disposable copies; no coverage or mutation-score gate."""

import os
import sys
import json
import shutil
import signal
import hashlib
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class _Mutation:
	name: str
	before: str
	after: str
	test: str
	message: str


_MUTATIONS = [
	_Mutation(
		"missing_multiply_growth",
		'left.width + right.width\n\t\t\tif operation == "*"',
		'max(left.width, right.width)\n\t\t\tif operation == "*"',
		"tests/test_numeric_hardening.py::test_small_arithmetic_matrix",
		"value.width == width",
	),
	_Mutation(
		"multiply_adds",
		"result = a * b",
		"result = a + b",
		"tests/test_numeric_hardening.py::test_small_arithmetic_matrix",
		"str(value) ==",
	),
	_Mutation(
		"floor_division",
		"quotient = abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)",
		"quotient = a // b",
		"tests/test_numeric_hardening.py::test_small_arithmetic_matrix",
		"str(value) ==",
	),
	_Mutation(
		"wrong_remainder_sign",
		"result = -remainder if a < 0 else remainder",
		"result = remainder",
		"tests/test_numeric_hardening.py::test_small_arithmetic_matrix",
		"str(value) ==",
	),
	_Mutation(
		"narrowing_loses_sign",
		"text = self._text[0] * (width - len(low)) + low",
		"text = self._text[-width:]",
		"tests/test_numeric.py::test_sizes_and_overflow",
		"int(s.resize(4)) == 7",
	),
	_Mutation(
		"unsigned_right_shift_extends_sign",
		'fill = self._text[0] if arithmetic and self._signed else "0"',
		"fill = self._text[0]",
		"tests/test_numeric_hardening.py::test_unsigned_shift",
		'str(value >> 1) == "0100"',
	),
	_Mutation(
		"mod_normalises_weak_sign",
		'negative = left._text[0] == "1"',
		'negative = left._text[0] in "1H"',
		"tests/test_numeric.py::test_division_and_scalar_quirks",
		'int(Signed(LogicArray("H011")) % Signed.from_int(3, width=4)) == 2',
	),
	_Mutation(
		"no_oversized_divisor_shortcut",
		'if operation == "/" and not reflected and width > self.width:',
		"if False:",
		"tests/test_numeric.py::test_division_and_scalar_quirks",
		"int(minimum / 8) == 0",
	),
	_Mutation(
		"null_concat_uses_left",
		"return type(self)._new(text, other.range)",
		"return type(self)._new(text, self.range)",
		"tests/test_numeric_hardening.py::test_distinct_null_concatenation",
		'bounds(left.concat(right)) == (2, "downto", 3)',
	),
	_Mutation(
		"silent_meta_integer",
		'raise ValueError(f"cannot convert unresolved {type(self).__name__} {self._text} to an integer")',
		"return self.to_logic_array().to_unsigned()",
		"tests/test_numeric_hardening.py::test_resolver_before_import",
		"resolved X with",
	),
	_Mutation(
		"unexpected_exception_erases_case",
		'if operation == "+":\n\t\t\tresult = a + b',
		'if operation == "+":\n\t\t\traise ZeroDivisionError("injected spurious error")',
		"tests/test_numeric_hardening.py::test_valid_oracle_arithmetic",
		"valid oracle case raised",
	),
]

_WORKER = """
import sys
import json
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "src"), str(root)]
import coaxi
origin = Path(coaxi.__file__).resolve()
if not __debug__ or not origin.is_relative_to(root / "src"):
    raise RuntimeError("HARNESS: incorrect interpreter or import origin")
import pytest
class Recorder:
    def __init__(self):
        self.inventory = []
        self.reports = []
    def pytest_collection_finish(self, session):
        self.inventory = [item.nodeid for item in session.items]
    def pytest_runtest_makereport(self, item, call):
        exc = call.excinfo
        self.reports.append({
            "nodeid": item.nodeid,
            "phase": call.when,
            "exception": exc.type.__module__ + "." + exc.type.__name__ if exc else None,
            "message": str(exc.getrepr(style="short")) if exc else "",
            "path": str(Path(exc.traceback[-1].path).resolve().relative_to(root)) if exc else "",
        })
recorder = Recorder()
code = pytest.main(["-q", sys.argv[2], "--tb=short"], plugins=[recorder])
(root / "evidence.json").write_text(json.dumps({
    "origin": str(origin), "inventory": recorder.inventory, "reports": recorder.reports,
}))
raise SystemExit(code)
"""


@dataclass(frozen=True)
class _Report:
	nodeid: str
	phase: str
	exception: str | None
	message: str
	path: str


@dataclass(frozen=True)
class _Outcome:
	code: int
	inventory: tuple[str, ...]
	reports: tuple[_Report, ...]


def _hashes(root: Path) -> dict[str, str]:
	return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.py")}


def _validate(outcome: _Outcome) -> None:
	assert outcome.code in (0, 1), "HARNESS: abnormal worker exit"
	inventory = set(outcome.inventory)
	assert inventory and len(inventory) == len(outcome.inventory), "HARNESS: empty/duplicate inventory"
	for phase in ("setup", "call", "teardown"):
		reports = [r for r in outcome.reports if r.phase == phase]
		assert len(reports) == len(inventory) and {r.nodeid for r in reports} == inventory, (
			"HARNESS: missing/duplicate test phase"
		)
		if phase != "call":
			assert all(r.exception is None for r in reports), "HARNESS: setup/teardown failure"
	assert len(outcome.reports) == 3 * len(inventory), "HARNESS: unexpected phase"


def _check_mutant(outcome: _Outcome, baseline: _Outcome, mutation: _Mutation) -> int:
	"""Count only intended call-phase assertion failures with the full baseline inventory."""
	_validate(outcome)
	_validate(baseline)
	assert baseline.code == 0 and all(r.exception is None for r in baseline.reports), "HARNESS: failed baseline"
	assert set(outcome.inventory) == set(baseline.inventory), "HARNESS: changed inventory"
	failures = [r for r in outcome.reports if r.exception is not None]
	assert outcome.code == 1 and failures, f"SURVIVED: {mutation.name}"
	location = (
		"tests/test_numeric_vhdl.py"
		if mutation.name == "unexpected_exception_erases_case"
		else mutation.test.split("::")[0]
	)
	for report in failures:
		assert report.phase == "call" and report.exception == "builtins.AssertionError", "HARNESS: unrelated exception"
		assert report.path == location and mutation.message in report.message, "HARNESS: unrelated assertion"
		assert "HARNESS:" not in report.message, "HARNESS: nested harness failure"
	return len(failures)


def _run(root: Path, test: str) -> _Outcome:
	environment = os.environ.copy()
	environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
	for key in ("PYTHONOPTIMIZE", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
		environment.pop(key, None)
	log = root / "worker.log"
	with log.open("w") as output:
		process = subprocess.Popen(
			[sys.executable, "-I", "-B", "-c", _WORKER, str(root), test],
			cwd=root,
			env=environment,
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
			raise RuntimeError("HARNESS: timeout is not a mutation kill") from exc
	assert (root / "evidence.json").is_file(), log.read_text()
	data = json.loads((root / "evidence.json").read_text())
	assert Path(data["origin"]).resolve().is_relative_to(root / "src"), "HARNESS: wrong import origin"
	outcome = _Outcome(code, tuple(data["inventory"]), tuple(_Report(**r) for r in data["reports"]))
	_validate(outcome)
	return outcome


def main() -> None:
	"""Run passing controls and eleven targeted faults without editing the working package."""
	if not __debug__:
		raise RuntimeError("HARNESS: run without Python optimisation")
	root = Path(__file__).resolve().parents[1]
	report = root / "numeric-mutation-results.json"
	report.unlink(missing_ok=True)
	before = _hashes(root / "src")
	original = (root / "src" / "coaxi" / "_numeric.py").read_text()
	for mutation in _MUTATIONS:
		assert original.count(mutation.before) == 1, f"HARNESS: ambiguous anchor: {mutation.name}"
		compile(original.replace(mutation.before, mutation.after), "_numeric.py", "exec")
	results: list[dict[str, str | int]] = []
	try:
		with tempfile.TemporaryDirectory(prefix="coaxi-numeric-mutations-") as directory:
			base = Path(directory)
			snapshot = base / "snapshot"
			for part in ("src", "tests"):
				shutil.copytree(
					root / part,
					snapshot / part,
					ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "sim_build"),
				)
			controls: dict[str, _Outcome] = {}
			for number, mutation in enumerate(_MUTATIONS):
				for control in (True, False):
					if control and mutation.test in controls:
						continue
					variant = base / f"{number}-{'control' if control else mutation.name}"
					shutil.copytree(snapshot, variant)
					path = variant / "src" / "coaxi" / "_numeric.py"
					if not control:
						path.write_text(original.replace(mutation.before, mutation.after))
						assert {k for k, v in _hashes(variant / "src").items() if before[k] != v} == {
							"coaxi/_numeric.py"
						}
					outcome = _run(variant, mutation.test)
					if control:
						assert outcome.code == 0 and all(r.exception is None for r in outcome.reports), (
							f"HARNESS: baseline failed: {mutation.test}"
						)
						if mutation.test.endswith(("test_small_arithmetic_matrix", "test_distinct_null_concatenation")):
							expected_count = 2
						elif mutation.test.endswith("test_resolver_before_import"):
							expected_count = 4
						else:
							expected_count = 1
						assert len(outcome.inventory) == expected_count, "HARNESS: incomplete selected tests"
						controls[mutation.test] = outcome
						print(f"control passed: {mutation.test}", flush=True)
					else:
						failures = _check_mutant(outcome, controls[mutation.test], mutation)
						results.append({"mutation": mutation.name, "status": "killed", "failures": failures})
						print(f"killed {mutation.name}: intended assertion", flush=True)
	finally:
		assert _hashes(root / "src") == before, "HARNESS: working package changed"
	report.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
	main()

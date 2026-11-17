# test_numeric_mutation_harness.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Reject unrelated failures as evidence that a numeric mutation was detected."""

import sys
import signal
import subprocess
from pathlib import Path
from dataclasses import replace

import pytest

from tests import run_numeric_mutations
from tests.run_numeric_mutations import _Mutation, _Outcome, _Report, _check_mutant, _run


_NODE = "tests/test_probe.py::test_probe"
_MUTATION = _Mutation("probe", "", "", _NODE, "intended assertion")
_CONTROL = _Outcome(0, (_NODE,), tuple(_Report(_NODE, phase, None, "", "") for phase in ("setup", "call", "teardown")))
_FAILURE = _Report(_NODE, "call", "builtins.AssertionError", "intended assertion", "tests/test_probe.py")
_DETECTED = replace(_CONTROL, code=1, reports=(_CONTROL.reports[0], _FAILURE, _CONTROL.reports[2]))


def test_mutation_accepts_intended_failure() -> None:
	"""The control passes and the mutant fails at the declared call-phase assertion."""
	assert _check_mutant(_DETECTED, _CONTROL, _MUTATION) == 1


@pytest.mark.parametrize(
	"outcome",
	[
		replace(_DETECTED, code=0),
		replace(_DETECTED, code=2),
		replace(_DETECTED, code=-9),
		replace(_DETECTED, inventory=()),
		replace(_DETECTED, inventory=(_NODE, _NODE)),
		replace(_DETECTED, inventory=("tests/test_wrong.py::test_wrong",)),
		replace(_DETECTED, reports=(_FAILURE,)),
		replace(_DETECTED, reports=(*_DETECTED.reports, _FAILURE)),
		replace(
			_DETECTED,
			reports=(_CONTROL.reports[0], replace(_FAILURE, exception="builtins.TypeError"), _CONTROL.reports[2]),
		),
		replace(
			_DETECTED,
			reports=(_CONTROL.reports[0], replace(_FAILURE, exception="builtins.RuntimeError"), _CONTROL.reports[2]),
		),
		replace(
			_DETECTED,
			reports=(_CONTROL.reports[0], replace(_FAILURE, exception="unittest.SkipTest"), _CONTROL.reports[2]),
		),
		replace(
			_DETECTED,
			reports=(_CONTROL.reports[0], replace(_FAILURE, message="unrelated assertion"), _CONTROL.reports[2]),
		),
		replace(
			_DETECTED, reports=(_CONTROL.reports[0], replace(_FAILURE, path="tests/test_wrong.py"), _CONTROL.reports[2])
		),
		replace(_DETECTED, reports=(_CONTROL.reports[0], replace(_FAILURE, nodeid="wrong"), _CONTROL.reports[2])),
		replace(_DETECTED, reports=(replace(_FAILURE, phase="setup"), _CONTROL.reports[1], _CONTROL.reports[2])),
		replace(_DETECTED, reports=(_CONTROL.reports[0], _CONTROL.reports[1], replace(_FAILURE, phase="teardown"))),
	],
)
def test_mutation_rejects_bad_evidence(outcome: _Outcome) -> None:
	"""Crashes, incomplete execution, skips, and unrelated exceptions cannot count as kills."""
	with pytest.raises(AssertionError):
		_check_mutant(outcome, _CONTROL, _MUTATION)


def test_mutation_invalidates_stale_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""A failed preflight must not leave an earlier successful report in place."""
	package = tmp_path / "src" / "coaxi"
	package.mkdir(parents=True)
	(package / "_numeric.py").write_text("")
	report = tmp_path / "numeric-mutation-results.json"
	report.write_text('{"stale": true}')
	monkeypatch.setattr(run_numeric_mutations, "__file__", str(tmp_path / "tests" / "run_numeric_mutations.py"))
	with pytest.raises(AssertionError, match="ambiguous anchor"):
		run_numeric_mutations.main()
	assert not report.exists()


def test_mutation_rejects_failed_control() -> None:
	"""The selected tests must pass against the working implementation first."""
	with pytest.raises(AssertionError, match="failed baseline"):
		_check_mutant(_DETECTED, _DETECTED, _MUTATION)


def test_mutation_rejects_wrong_import(tmp_path: Path) -> None:
	"""An installed or editable package outside the temporary copy is not a valid control."""
	with pytest.raises(AssertionError, match="incorrect interpreter or import origin"):
		_run(tmp_path, _NODE)


def test_mutation_ignores_inherited_pytest_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Inherited selection filters and optimisation cannot hide selected parameter cases."""
	package = tmp_path / "src" / "coaxi"
	package.mkdir(parents=True)
	(package / "__init__.py").write_text("")
	(tmp_path / "test_probe.py").write_text(
		"import pytest\n@pytest.mark.parametrize('n', [0, 1])\ndef test_probe(n):\n    assert n in (0, 1)\n"
	)
	monkeypatch.setenv("PYTEST_ADDOPTS", "-k cannot_match --maxfail=1")
	monkeypatch.setenv("PYTEST_PLUGINS", "nonexistent_plugin")
	monkeypatch.setenv("PYTHONOPTIMIZE", "2")
	outcome = _run(tmp_path, "test_probe.py")
	assert outcome.code == 0 and len(outcome.inventory) == 2


def test_mutation_rejects_optimised_parent() -> None:
	"""Optimisation must fail before starting any mutation or writing a success report."""
	root = Path(__file__).resolve().parents[1]
	result = subprocess.run(
		[sys.executable, "-O", str(root / "tests" / "run_numeric_mutations.py")],
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		timeout=15,
		check=False,
	)
	assert result.returncode != 0 and "HARNESS: run without Python optimisation" in result.stdout


def test_mutation_timeout_is_not_a_kill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""A timed-out worker receives TERM then KILL and cannot produce a mutation verdict."""

	class Stalled:
		pid = 12345
		waits = 0

		def wait(self, timeout: float) -> int:
			self.waits += 1
			if self.waits < 3:
				raise subprocess.TimeoutExpired("worker", timeout)
			return -9

	signals: list[tuple[int, int]] = []
	monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Stalled())
	monkeypatch.setattr("tests.run_numeric_mutations.os.killpg", lambda pid, sig: signals.append((pid, sig)))
	with pytest.raises(RuntimeError, match="timeout is not a mutation kill"):
		_run(tmp_path, _NODE)
	assert signals == [(12345, signal.SIGTERM), (12345, signal.SIGKILL)]

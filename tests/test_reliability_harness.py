# test_reliability_harness.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Mutation verdicts must not mistake broken infrastructure or unrelated tests for detection."""

import sys
import subprocess
from pathlib import Path
from xml.etree import ElementTree

import pytest
from tests.run_reliability import _MUTATIONS, _check_mutant, _inventory


def _cases() -> list[ElementTree.Element]:
	return [
		ElementTree.Element("testcase", classname="reliability_cases", name=f"{name}/seed=73{suffix}")
		for name, suffix in (
			("source_wire_scoreboard", ""),
			("sink_wire_scoreboard", "/ready=False"),
			("sink_wire_scoreboard", "/ready=True"),
			("lifecycle_accounting", ""),
		)
	]


@pytest.mark.parametrize(
	"problem",
	[
		"valid_kill",
		"survived",
		"wrong_type",
		"wrong_message",
		"wrong_test",
		"wrong_origin",
		"timeout",
		"skip",
		"missing",
	],
)
def test_mutation_verdict(problem: str) -> None:
	"""Only the intended named test's specific assertion constitutes a mutation kill."""
	baseline = _inventory(_cases())
	cases = _cases()
	failure = ElementTree.SubElement(cases[0], "failure", type="AssertionError", message="[reliability] wire mismatch")
	failure.text = (
		'Traceback:\n File "tests/reliability_cases.py", line 90\nAssertionError: [reliability] wire mismatch'
	)
	if problem == "survived":
		cases[0].remove(failure)
	elif problem == "wrong_type":
		failure.set("type", "ValueError")
	elif problem == "wrong_message":
		failure.set("message", "different failure")
		failure.text = ""
	elif problem == "wrong_test":
		cases[0].remove(failure)
		cases[-1].append(failure)
	elif problem == "wrong_origin":
		failure.text += "\nHARNESS: wrong module origin"
	elif problem == "timeout":
		failure.set("type", "SimTimeoutError")
	elif problem == "skip":
		ElementTree.SubElement(cases[-1], "skipped")
	elif problem == "missing":
		cases.pop()
	if problem == "valid_kill":
		assert _check_mutant(cases, baseline, _MUTATIONS[0]) == 1
	else:
		with pytest.raises(AssertionError):
			_check_mutant(cases, baseline, _MUTATIONS[0])


@pytest.mark.parametrize("entry", ["command", "verdict"])
def test_optimised_interpreter_is_rejected(entry: str) -> None:
	"""An optimised parent must never label a passing mutant as detected."""
	root = Path(__file__).resolve().parents[1]
	arguments = [str(root / "tests" / "run_reliability.py"), "--mutations"]
	if entry == "verdict":
		arguments = [
			"-c",
			(
				"from tests.test_reliability_harness import _cases; "
				"from tests.run_reliability import _MUTATIONS, _check_mutant; "
				"cases = _cases(); "
				"baseline = {(case.attrib['classname'], case.attrib['name']) for case in cases}; "
				"_check_mutant(cases, baseline, _MUTATIONS[0])"
			),
		]
	result = subprocess.run(
		[sys.executable, "-O", *arguments], cwd=root, capture_output=True, text=True, timeout=30, check=False
	)
	assert result.returncode != 0
	assert "Python optimisation disables safety assertions" in result.stderr
	assert "killed" not in result.stdout

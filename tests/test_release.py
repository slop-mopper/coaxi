# test_release.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Regression tests for build-free release guards; no package-index access or uploads."""

import sys
import tomllib
import subprocess
from pathlib import Path

import pytest

from tests.check_release import check_release_ref
from tests.check_release import distribution_paths
from tests.check_release import release_destination


def _project(root: Path, version: str = "1.0.0", locked: str = "1.0.0") -> None:
	(root / "pyproject.toml").write_text(f'[project]\nname = "coaxi"\nversion = "{version}"\n', encoding="utf-8")
	(root / "uv.lock").write_text(f'[[package]]\nname = "coaxi"\nversion = "{locked}"\n', encoding="utf-8")


@pytest.mark.parametrize("version", ["1.0.0", "1.0.1rc1"])
def test_matching_release_ref(tmp_path: Path, version: str) -> None:
	"""Exact version tags, including pre-release versions, match project and lock metadata."""
	_project(tmp_path, version, version)
	assert check_release_ref(tmp_path, f"refs/tags/v{version}") == version


@pytest.mark.parametrize(
	"ref",
	[
		"",
		"refs/heads/master",
		"refs/heads/v1.0.0",
		"v1.0.0",
		"refs/tags/1.0.0",
		"refs/tags/v0.1.0",
		"refs/tags/v1.0.0\n",
	],
)
def test_wrong_release_ref(tmp_path: Path, ref: str) -> None:
	"""Branches, different versions and near-matches cannot be published."""
	_project(tmp_path)
	with pytest.raises(ValueError, match="Release must run on"):
		check_release_ref(tmp_path, ref)


def test_stale_release_lock(tmp_path: Path) -> None:
	"""A stale locked version fails even with the correct tag."""
	_project(tmp_path, locked="0.1.0")
	with pytest.raises(ValueError, match="uv.lock"):
		check_release_ref(tmp_path, "refs/tags/v1.0.0")


@pytest.mark.parametrize(
	("event", "destination", "expected"),
	[
		("push", "", "pypi"),
		("push", "test-pypi", "pypi"),
		("push", "pypi", "pypi"),
		("workflow_dispatch", "pypi", "pypi"),
		("workflow_dispatch", "test-pypi", "test-pypi"),
	],
)
def test_release_destination(event: str, destination: str, expected: str) -> None:
	"""Tag pushes select production; explicit manual runs can select either index."""
	assert release_destination(event, destination) == expected


@pytest.mark.parametrize(
	("event", "destination"),
	[
		("pull_request", "pypi"),
		("release", "pypi"),
		("", "pypi"),
		("workflow_dispatch", ""),
		("workflow_dispatch", "testpypi"),
		("workflow_dispatch", "pypi\n"),
	],
)
def test_invalid_release_destination(event: str, destination: str) -> None:
	"""Unknown events and missing or malformed manual selections fail closed."""
	with pytest.raises(ValueError, match="Unsupported release"):
		release_destination(event, destination)


@pytest.mark.parametrize(
	("event", "destination", "expected"),
	[("push", "", "pypi"), ("workflow_dispatch", "pypi", "pypi"), ("workflow_dispatch", "test-pypi", "test-pypi")],
)
def test_release_cli_outputs(event: str, destination: str, expected: str) -> None:
	"""The exact guard command used in CI emits the effective destination for the publish job."""
	root = Path(__file__).resolve().parents[1]
	version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
	result = subprocess.run(
		[
			sys.executable,
			"tests/check_release.py",
			f"refs/tags/v{version}",
			"--event",
			event,
			"--destination",
			destination,
		],
		cwd=root,
		check=True,
		capture_output=True,
		text=True,
		timeout=30,
	)
	assert result.stdout.splitlines() == [f"version={version}", f"destination={expected}"]


@pytest.mark.parametrize(
	("ref", "event", "destination"),
	[
		("refs/heads/master", "push", ""),
		("refs/tags/v-mismatch", "push", ""),
		(None, "workflow_dispatch", ""),
		(None, "workflow_dispatch", "testpypi"),
		(None, "pull_request", "pypi"),
	],
)
def test_release_cli_rejects_without_outputs(ref: str | None, event: str, destination: str) -> None:
	"""Invalid refs, events and destinations must fail before publishing any workflow output."""
	root = Path(__file__).resolve().parents[1]
	version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
	result = subprocess.run(
		[
			sys.executable,
			"tests/check_release.py",
			ref if ref is not None else f"refs/tags/v{version}",
			"--event",
			event,
			"--destination",
			destination,
		],
		cwd=root,
		check=False,
		capture_output=True,
		text=True,
		timeout=30,
	)
	assert result.returncode != 0
	assert result.stdout == ""
	assert "ValueError:" in result.stderr


def test_workflow_release_wiring() -> None:
	"""Static wiring checks complement Actionlint; they do not simulate GitHub event delivery."""
	root = Path(__file__).resolve().parents[1]
	workflow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
	assert '\n  push:\n    tags:\n      - "v*"\n' in workflow
	assert "\n  workflow_dispatch:\n" in workflow
	effective_index = "${{ github.event_name == 'push' && 'pypi' || inputs.destination }}"
	assert f"group: release-${{{{ github.ref }}}}-{effective_index}" in workflow
	assert "cancel-in-progress: false" in workflow
	assert "description: Package index\n" in workflow
	assert "default: test-pypi\n" in workflow
	validation, publish = workflow.split("\n  publish:\n")
	assert "destination: ${{ steps.release.outputs.destination }}" in validation
	assert "RELEASE_REF: ${{ github.ref }}" in validation
	assert "RELEASE_EVENT: ${{ github.event_name }}" in validation
	assert "RELEASE_DESTINATION: ${{ inputs.destination }}" in validation
	assert 'python3 tests/check_release.py "$RELEASE_REF"' in validation
	assert '--event "$RELEASE_EVENT" --destination "$RELEASE_DESTINATION" >> "$GITHUB_OUTPUT"' in validation
	assert "id-token:" not in validation
	assert "permissions: {}" in validation
	assert "needs: validate-build" in publish
	assert "inputs.destination" not in publish
	assert (
		"if: needs.validate-build.outputs.destination == 'pypi' || "
		"needs.validate-build.outputs.destination == 'test-pypi'\n"
	) in publish
	assert "name: ${{ needs.validate-build.outputs.destination }}" in publish
	for field, production, test_index in (
		("url", "https://pypi.org/p/coaxi", "https://test.pypi.org/p/coaxi"),
		("repository-url", "https://upload.pypi.org/legacy/", "https://test.pypi.org/legacy/"),
	):
		assert (
			f"{field}: ${{{{ needs.validate-build.outputs.destination == 'pypi' && "
			f"'{production}' || '{test_index}' }}}}\n"
		) in publish
	assert "      id-token: write\n" in publish
	assert "skip-existing: false" in publish


def test_distribution_pair(tmp_path: Path) -> None:
	"""Only the exact release pair is accepted; uv's non-uploaded marker is allowed."""
	wheel = tmp_path / "coaxi-1.0.0-py3-none-any.whl"
	source = tmp_path / "coaxi-1.0.0.tar.gz"
	wheel.touch()
	source.touch()
	(tmp_path / ".gitignore").write_text("*\n", encoding="utf-8")
	assert distribution_paths(tmp_path, "1.0.0") == (wheel, source)


@pytest.mark.parametrize(
	"names",
	[
		[],
		["coaxi-1.0.0.tar.gz"],
		["coaxi-1.0.0-py3-none-any.whl"],
		["coaxi-0.1.0-py3-none-any.whl", "coaxi-1.0.0.tar.gz"],
		["coaxi-1.0.0-py3-none-any.whl", "coaxi-1.0.0.tar.gz", "coaxi-0.1.0.tar.gz"],
		["coaxi-1.0.0-py3-none-any.whl", "coaxi-1.0.0.tar.gz", ".unexpected"],
	],
)
def test_wrong_distribution_pair(tmp_path: Path, names: list[str]) -> None:
	"""Missing, stale and unexpected files cannot reach the upload artefact."""
	for name in names:
		(tmp_path / name).touch()
	with pytest.raises(ValueError, match="Expected only"):
		distribution_paths(tmp_path, "1.0.0")


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_distribution_must_be_ordinary_file(tmp_path: Path, kind: str) -> None:
	"""Expected filenames cannot conceal directories or linked external files."""
	wheel = tmp_path / "coaxi-1.0.0-py3-none-any.whl"
	source = tmp_path / "coaxi-1.0.0.tar.gz"
	source.touch()
	if kind == "symlink":
		wheel.symlink_to(source)
	else:
		wheel.mkdir()
	with pytest.raises(ValueError, match="ordinary file"):
		distribution_paths(tmp_path, "1.0.0")


def test_distribution_cli_refuses_optimisation(tmp_path: Path) -> None:
	"""The standalone validator cannot silently skip assertions under optimised Python."""
	result = subprocess.run(
		[sys.executable, "-O", "-m", "tests.test_distribution", "--dist", str(tmp_path)],
		cwd=Path(__file__).resolve().parents[1],
		check=False,
		capture_output=True,
		text=True,
		timeout=30,
	)
	assert result.returncode != 0
	assert "Distribution validation requires Python assertions" in result.stderr

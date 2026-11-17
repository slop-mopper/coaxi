# test_release.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Regression tests for build-free release guards; no package-index access or uploads."""

import sys
import subprocess
from pathlib import Path

import pytest

from tests.check_release import check_release_ref
from tests.check_release import distribution_paths


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

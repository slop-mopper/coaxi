# check_release.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Build-free release guards, also runnable before CI installs project dependencies."""

import argparse
import tomllib
from pathlib import Path


def check_release_ref(root: Path, ref: str) -> str:
	"""Require ref to be the exact v<project-version> tag; check the root's locked version too."""
	project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
	version = project["version"]
	if project["name"] != "coaxi" or not isinstance(version, str) or not version:
		raise ValueError("Expected coaxi with a non-empty static project version")
	if ref != f"refs/tags/v{version}":
		raise ValueError(f"Release must run on refs/tags/v{version}; received {ref!r}")
	lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
	locked_versions = [package["version"] for package in lock["package"] if package["name"] == "coaxi"]
	if locked_versions != [version]:
		raise ValueError("The coaxi version in uv.lock must match pyproject.toml")
	return version


def distribution_paths(dist: Path, version: str) -> tuple[Path, Path]:
	"""Return the wheel and sdist for version in dist, rejecting missing, stale or linked files."""
	wheel = dist / f"coaxi-{version}-py3-none-any.whl"
	source = dist / f"coaxi-{version}.tar.gz"
	expected = {wheel.name, source.name}
	# uv creates this marker alongside the distributions; it is never uploaded.
	entries = {path.name for path in dist.iterdir() if path.name != ".gitignore"}
	if entries != expected:
		raise ValueError(f"Expected only {sorted(expected)} in {dist}; found {sorted(entries)}")
	for path in (wheel, source):
		if path.is_symlink() or not path.is_file():
			raise ValueError(f"Release distribution must be an ordinary file: {path}")
	return wheel, source


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("ref", help="Full triggering Git ref, for example refs/tags/v1.0.0")
	arguments = parser.parse_args()
	print(check_release_ref(Path(__file__).resolve().parents[1], arguments.ref))

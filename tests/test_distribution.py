# test_distribution.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Build and inspect distributions, then exercise the installed wheel without checkout imports."""

import sys
import argparse
import tarfile
import tomllib
import zipfile
import subprocess
from pathlib import Path
from email.parser import Parser
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from tests.check_release import distribution_paths


def test_distribution(tmp_path: Path) -> None:
	"""Verify source/wheel contents, isolated runtime installation and the installed example."""
	root = Path(__file__).resolve().parents[1]
	dist = tmp_path / "dist"
	# uv's default builds the wheel from the sdist, rather than the live checkout.
	subprocess.run(["uv", "build", "--no-sources", "--out-dir", str(dist)], cwd=root, check=True, timeout=120)
	check_distribution(dist, tmp_path)


def check_distribution(dist: Path, tmp_path: Path) -> None:
	"""Inspect the already-built dist pair and exercise its installed wheel using tmp_path for scratch."""
	if not __debug__:
		raise RuntimeError("Distribution validation requires Python assertions; do not use -O or PYTHONOPTIMIZE")
	root = Path(__file__).resolve().parents[1]
	metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
	version = metadata["project"]["version"]
	licence = (root / "LICENSE.txt").read_bytes()
	package_files = {
		"__init__.py",
		"_binding.py",
		"_bits.py",
		"_numeric.py",
		"_payload.py",
		"_sideband.py",
		"_stream.py",
		"py.typed",
	}
	wheel_path, source_path = distribution_paths(dist, version)
	with zipfile.ZipFile(wheel_path) as wheel:
		files = set(wheel.namelist())
		assert len(files) == len(wheel.namelist()), "duplicate wheel archive members"
		dist_info = f"coaxi-{version}.dist-info"
		wheel_metadata = Parser().parsestr(wheel.read(f"{dist_info}/METADATA").decode("utf-8"))
		assert wheel_metadata["Name"] == "coaxi"
		assert wheel_metadata["Version"] == version
		assert wheel_metadata["Requires-Python"] == ">=3.13"
		assert {value.replace(" ", "") for value in wheel_metadata.get_all("Requires-Dist", [])} == {
			value.replace(" ", "") for value in metadata["project"]["dependencies"]
		}
		assert wheel_metadata["License-Expression"] == "CC0-1.0"
		assert wheel_metadata.get_all("License-File") == ["LICENSE.txt"]
		assert wheel.read(f"{dist_info}/licenses/LICENSE.txt") == licence
		assert wheel_metadata.get_payload() == (root / "README.md").read_text(encoding="utf-8")
		assert {name for name in files if name.startswith("coaxi/")} == {f"coaxi/{name}" for name in package_files}
		assert not any(name.startswith("cocotbext/") or "__pycache__" in name for name in files)
		for name in package_files:
			assert wheel.read(f"coaxi/{name}") == (root / "src" / "coaxi" / name).read_bytes()
		assert wheel.read("coaxi/py.typed") == b""
	with tarfile.open(source_path) as source:
		prefix = f"coaxi-{version}"
		source_files = set(source.getnames())
		assert len(source_files) == len(source.getnames()), "duplicate sdist archive members"
		member = source.extractfile(f"{prefix}/PKG-INFO")
		assert member is not None
		with member:
			source_metadata = Parser().parsestr(member.read().decode("utf-8"))
		for header in ("Name", "Version", "Requires-Python", "License-Expression", "License-File", "Requires-Dist"):
			assert source_metadata.get_all(header) == wheel_metadata.get_all(header), header
		member = source.extractfile(f"{prefix}/pyproject.toml")
		assert member is not None
		with member:
			assert member.read() == (root / "pyproject.toml").read_bytes()
		for path in [
			"pyproject.toml",
			"README.md",
			"ARCHITECTURE.md",
			"AGENTS.md",
			"uv.lock",
			"tests/test_distribution.py",
			"tests/check_release.py",
			"tests/__init__.py",
			"tests/test_release.py",
			"tests/test_documentation.py",
			"docs/conf.py",
			"docs/index.md",
			"RELEASING.md",
			"tests/test_simulation.py",
			"tests/test_typing.py",
			"tests/test_values.py",
			"tests/test_numeric.py",
			"tests/test_numeric_vhdl.py",
			"tests/test_numeric_errors.py",
			"tests/test_numeric_documentation.py",
			"tests/test_numeric_simulation.py",
			"tests/numeric_cases.py",
			"tests/hdl/numeric_dut.vhd",
			"tests/stream_cases.py",
			"tests/full_rate_cases.py",
			"tests/frame_cases.py",
			"tests/handle_cases.py",
			"tests/sideband_cases.py",
			"tests/omission_cases.py",
			"tests/reset_pin_cases.py",
			"tests/audit_cases.py",
			"tests/test_validation.py",
			"tests/run_coverage.py",
			"tests/hdl/stream_dut.vhd",
			"examples/stream_loopback.py",
			*[f"src/coaxi/{name}" for name in package_files],
		]:
			assert f"{prefix}/{path}" in source_files
		# Ship all guide/reference sources, but not generated HTML or doctrees.
		docs = root / "docs"
		doc_paths = [docs / "conf.py", docs / "_static" / "code.css", *sorted(docs.rglob("*.md"))]
		for doc_path in doc_paths:
			relative = doc_path.relative_to(root)
			if "_build" in relative.parts:
				continue
			member = source.extractfile(f"{prefix}/{relative.as_posix()}")
			assert member is not None, relative
			with member:
				assert member.read() == doc_path.read_bytes(), relative
		assert not any("/docs/_build/" in name for name in source_files)
		member = source.extractfile(f"{prefix}/LICENSE.txt")
		assert member is not None
		with member:
			assert member.read() == licence
		fixture = tmp_path / "fixture"
		fixture.mkdir()
		for relative in ("examples/stream_loopback.py", "tests/hdl/stream_dut.vhd"):
			member = source.extractfile(f"{prefix}/{relative}")
			assert member is not None
			with member:
				(fixture / Path(relative).name).write_bytes(member.read())

	# Install only the wheel's runtime graph at locked versions. The consumer
	# must not inherit development packages; uv may download uncached wheels.
	consumer = tmp_path / "consumer"
	subprocess.run(["uv", "venv", "--python", sys.executable, str(consumer)], check=True, timeout=30)
	python = consumer / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
	lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
	constraints = tmp_path / "constraints.txt"
	constraints.write_text(
		"".join(
			f"{package['name']}=={package['version']}\n" for package in lock["package"] if package["name"] != "coaxi"
		),
		encoding="utf-8",
	)
	subprocess.run(
		[
			"uv",
			"pip",
			"install",
			"--python",
			str(python),
			"--constraint",
			str(constraints),
			str(wheel_path),
		],
		check=True,
		timeout=120,
	)
	# -I excludes cwd/PYTHONPATH; neither the checkout nor its .venv supplies imports.
	smoke = """
import inspect
import sys
from pathlib import Path
from importlib.metadata import distribution, PackageNotFoundError

import coaxi
from cocotb.types import LogicArray

consumer = Path(sys.argv[1]).resolve()
assert Path(sys.prefix).resolve() == consumer
assert Path(coaxi.__file__).is_relative_to(consumer), coaxi.__file__
assert Path(distribution("coaxi").locate_file("")).resolve().is_relative_to(consumer)
assert distribution("coaxi").version == sys.argv[2]
for development_package in ("pyrefly", "ruff", "coverage", "sphinx", "myst-parser", "furo"):
	try:
		distribution(development_package)
	except PackageNotFoundError:
		pass
	else:
		raise AssertionError(f"consumer inherited {development_package}")
assert coaxi.__all__
for name in coaxi.__all__:
	assert getattr(coaxi, name) is not None, name
for name, module in list(sys.modules.items()):
	if name == "coaxi" or name.startswith("coaxi."):
		assert Path(module.__file__).is_relative_to(consumer), (name, module.__file__)
assert coaxi.to_unsigned(LogicArray("1010")) == 10
assert coaxi.to_signed(LogicArray("1111")) == -1
u = coaxi.Unsigned.from_int(255, width=8)
assert (u + 1).to_int() == 0
assert (u * 2).width == 16 and (u * 2).to_int() == 510
assert coaxi.Signed(u).to_int() == -1
assert str(coaxi.Signed(u).to_logic_array()) == "11111111"
try:
	coaxi.Signed(LogicArray("X001")).to_int()
except ValueError:
	pass
else:
	raise AssertionError("unresolved numeric value was converted")
import warnings
with warnings.catch_warnings(record=True) as caught:
	warnings.simplefilter("always", coaxi.NumericStdWarning)
	assert not (coaxi.Signed(LogicArray("X001")) == 0)
assert len(caught) == 1 and caught[0].category is coaxi.NumericStdWarning
assert coaxi.AxiStreamSidebands().keep is None
assert coaxi.AxiStreamTransfer(42, None).user is None
try:
	coaxi.to_unsigned(LogicArray("X001"))
except ValueError:
	pass
else:
	raise AssertionError("unresolved payload was converted")
assert inspect.iscoroutinefunction(coaxi.AxiStreamSource.send_frame)
assert inspect.iscoroutinefunction(coaxi.AxiStreamSink.recv_frame)
assert inspect.iscoroutinefunction(coaxi.AxiStreamSink.close)
assert inspect.iscoroutinefunction(coaxi.AxiStreamSource.close)
for endpoint in (coaxi.AxiStreamSource, coaxi.AxiStreamSink):
	assert inspect.iscoroutinefunction(endpoint.initialise)
	assert not hasattr(endpoint, "reset")
	assert inspect.signature(endpoint).parameters["reset"].default is None
	assert inspect.signature(endpoint).parameters["reset_active_high"].default is False
assert inspect.signature(coaxi.AxiStreamSink).parameters["buffer_capacity"].default is None
assert inspect.signature(coaxi.AxiStreamSink.recv_frame).parameters["max_transfers"].default is None
"""
	subprocess.run(
		[str(python), "-I", "-c", smoke, str(consumer), version],
		cwd=tmp_path,
		check=True,
		timeout=30,
	)

	# Check import origin inside the simulator too, using the sdist's example
	# and HDL fixture rather than anything on the checkout's module path.
	example = fixture / "stream_loopback.py"
	with example.open("a", encoding="utf-8") as module:
		module.write(
			"\nimport sys\nfrom pathlib import Path\nimport coaxi\n"
			f"_expected_consumer = Path({str(consumer)!r}).resolve()\n"
			"assert Path(sys.prefix).resolve() == _expected_consumer, sys.prefix\n"
			"assert Path(coaxi.__file__).is_relative_to(_expected_consumer), coaxi.__file__\n"
		)
	simulate = """
import os
import sys
from pathlib import Path
from cocotb_tools.runner import get_runner

fixture = Path(sys.argv[1])
# This consumer intentionally has runtime dependencies only. Coverage of the
# checkout is collected separately, not injected into this installation.
os.environ["COCOTB_USER_COVERAGE"] = "0"
runner = get_runner("nvc")
runner.build(
	sources=[fixture / "stream_dut.vhd"],
	hdl_toplevel="stream_dut",
	build_args=["--std=2008"],
	build_dir=fixture / "sim_build",
)
for mode in ("0", "1"):
	# The runner merges os.environ over extra_env; set the requested values here.
	os.environ["COCOTB_TRUST_INERTIAL_WRITES"] = mode
	os.environ["COCOTB_RESOLVE_X"] = "ZEROS"
	runner.test(
		hdl_toplevel="stream_dut",
		test_module="stream_loopback",
		test_dir=fixture,
		build_dir=fixture / "sim_build",
		results_xml=str(fixture / f"results-{mode}.xml"),
	)
"""
	subprocess.run([str(python), "-I", "-c", simulate, str(fixture)], cwd=tmp_path, check=True, timeout=60)
	# A simulator can exit successfully without producing results. Require
	# both completed runs, rather than trusting the runner's process status.
	for mode in ("0", "1"):
		results = ElementTree.parse(fixture / f"results-{mode}.xml").findall(".//testcase")
		assert len(results) == 1
		assert results[0].get("name") == "stream_loopback"
		for status in ("failure", "error", "skipped"):
			assert results[0].find(status) is None, ElementTree.tostring(results[0], encoding="unicode")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Validate already-built release files without rebuilding them.")
	parser.add_argument(
		"--dist", required=True, type=Path, help="Directory containing the exact release sdist and wheel"
	)
	arguments = parser.parse_args()
	with TemporaryDirectory(prefix="coaxi-release-") as scratch:
		check_distribution(arguments.dist.resolve(), Path(scratch))

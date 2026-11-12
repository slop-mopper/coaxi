# test_distribution.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Build and inspect distributions, then exercise the installed wheel without checkout imports."""

import sys
import tarfile
import tomllib
import zipfile
import subprocess
from pathlib import Path
from email.parser import Parser
from xml.etree import ElementTree


def test_distribution(tmp_path: Path) -> None:
	"""Verify source/wheel contents, isolated runtime installation and the installed example."""
	root = Path(__file__).resolve().parents[1]
	dist = tmp_path / "dist"
	# uv's default builds the wheel from the sdist, rather than the live checkout.
	subprocess.run(["uv", "build", "--out-dir", str(dist)], cwd=root, check=True, timeout=120)
	metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
	version = metadata["project"]["version"]
	licence = (root / "LICENSE.txt").read_bytes()
	package_files = {"__init__.py", "_binding.py", "_payload.py", "_sideband.py", "_stream.py", "py.typed"}
	wheel_path = dist / f"coaxi-{version}-py3-none-any.whl"
	with zipfile.ZipFile(wheel_path) as wheel:
		files = set(wheel.namelist())
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
	with tarfile.open(dist / f"coaxi-{version}.tar.gz") as source:
		prefix = f"coaxi-{version}"
		source_files = set(source.getnames())
		for path in [
			"pyproject.toml",
			"README.md",
			"ARCHITECTURE.md",
			"AGENTS.md",
			"uv.lock",
			"tests/test_distribution.py",
			"tests/test_simulation.py",
			"tests/test_typing.py",
			"tests/test_values.py",
			"tests/stream_cases.py",
			"tests/full_rate_cases.py",
			"tests/frame_cases.py",
			"tests/handle_cases.py",
			"tests/sideband_cases.py",
			"tests/omission_cases.py",
			"tests/reset_pin_cases.py",
			"tests/hdl/stream_dut.vhd",
			"examples/stream_loopback.py",
			*[f"src/coaxi/{name}" for name in package_files],
		]:
			assert f"{prefix}/{path}" in source_files
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
for development_package in ("pyrefly", "ruff"):
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
		[str(python), "-I", "-c", smoke, str(consumer)],
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

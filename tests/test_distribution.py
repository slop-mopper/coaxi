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


def test_distribution(tmp_path: Path) -> None:
	"""Verify the source/wheel contents and public imports using the current uv environment."""
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
			"tests/hdl/stream_dut.vhd",
			"examples/stream_loopback.py",
			*[f"src/coaxi/{name}" for name in package_files],
		]:
			assert f"{prefix}/{path}" in source_files
		member = source.extractfile(f"{prefix}/LICENSE.txt")
		assert member is not None
		with member:
			assert member.read() == licence
	installed = tmp_path / "installed"
	subprocess.run(
		["uv", "pip", "install", "--python", sys.executable, "--no-deps", "--target", str(installed), str(wheel_path)],
		cwd=root,
		check=True,
		timeout=120,
	)
	# -I excludes cwd/PYTHONPATH; place the installed wheel ahead of the editable install.
	# Runtime dependencies still come from the uv-managed project-local environment.
	smoke = """
import inspect
import sys
from pathlib import Path
from importlib.metadata import distribution

sys.path.insert(0, sys.argv[1])
import coaxi
from cocotb.types import LogicArray

assert Path(coaxi.__file__).is_relative_to(sys.argv[1]), coaxi.__file__
assert Path(distribution("coaxi").locate_file("")).resolve() == Path(sys.argv[1]).resolve()
assert coaxi.__all__
for name in coaxi.__all__:
	assert getattr(coaxi, name) is not None, name
for name, module in list(sys.modules.items()):
	if name == "coaxi" or name.startswith("coaxi."):
		assert Path(module.__file__).is_relative_to(sys.argv[1]), (name, module.__file__)
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
assert inspect.signature(coaxi.AxiStreamSink).parameters["buffer_capacity"].default is None
assert inspect.signature(coaxi.AxiStreamSink.recv_frame).parameters["max_transfers"].default is None
"""
	subprocess.run(
		[sys.executable, "-I", "-c", smoke, str(installed)],
		cwd=tmp_path,
		check=True,
		timeout=30,
	)

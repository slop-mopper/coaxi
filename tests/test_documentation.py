# test_documentation.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check reference signatures, guide snippets, and Pages deployment permissions."""

import ast
import inspect
import re
from pathlib import Path
from runpy import run_path
from types import UnionType
from functools import reduce
from operator import or_
from typing import Any, Self, TypeAliasType, get_args, get_origin
from collections.abc import Iterator, Mapping, Sequence

import coaxi
from cocotb.types import Logic, LogicArray
from cocotb.handle import HierarchyObject, LogicArrayObject, LogicObject, SimHandleBase


def _reference_entries() -> Iterator[tuple[Path, str, str, str]]:
	"""Read the explicit Python-domain declarations from the reference."""
	api = Path(__file__).resolve().parents[1] / "docs" / "api"
	pattern = r"^```\{py:(class|exception|method|function|type)\} ([^\n]+)\n(.*?)^```"
	for path in sorted(api.glob("*.md")):
		for match in re.finditer(pattern, path.read_text(encoding="utf-8"), re.MULTILINE | re.DOTALL):
			yield path, *match.groups()


def _reference_namespace(owner: Any) -> dict[str, Any]:
	"""Use the class's own type variable when evaluating its documented signature."""
	namespace = {
		**vars(coaxi),
		"Self": Self,
		"Sequence": Sequence,
		"Mapping": Mapping,
		"Logic": Logic,
		"LogicArray": LogicArray,
		"HierarchyObject": HierarchyObject,
		"LogicObject": LogicObject,
		"LogicArrayObject": LogicArrayObject,
		"SimHandleBase": SimHandleBase,
	}
	type_parameters = getattr(owner, "__type_params__", ())
	if type_parameters:
		namespace["T"] = type_parameters[0]
	return namespace


def _public_annotation(annotation: Any) -> Any:
	"""Expand private control aliases; public aliases remain named in the reference."""
	if isinstance(annotation, TypeAliasType) and annotation.__name__.startswith("_"):
		return _public_annotation(annotation.__value__)
	if get_origin(annotation) is UnionType:
		return reduce(or_, (_public_annotation(part) for part in get_args(annotation)))
	return annotation


def _documented_signature(text: str, namespace: dict[str, Any]) -> inspect.Signature:
	"""Parse the declaration without executing a function body."""
	node = ast.parse(f"def _documented{text}:\n\tpass\n").body[0]
	assert isinstance(node, ast.FunctionDef)
	parameters: list[inspect.Parameter] = []

	def add(argument: ast.arg, kind: inspect._ParameterKind, default: ast.expr | None = None) -> None:
		assert argument.annotation is not None
		parameters.append(
			inspect.Parameter(
				argument.arg,
				kind,
				default=inspect.Parameter.empty if default is None else ast.literal_eval(default),
				annotation=eval(ast.unparse(argument.annotation), namespace),
			)
		)

	positional = node.args.posonlyargs + node.args.args
	defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
	for index, (argument, default) in enumerate(zip(positional, defaults, strict=True)):
		kind = (
			inspect.Parameter.POSITIONAL_ONLY
			if index < len(node.args.posonlyargs)
			else inspect.Parameter.POSITIONAL_OR_KEYWORD
		)
		add(argument, kind, default)
	if node.args.vararg is not None:
		add(node.args.vararg, inspect.Parameter.VAR_POSITIONAL)
	for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
		add(argument, inspect.Parameter.KEYWORD_ONLY, default)
	if node.args.kwarg is not None:
		add(node.args.kwarg, inspect.Parameter.VAR_KEYWORD)
	assert node.returns is not None
	return inspect.Signature(parameters, return_annotation=eval(ast.unparse(node.returns), namespace))


def test_reference_matches_public_api() -> None:
	"""Check export coverage, separate class pages, and typed parameter/return contracts."""
	config = run_path(str(Path(__file__).resolve().parents[1] / "docs" / "conf.py"))
	assert "fieldlist" in config["myst_enable_extensions"], "parameter fields must render as structured lists"
	exports: set[str] = set()
	methods: dict[str, set[str]] = {}
	class_pages: list[Path] = []
	for path, kind, declaration, body in _reference_entries():
		name = re.split(r"[\[(]", declaration, maxsplit=1)[0]
		owner_name, _, member_name = name.partition(".")
		owner = getattr(coaxi, owner_name)
		namespace = _reference_namespace(owner)
		if kind == "method":
			actual = getattr(owner, member_name)
			methods.setdefault(owner_name, set()).add(member_name)
		else:
			exports.add(name)
			actual = owner
		if kind in ("class", "exception"):
			class_pages.append(path)
		if kind == "type":
			definition = re.search(r"^:annotation: = (.+)$", body, re.MULTILINE)
			assert definition is not None, name
			assert eval(definition[1], namespace) == owner.__value__, name
			continue
		if "(" not in declaration:
			assert kind == "class" and name == "Payload"
			continue  # A structural protocol has no public constructor.
		signature_text = declaration[declaration.index("(") :]
		documented = _documented_signature(signature_text, namespace)
		parameters = documented.parameters
		assert set(re.findall(r"^:param (\w+): .+", body, re.MULTILINE)) == set(parameters), name
		field_types = dict(re.findall(r"^:type (\w+): (.+)$", body, re.MULTILINE))
		assert set(field_types) == set(parameters), name
		for parameter_name, parameter in parameters.items():
			assert parameter.annotation is not inspect.Parameter.empty, (name, parameter_name)
			assert eval(field_types[parameter_name], namespace) == parameter.annotation, (name, parameter_name)
		result = re.search(r"^:rtype: (.+)$", body, re.MULTILINE)
		assert result is not None and ":returns: " in body, name
		assert documented.return_annotation is not inspect.Signature.empty, name
		assert eval(result[1], namespace) == documented.return_annotation, name
		if kind == "exception":
			assert issubclass(owner, Exception)
			assert list(parameters) == ["args"]  # BaseException has no inspectable signature.
		else:
			implemented = inspect.signature(actual)
			implemented = implemented.replace(
				parameters=[
					p.replace(annotation=_public_annotation(p.annotation))
					for p in implemented.parameters.values()
					if p.name not in ("self", "cls")
				],
				return_annotation=_public_annotation(implemented.return_annotation),
			)
			assert documented == implemented, (name, documented, implemented)
			assert (":async:" in body) == inspect.iscoroutinefunction(actual), name
	assert exports == set(coaxi.__all__)
	assert len(class_pages) == len(set(class_pages)), "each public class needs its own page"
	for name in exports:
		owner = getattr(coaxi, name)
		if not inspect.isclass(owner) or issubclass(owner, Exception):
			continue
		public_methods = {
			member
			for member, value in inspect.getmembers(owner)
			if not member.startswith("_") and (inspect.isfunction(value) or inspect.ismethod(value))
		}
		assert methods.get(name, set()) == public_methods, name


def test_guide_python_syntax_and_tested_tutorial() -> None:
	"""Parse guide snippets and keep the tutorial attached to the simulator-tested source."""
	docs = Path(__file__).resolve().parents[1] / "docs"
	for path in docs.rglob("*.md"):
		if "_build" in path.parts:
			continue
		text = path.read_text(encoding="utf-8")
		assert "SPDX-License-Identifier:" not in text, path
		for code in re.findall(r"^```python\n(.*?)^```", text, re.MULTILINE | re.DOTALL):
			ast.parse(code, filename=str(path))
	tutorial = (docs / "getting-started.md").read_text(encoding="utf-8")
	assert "```{literalinclude} ../examples/stream_loopback.py\n" in tutorial
	assert ":lines: 8-" in tutorial
	assert "uv run pytest -q tests/test_simulation.py -k example" in tutorial


def test_pages_workflow_permissions() -> None:
	"""Pull requests build without deployment credentials; only master can publish."""
	root = Path(__file__).resolve().parents[1]
	workflow = (root / ".github/workflows/docs.yml").read_text(encoding="utf-8")
	build, deploy = workflow.split("\n  deploy:\n", maxsplit=1)
	assert "\n  pull_request:\n    branches:\n      - master\n" in build
	assert "\n  push:\n    branches:\n      - master\n" in build
	assert "\n  workflow_dispatch:\n" in build
	assert "\npermissions: {}\n" in build
	assert "\n    permissions:\n      contents: read\n" in build
	assert "pages: write" not in build
	assert "id-token: write" not in build
	assert "pull_request_target" not in workflow
	assert "persist-credentials: false" in build
	assert "uv sync --locked --no-dev --group docs" in build
	assert "uv run --locked --no-dev --group docs sphinx-build -M html docs docs/_build -n -W --keep-going" in build
	assert "uv run --locked --no-dev --group docs sphinx-build -M doctest docs docs/_build -n -W --keep-going" in build
	guard = "if: github.ref == 'refs/heads/master' && github.event_name != 'pull_request'"
	upload = build.split("- name: Upload the Pages site\n", maxsplit=1)[1]
	assert guard in upload
	assert "uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9" in upload
	assert "\n          name: github-pages\n          path: docs/_build/html\n" in upload
	assert guard in deploy
	assert "needs: build" in deploy
	assert "\n    permissions:\n      pages: write\n      id-token: write\n" in deploy
	assert "name: github-pages" in deploy
	assert "actions/checkout@" not in deploy
	assert "\n        run:" not in deploy
	assert deploy.count("uses:") == 1
	assert "uses: actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346" in deploy
	assert "\n          artifact_name: github-pages\n" in deploy

# conf.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Build the coaxi guide and typed API reference."""

from importlib.metadata import version as _distribution_version

project = "coaxi"
release = _distribution_version("coaxi")

extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.doctest"]
root_doc = "index"
exclude_patterns = ["_build"]
myst_heading_anchors = 3
myst_enable_extensions = ["fieldlist"]

# External cocotb types are linked on the API index. Keep offline builds usable;
# unresolved coaxi references must still fail the nitpicky build.
nitpick_ignore = [
	("py:class", name)
	for name in ("SimHandleBase", "HierarchyObject", "LogicObject", "LogicArrayObject", "Logic", "LogicArray", "T")
]

html_theme = "furo"
html_title = project

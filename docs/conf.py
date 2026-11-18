# conf.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Build the coaxi guide and typed API reference."""

from importlib.metadata import version as _distribution_version

project = "coaxi"
release = _distribution_version("coaxi")

extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.doctest"]
root_doc = "index"
exclude_patterns = ["_build", "_numeric-methods.md"]
myst_heading_anchors = 3
myst_enable_extensions = ["fieldlist"]
python_maximum_signature_line_length = 88
python_trailing_comma_in_multi_line_signatures = True

# External cocotb types are linked on the API index. Keep offline builds usable;
# unresolved coaxi references must still fail the nitpicky build.
nitpick_ignore = [
	("py:class", name)
	for name in (
		"SimHandleBase",
		"HierarchyObject",
		"LogicObject",
		"LogicArrayObject",
		"Logic",
		"LogicArray",
		"Range",
		"Self",
		"T",
	)
]

html_theme = "furo"
html_title = project
html_static_path = ["_static"]
html_css_files = ["code.css"]

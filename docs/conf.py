# conf.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Sphinx configuration for the documentation skeleton."""

from importlib.metadata import version as _distribution_version

project = "coaxi"
release = _distribution_version("coaxi")

extensions = ["myst_parser", "sphinx.ext.autodoc"]
root_doc = "index"
exclude_patterns = ["_build"]

html_theme = "furo"
html_title = project

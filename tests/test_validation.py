# test_validation.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Fail invalid dynamically constructed bindings at the public boundary."""

from typing import Any, cast

import pytest

from coaxi import AxiStreamBus, SignalBindingError


@pytest.mark.parametrize("valid", [None, "unresolved_name", 0])
def test_direct_binding_requires_valid_handle(valid: object) -> None:
	"""Report the mandatory role, rather than a later AttributeError in an endpoint."""
	with pytest.raises(SignalBindingError, match="valid"):
		AxiStreamBus(data=None, valid=cast(Any, valid), ready=None)

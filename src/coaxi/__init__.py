# __init__.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""coaxi: AXI-Stream helpers with independent signal binding and structured payloads."""

from ._binding import AxiStreamBus, Signal, SignalBindingError
from ._payload import HandlePayload, Payload, PayloadValue, to_signed, to_unsigned
from ._stream import (
	AxiStreamSink,
	AxiStreamSource,
	AxiStreamTransfer,
	EndpointStateError,
	ProtocolValueError,
	TransferReset,
)

__all__ = [
	"AxiStreamBus",
	"AxiStreamSink",
	"AxiStreamSource",
	"AxiStreamTransfer",
	"EndpointStateError",
	"HandlePayload",
	"Payload",
	"PayloadValue",
	"ProtocolValueError",
	"Signal",
	"SignalBindingError",
	"TransferReset",
	"to_signed",
	"to_unsigned",
]

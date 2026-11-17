# Payloads and conversion

The default adapter, {py:class}`coaxi.HandlePayload`, supports scalar logic,
logic vectors, and named containers such as VHDL records. It does not flatten
records or convert received values to integers. Handshake and framing logic
do not depend on the payload representation.

## Vectors and records

Unsigned integers can be sent directly. On a 16-bit unframed vector bus,
signed values use an explicit two's-complement vector:

```python
from cocotb.types import LogicArray

await source.send(42)  # Unframed, data-bearing bus.
await source.send(LogicArray.from_signed(-12, 16))
```

Record values use mappings with the HDL field names. Every field must be
present, with no additional keys. Nested records use nested mappings.
For this VHDL record:

```{literalinclude} ../tests/hdl/stream_dut.vhd
:language: vhdl
:start-at: type IQ_t is record
:end-at: end record;
:dedent: 1
```

a source bound to a framed IQ-record bus can send:

```python
samples = [
	{"i": LogicArray.from_signed(-12, 16), "q": LogicArray.from_signed(34, 16)},
	{"i": LogicArray.from_signed(56, 16), "q": LogicArray.from_signed(-78, 16)},
]
await source.send_frame(samples)
```

Received scalars are `Logic`, vectors are `LogicArray`, and containers are
new dictionaries of field snapshots. The default adapter validates the whole
payload before writing any leaf. Integer inputs must be unsigned and fit the
HDL width; unsupported leaf types fail when the adapter is constructed.
Errors from leaf conversion include the HDL path.

Do not mutate payload values or contained logic arrays while a send is active.
The source does not copy a complete frame before sending it.

## Meta-values

Payloads and raw sidebands can contain HDL meta-values for propagation and
fault-injection tests. Reading them does not silently resolve `X`, `U`, or `Z`.
With the default adapter, source initialisation and reset assertion clear
owned payload leaves to zero. Custom adapters define their own recovery
values through `clear()`. Sink initialisation does not clear incoming data.

Numeric conversion is explicit:

```{doctest}
>>> from cocotb.types import LogicArray
>>> from coaxi import to_signed, to_unsigned
>>> bits = LogicArray("11111111")
>>> to_unsigned(bits), to_signed(bits)
(255, -1)
>>> to_unsigned(LogicArray("00LH"))
1
>>> to_unsigned(LogicArray("00X1"))
Traceback (most recent call last):
...
ValueError: cannot convert unresolved payload 00X1 to an integer
```

The numeric helpers reject unresolved values even when `COCOTB_RESOLVE_X`
would allow cocotb to resolve them. Weak `L` and `H` are resolvable for numeric
conversion. Sampled handshake controls, accepted last, and monitored reset
instead require literal `0` or `1`; weak values also fail there.

## Application-defined types

Implement {py:class}`coaxi.Payload` to use an application value type. The
adapter binds its own handles and provides synchronous `drive()`, `read()`,
and `clear()` methods. They must not yield. Reads must produce independent
snapshots, and clearing must define every owned payload leaf.

Supply the adapter through the endpoint constructor. With `Payload[T]`,
the source accepts `T` and the sink produces `AxiStreamTransfer[T]`.
Without an adapter, endpoint typing is `PayloadValue | None`; `None` is only
accepted on a data-less bus. A data-less bus rejects custom adapters.

Validate before writing where possible. A custom adapter can partially
write before raising; local recovery cannot undo those writes or accepted
traffic. The sink calls only `read()`, never `clear()` or `drive()`, because
it does not own the incoming payload.

Custom payloads do not relax the keep/strb layout requirements. Last, user,
id, and dest remain independent of payload shape.

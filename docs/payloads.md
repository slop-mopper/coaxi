# Payloads and conversion

{py:class}`coaxi.HandlePayload` is the default adapter. It reads scalar signals
as `Logic`, vectors as `LogicArray`, and records as dictionaries keyed by
field name.

## Vectors and records

For an unframed vector bus, send a non-negative integer that fits the signal.
For a negative value, supply its two's-complement bits:

```python
from cocotb.types import LogicArray

await source.send(42)
await source.send(LogicArray.from_signed(-12, 16))
```

Each mapping key must match an HDL field name. Use nested mappings for nested
records. For the following VHDL record, pass a mapping with `i` and `q`:

```{literalinclude} ../examples/iq_loopback.vhd
:language: vhdl
:start-at: type iq_t is record
:end-at: end record;
:dedent: 1
```

```python
samples = [
	{"i": LogicArray.from_signed(-12, 16), "q": LogicArray.from_signed(34, 16)},
	{"i": LogicArray.from_signed(56, 16), "q": LogicArray.from_signed(-78, 16)},
]
await source.send_frame(samples)
```

`HandlePayload` checks all fields before writing any of them. It rejects
unsupported handle types at construction and includes the HDL path in
conversion errors. Keep the payload unchanged until the send returns;
`send_frame()` reads each entry when it prepares that beat.

## Meta-values

Payload and sideband snapshots keep logic values such as `X`, `U`, and `Z`.
The integer conversion helpers treat `L` as zero and `H` as one. They reject
unresolved bits even if `COCOTB_RESOLVE_X` is set to resolve them:

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

Sampled handshake controls, accepted `last`, and monitored reset require
literal `0` or `1`.

## Numeric values

{py:class}`coaxi.Signed` and {py:class}`coaxi.Unsigned` use VHDL width rules.
Export a `LogicArray` before passing either type to the default adapter:

```python
from coaxi import Signed

sample = Signed.from_int(-12, width=16)
await source.send(sample.to_logic_array())
```

To interpret a received `LogicArray` as signed, use `Signed(transfer.data)`.
See [Numeric values](numeric.md) for widths and operators.

## Application-defined types

Use a {py:class}`coaxi.Payload` adapter when the testbench works with a Python
type such as a dataclass. Each adapter needs a bound `data` signal.
[IQ samples as a dataclass](examples/custom-payload.md) includes the VHDL,
bus bindings, and a test that sends and receives a frame.

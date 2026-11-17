# Payloads and conversion

The default adapter, {py:class}`coaxi.HandlePayload`, supports scalar logic,
logic vectors, and named containers such as VHDL records. Received values
use cocotb logic types and field mappings. Adapters provide payload access;
endpoints handle handshakes and framing.

## Vectors and records

Unsigned integers can be sent directly. On a 16-bit unframed vector bus,
signed values use an explicit two's-complement vector:

```python
from cocotb.types import LogicArray

await source.send(42)  # Unframed, data-bearing bus.
await source.send(LogicArray.from_signed(-12, 16))
```

Record values use mappings whose keys match all HDL field names.
Nested records use nested mappings.
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

Keep payload values and contained logic arrays unchanged while a send is active.
The source reads each frame entry as it sends it.

## Meta-values

Payloads and raw sidebands can contain HDL meta-values for propagation and
fault-injection tests. Snapshots include `X`, `U`, and `Z` as logic values.
With the default adapter, source initialisation and reset assertion clear
owned payload leaves to zero. Custom adapters define their own recovery
values through `clear()`. The sink owns only `ready`.

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
conversion. Sampled handshake controls, accepted `last`, and monitored reset
require literal `0` or `1`; weak values also fail there.

## Numeric values

{py:class}`coaxi.Signed` and {py:class}`coaxi.Unsigned` provide VHDL-width
arithmetic on snapshots. Convert explicitly when using the default payload adapter:

```python
from coaxi import Signed

sample = Signed.from_int(-12, width=16)
await source.send(sample.to_logic_array())
```

Received vectors can be interpreted with `Signed(transfer.data)` when the
payload is a `LogicArray`. Numeric construction copies the snapshot.
See [Numeric values](numeric.md) for integer overloads, wraparound, and meta-values.

## Application-defined types

Implement {py:class}`coaxi.Payload` to use an application value type. The
adapter binds its own handles and provides synchronous `drive()`, `read()`,
and `clear()` methods. Each method must complete synchronously. Reads must
produce independent snapshots, and clearing must define every owned payload leaf.

Supply the adapter through the endpoint constructor. With `Payload[T]`,
the source accepts `T` and the sink produces `AxiStreamTransfer[T]`.
Without an adapter, endpoint typing is `PayloadValue | None`; `None` is only
accepted on a data-less bus. A data-less bus rejects custom adapters.

Validate before writing where possible. A custom adapter can partially
write before raising; coordinate recovery with the peer.
The sink accesses incoming payloads through `read()`.

With `data` present, `keep` and `strb` require a byte-aligned logic-vector handle.
See [Byte lanes](sidebands.md#byte-lanes) for the lane layout and data-less buses.
`last`, `user`, `id`, and `dest` support any payload shape.

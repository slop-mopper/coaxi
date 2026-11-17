# API reference

Import the public API from `coaxi`. Generic `T` denotes an application payload
type. Default endpoints use `PayloadValue | None`; a custom `Payload[T]`
adapter selects `T`.

```{py:module} coaxi
```

```{toctree}
:maxdepth: 1

bus
source
sink
transfer
sidebands
handle-payload
payload
types
```

## Errors

```{toctree}
:maxdepth: 1

signal-binding-error
protocol-value-error
endpoint-state-error
transfer-reset
```

Conversion and argument checks can also raise `TypeError`, `ValueError`, or
`OverflowError`. Custom adapter failures propagate through the calling operation.
Overflow without `ready` raises `OverflowError`. See [Lifecycle and recovery](../lifecycle.md)
for when explicit initialisation is required.

Cocotb types in signatures are defined in
[`cocotb.handle`](https://docs.cocotb.org/en/stable/library_reference.html#handles)
and [`cocotb.types`](https://docs.cocotb.org/en/stable/library_reference.html#hdl-datatypes).
`Mapping` and `Sequence` refer to `collections.abc`.
The reference includes public operations; dataclass-generated equality and
representation methods and inherited exception methods follow Python behaviour.

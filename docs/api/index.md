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
signed
unsigned
```

## Errors

```{toctree}
:maxdepth: 1

signal-binding-error
protocol-value-error
endpoint-state-error
transfer-reset
numeric-std-warning
```

See [Lifecycle and recovery](../lifecycle.md#errors-and-cancellation) for
which errors require `initialise()` before the next transfer.

Cocotb types in signatures are defined in
[`cocotb.handle`](https://docs.cocotb.org/en/stable/library_reference.html#handles)
and [`cocotb.types`](https://docs.cocotb.org/en/stable/library_reference.html#hdl-datatypes).
`Mapping` and `Sequence` refer to `collections.abc`.

# Payload

```{py:currentmodule} coaxi
```

```{py:class} Payload[T]
```

Adapter for an application payload type `T`. Bind the data handles in the
adapter and pass it to the endpoint's `payload` parameter. An adapter can
inherit from `Payload[T]` or implement its methods without inheritance.

The source calls `drive()` and `clear()`; the sink calls `read()`. These
methods must be synchronous. Validate all fields before writing any of them
to avoid leaving a partial payload on a conversion error.

See [IQ samples as a dataclass](../examples/custom-payload.md) for the
VHDL, adapter, and cocotb test.

## read

```{py:method} Payload.read() -> T

:returns: A snapshot independent of later reads or writes.
```

## drive

```{py:method} Payload.drive(value: T) -> None

:Parameters:
  - `value: T`

    Application payload to convert and write.

:returns: `None`.
```

## clear

```{py:method} Payload.clear() -> None

:returns: `None`, after scheduling a defined value for every payload field the adapter drives.
```

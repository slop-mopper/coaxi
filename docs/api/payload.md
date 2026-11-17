# Payload

```{py:currentmodule} coaxi
```

```{py:class} Payload[T]
```

Structural protocol for synchronous application-defined payload access.
Implement the methods below and supply the adapter to an endpoint; inheritance
is optional.

Bind handles in the implementation. Methods must complete synchronously.
`read()` must return an independent snapshot, and `clear()` must define every
owned leaf. The source uses `drive()` and `clear()`; the sink uses `read()`.
Custom adapters can partially write before raising. Validate before writing
where possible.

## read

```{py:method} Payload.read() -> T

:returns: An independent snapshot in the application's payload representation.
```

## drive

```{py:method} Payload.drive(value: T) -> None

:Parameters:
  - `value: T`

    Application payload to validate and drive synchronously.

:returns: `None`.
```

## clear

```{py:method} Payload.clear() -> None

:returns: `None`, after scheduling a defined value for every owned leaf.
```

Endpoints handle handshakes and framing. See [Payloads and conversion](../payloads.md).

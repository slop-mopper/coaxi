# Payload

```{py:currentmodule} coaxi
```

```{py:class} Payload[T]
```

Structural protocol for synchronous application-defined payload access.
Implement the methods below and supply the adapter to an endpoint; inheritance
is optional. Protocols are not instantiated directly.

Bind handles in the implementation. Methods must not yield, read must return
an independent snapshot, and clear must define every owned leaf.
The source uses drive and clear; the sink uses only read.
Custom adapters can partially write before raising. Validate before writing
where possible.

## read

```{py:method} Payload.read() -> T

:returns: An independent snapshot in the application's payload representation.
:rtype: T
```

## drive

```{py:method} Payload.drive(value: T) -> None

:param value: Application payload to validate and drive without yielding.
:type value: T
:returns: None.
:rtype: None
```

## clear

```{py:method} Payload.clear() -> None

:returns: None, after scheduling a defined value for every owned leaf.
:rtype: None
```

These operations do not implement handshakes or framing. Keep those concerns
in the endpoints. See [Payloads and conversion](../payloads.md).

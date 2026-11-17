# EndpointStateError

```{py:currentmodule} coaxi
```

```{py:exception} EndpointStateError(*args: object) -> None

:param args: Exception arguments, normally a diagnostic message.
:type args: object
:returns: None.
:rtype: None
```

Subclass of `RuntimeError`. Reports an endpoint that needs initialisation,
is in reset or releasing, or already has an active operation.
It also rejects overlapping initialisation and close calls.

Calls are rejected instead of queued. Independent endpoints may run
concurrently.

# EndpointStateError

```{py:currentmodule} coaxi
```

```{py:exception} EndpointStateError(*args: object) -> None

:Parameters:
  - `args: object`

    Exception arguments, normally a diagnostic message.

:returns: `None`.
```

Subclass of `RuntimeError`. Reports an endpoint that needs initialisation,
is in reset or releasing, or already has an active operation.
It also rejects overlapping `initialise()` and `close()` calls.

Independent endpoints may run concurrently.

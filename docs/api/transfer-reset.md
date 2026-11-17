# TransferReset

```{py:currentmodule} coaxi
```

```{py:exception} TransferReset(*args: object) -> None

:Parameters:
  - `args: object`

    Exception arguments, normally a diagnostic message.

:returns: `None`.
```

Subclass of `RuntimeError`. Pin assertion, explicit `initialise()`, or `close()`
invalidated pending work. Traffic may already have been accepted before
interruption. Check what the peer accepted before retrying.

Catch expected interruption inside spawned operation coroutines; cocotb can
fail on an unobserved exception before a later await observes it.
A healthy endpoint resumes automatically after a pin-only reset. Earlier faults
or caller cancellation still require local recovery.
See [Lifecycle and recovery](../lifecycle.md).

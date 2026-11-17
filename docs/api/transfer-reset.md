# TransferReset

```{py:currentmodule} coaxi
```

```{py:exception} TransferReset(*args: object) -> None

:param args: Exception arguments, normally a diagnostic message.
:type args: object
:returns: None.
:rtype: None
```

Subclass of `RuntimeError`. Pin assertion, explicit initialisation, or close
invalidated pending work. Traffic may already have been accepted before
interruption. No acceptance is undone and no retry is performed.

Catch expected interruption inside spawned operation coroutines; cocotb can
fail on an unobserved exception before a later await observes it.
A healthy endpoint resumes automatically after a pin-only reset. Earlier faults
or caller cancellation still require local recovery.
See [Lifecycle and recovery](../lifecycle.md).

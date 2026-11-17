# ProtocolValueError

```{py:currentmodule} coaxi
```

```{py:exception} ProtocolValueError(*args: object) -> None

:Parameters:
  - `args: object`

    Exception arguments, normally a diagnostic message.

:returns: `None`.
```

Subclass of `ValueError`. Reports invalid sampled `valid` or `ready`, accepted
`last`, monitored reset, literal reserved `keep`/`strb` pairs, or non-binary
packet assembly identifiers. Weak `L` and `H` fail control and identifier checks.

An in-progress protocol error requires explicit `initialise()`. The first
recorded fault continues to be reported across pin cycles until local recovery.
Payloads support meta-values; numeric conversion is explicit.

# ProtocolValueError

```{py:currentmodule} coaxi
```

```{py:exception} ProtocolValueError(*args: object) -> None

:param args: Exception arguments, normally a diagnostic message.
:type args: object
:returns: None.
:rtype: None
```

Subclass of `ValueError`. Reports invalid sampled valid/ready, accepted last,
monitored reset, literal reserved keep/strb pairs, or non-binary packet assembly
identifiers. Weak `L` and `H` fail control and identifier checks.

An in-progress protocol error requires explicit initialisation. A pin cycle
does not acknowledge a recorded fault. Payload meta-values alone do not raise
this error; numeric conversion is separate.

# SignalBindingError

```{py:currentmodule} coaxi
```

```{py:exception} SignalBindingError(*args: object) -> None

:param args: Exception arguments, normally a diagnostic message.
:type args: object
:returns: None.
:rtype: None
```

Subclass of `ValueError`. Reports missing names, unsuitable control or sideband
handles, aliased signals, or unsupported byte-qualifier layouts.
A failed binding does not drive the interface.

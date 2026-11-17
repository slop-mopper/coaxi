# SignalBindingError

```{py:currentmodule} coaxi
```

```{py:exception} SignalBindingError(*args: object) -> None

:Parameters:
  - `args: object`

    Exception arguments, normally a diagnostic message.

:returns: `None`.
```

Subclass of `ValueError`. Reports missing names, unsuitable control or sideband
handles, aliased signals, or unsupported byte-qualifier layouts.

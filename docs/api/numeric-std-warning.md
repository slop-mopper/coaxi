# NumericStdWarning

```{py:currentmodule} coaxi
```

```{py:exception} NumericStdWarning(*args: object) -> None

Filterable `UserWarning` for a VHDL `numeric_std` package warning.

:Parameters:
  - `args: object`

    Diagnostic message arguments.

:returns: `None`.
```

Ordinary comparisons warn on null or unresolved operands, null integer
conversion warns before returning zero, and scalar division/remainder paths
warn when narrowing an arithmetic result loses bits.

Use Python's `warnings` filters to suppress these diagnostics or promote
them to exceptions. Error-severity cases raise Python exceptions instead:
division by zero raises `ZeroDivisionError`, and invalid vector operations
raise `ValueError`.

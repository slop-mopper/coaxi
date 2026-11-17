# AxiStreamSidebands

```{py:currentmodule} coaxi
```

Optional per-transfer source metadata. Source operations apply the defaults
below when metadata is omitted. Keep supplied logic arrays unchanged until
the send completes.

```{py:class} AxiStreamSidebands(keep: SidebandValue | None = None, strb: SidebandValue | None = None, user: SidebandValue | None = None, id: SidebandValue | None = None, dest: SidebandValue | None = None) -> None

:Parameters:
  - `keep: SidebandValue | None`

    One presence bit per byte lane. Default `None` selects all lanes on a bound signal.

  - `strb: SidebandValue | None`

    One data/position bit per lane. Default `None` follows effective `keep` on a bound signal.

  - `user: SidebandValue | None`

    Application-defined metadata. Default `None` selects zero on a bound signal.

  - `id: SidebandValue | None`

    Stream identifier. Default `None` selects zero on a bound signal.

  - `dest: SidebandValue | None`

    Routing destination. Default `None` selects zero on a bound signal.

:returns: `None`.
```

Public attributes have the same names and types as the constructor parameters.
The source validates metadata when preparing each transfer.
An explicit value requires a bound signal. Integers must be unsigned and fit;
strings and logic values must match the bound width.
See [Sidebands and byte qualifiers](../sidebands.md) for lane pairs,
layout requirements, and examples.

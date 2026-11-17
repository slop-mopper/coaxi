# AxiStreamSidebands

```{py:currentmodule} coaxi
```

Optional per-transfer source metadata, independent of payload conversion.
Ordinary transfers need no metadata object. A frozen container does not prevent
mutation of contained logic arrays; do not mutate them during a send.

```{py:class} AxiStreamSidebands(keep: SidebandValue | None = None, strb: SidebandValue | None = None, user: SidebandValue | None = None, id: SidebandValue | None = None, dest: SidebandValue | None = None) -> None

:param keep: One presence bit per byte lane. Default `None` selects all lanes on a bound signal.
:type keep: SidebandValue | None
:param strb: One data/position bit per lane. Default `None` follows effective keep on a bound signal.
:type strb: SidebandValue | None
:param user: Application-defined metadata. Default `None` selects zero on a bound signal.
:type user: SidebandValue | None
:param id: Stream identifier. Default `None` selects zero on a bound signal.
:type id: SidebandValue | None
:param dest: Routing destination. Default `None` selects zero on a bound signal.
:type dest: SidebandValue | None
:returns: None.
:rtype: None
```

Public attributes have the same names and types as the constructor parameters.
Validation occurs when a source prepares the metadata, not in this constructor.
An explicit value for an absent signal is an error. Integers must be unsigned
and fit; strings and logic values must match the bound width.
See [Sidebands and byte qualifiers](../sidebands.md) for reserved lane pairs,
layout restrictions, and examples.

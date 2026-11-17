# AxiStreamTransfer

```{py:currentmodule} coaxi
```

A frozen record of one accepted transfer. Endpoint reads produce independent
payload and sideband snapshots. Contained dictionaries and logic arrays remain
mutable.

```{py:class} AxiStreamTransfer[T](data: T, last: bool | None, keep: Logic | LogicArray | None = None, strb: Logic | LogicArray | None = None, user: Logic | LogicArray | None = None, id: Logic | LogicArray | None = None, dest: Logic | LogicArray | None = None) -> None

:Parameters:
  - `data: T`

    Payload snapshot; `None` when the `data` signal is absent.

  - `last: bool | None`

    Sampled end-of-packet flag, or `None` without `last`.

  - `keep: Logic | LogicArray | None`

    Raw byte-presence qualifier. Default `None` indicates an absent signal.

  - `strb: Logic | LogicArray | None`

    Raw data/position-byte qualifier. Default `None` indicates an absent signal.

  - `user: Logic | LogicArray | None`

    Raw application metadata. Default `None` indicates an absent signal.

  - `id: Logic | LogicArray | None`

    Raw stream identifier. Default `None` indicates an absent signal.

  - `dest: Logic | LogicArray | None`

    Raw routing destination. Default `None` indicates an absent signal.

:returns: `None`.
```

Public attributes have the same names and types as the constructor parameters.
See [Sidebands and byte qualifiers](../sidebands.md) for the protocol meaning
of absent qualifiers and identifiers.

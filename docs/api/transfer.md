# AxiStreamTransfer

```{py:currentmodule} coaxi
```

A frozen record of one accepted transfer. Endpoint reads produce independent
payload and sideband snapshots. Freezing the record does not prevent mutation
of a contained dictionary or logic array.

```{py:class} AxiStreamTransfer[T](data: T, last: bool | None, keep: Logic | LogicArray | None = None, strb: Logic | LogicArray | None = None, user: Logic | LogicArray | None = None, id: Logic | LogicArray | None = None, dest: Logic | LogicArray | None = None) -> None

:param data: Payload snapshot; `None` when the data signal is absent.
:type data: T
:param last: Sampled end-of-packet flag, or `None` without last.
:type last: bool | None
:param keep: Raw byte-presence qualifier. Default `None` indicates an absent signal.
:type keep: Logic | LogicArray | None
:param strb: Raw data/position-byte qualifier. Default `None` indicates an absent signal.
:type strb: Logic | LogicArray | None
:param user: Raw application metadata. Default `None` indicates an absent signal.
:type user: Logic | LogicArray | None
:param id: Raw stream identifier. Default `None` indicates an absent signal.
:type id: Logic | LogicArray | None
:param dest: Raw routing destination. Default `None` indicates an absent signal.
:type dest: Logic | LogicArray | None
:returns: None.
:rtype: None
```

Public attributes have the same names and types as the constructor parameters.
No effective protocol defaults are substituted into absent fields: absent keep
means all lanes present, absent strb follows effective keep, and absent user,
id, and dest have effective value zero. No bytes are compacted or interpreted.

The constructor is a value container and does not validate an HDL interface.
Use payload sequences with `send_frame()`; received transfer records are not
its frame input format.

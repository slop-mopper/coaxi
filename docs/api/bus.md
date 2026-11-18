# AxiStreamBus

```{py:currentmodule} coaxi
```

Holds the stream's signal handles and checks their shapes on construction.
Use `bind()` to look up signals by name. See [Signal binding](../binding.md)
for the required signal widths and layouts.

```{py:class} AxiStreamBus(data: SimHandleBase | None, valid: LogicObject | LogicArrayObject, ready: LogicObject | LogicArrayObject | None, last: LogicObject | LogicArrayObject | None = None, _entity: HierarchyObject | None = None, *, keep: LogicObject | LogicArrayObject | None = None, strb: LogicObject | LogicArrayObject | None = None, user: LogicObject | LogicArrayObject | None = None, id: LogicObject | LogicArrayObject | None = None, dest: LogicObject | LogicArrayObject | None = None) -> None

:Parameters:
  - `data: SimHandleBase | None`

    Payload handle, or `None` for data-less traffic.

  - `valid: LogicObject | LogicArrayObject`

    Required one-bit `valid` handle.

  - `ready: LogicObject | LogicArrayObject | None`

    One-bit `ready` handle. With `None`, `valid` alone determines acceptance.

  - `last: LogicObject | LogicArrayObject | None`

    One-bit `last` handle. Default `None` omits framing.

  - `_entity: HierarchyObject | None`

    Internal lookup context, normally supplied by `bind()`. Default `None`.

  - `keep: LogicObject | LogicArrayObject | None`

    Byte-presence qualifier handle. Default `None` omits it.

  - `strb: LogicObject | LogicArrayObject | None`

    Data/position-byte qualifier handle. Default `None` omits it.

  - `user: LogicObject | LogicArrayObject | None`

    Application metadata handle of positive logic width. Default `None`.

  - `id: LogicObject | LogicArrayObject | None`

    Stream identifier handle of positive logic width. Default `None`.

  - `dest: LogicObject | LogicArrayObject | None`

    Routing destination handle of positive logic width. Default `None`.

:returns: `None`.
:raises SignalBindingError: A role has an unsuitable shape, aliases another role, or violates byte-lane requirements.
```

Public attributes have the same names and types as the handle parameters.

## bind

```{py:method} AxiStreamBus.bind(entity: HierarchyObject | None = None, *, prefix: str = "", t_prefix: bool = True, data: bool | Signal | None = None, valid: Signal | None = None, ready: bool | Signal | None = None, last: bool | Signal = False, keep: bool | Signal = False, strb: bool | Signal = False, user: bool | Signal = False, id: bool | Signal = False, dest: bool | Signal = False) -> Self
:classmethod:

:Parameters:
  - `entity: HierarchyObject | None`

    Parent for child-name lookup. Default `None`; may be omitted when every selected signal is a handle.

  - `prefix: str`

    Generated-name stem, followed by `_` when non-empty. Default `""`.

  - `t_prefix: bool`

    Add `t` before each generated role name. Default `True`.

  - `data: bool | Signal | None`

    `None` or `True` selects the generated name; `False` omits `data`; a name or handle overrides it. Default `None`.

  - `valid: Signal | None`

    Name or handle override for the required `valid` signal. Default `None` selects the generated name.

  - `ready: bool | Signal | None`

    `None` or `True` selects the generated name; `False` omits `ready`; a name or handle overrides it. Default `None`.

  - `last: bool | Signal`

    `False` omits `last`; `True` selects the generated name; a name or handle binds it independently. Default `False`.

  - `keep: bool | Signal`

    `False` omits `keep`; `True` selects the generated name; a name or handle binds it independently. Default `False`.

  - `strb: bool | Signal`

    `False` omits `strb`; `True` selects the generated name; a name or handle binds it independently. Default `False`.

  - `user: bool | Signal`

    `False` omits `user`; `True` selects the generated name; a name or handle binds it independently. Default `False`.

  - `id: bool | Signal`

    `False` omits `id`; `True` selects the generated name; a name or handle binds it independently. Default `False`.

  - `dest: bool | Signal`

    `False` omits `dest`; `True` selects the generated name; a name or handle binds it independently. Default `False`.

:returns: A validated bus with the selected handles and lookup context.
:raises SignalBindingError: Lookup, role shape, aliasing, or qualifier-layout validation fails.
```

Explicit names are used unchanged. Optional signals are enabled by their
selectors. Generated names combine the stem, optional `t`, and protocol role.

## resolve_clock

```{py:method} AxiStreamBus.resolve_clock(clock: Signal) -> LogicObject | LogicArrayObject

:Parameters:
  - `clock: Signal`

    Child name in the binding entity, or an already-bound one-bit logic handle.

:returns: A scalar or one-bit vector clock handle, separate from the bus roles.
:raises SignalBindingError: Lookup, clock shape, or alias validation fails.
```

Clock lookup uses the bus's binding entity independently of stream naming defaults.

# AxiStreamBus

```{py:currentmodule} coaxi
```

A frozen collection of bound stream handles. Construction validates bindings
without driving them. Prefer `bind()` for naming defaults and independent
overrides. See [Signal binding](../binding.md) for examples and layout constraints.

```{py:class} AxiStreamBus(data: SimHandleBase | None, valid: LogicObject | LogicArrayObject, ready: LogicObject | LogicArrayObject | None, last: LogicObject | LogicArrayObject | None = None, _entity: HierarchyObject | None = None, *, keep: LogicObject | LogicArrayObject | None = None, strb: LogicObject | LogicArrayObject | None = None, user: LogicObject | LogicArrayObject | None = None, id: LogicObject | LogicArrayObject | None = None, dest: LogicObject | LogicArrayObject | None = None) -> None

:param data: Payload handle, or `None` for data-less traffic.
:type data: SimHandleBase | None
:param valid: Required one-bit valid handle.
:type valid: LogicObject | LogicArrayObject
:param ready: One-bit ready handle, or `None` for unconditional acceptance.
:type ready: LogicObject | LogicArrayObject | None
:param last: One-bit last handle. Default `None` omits framing.
:type last: LogicObject | LogicArrayObject | None
:param _entity: Internal lookup context, normally supplied by `bind()`. Default `None`.
:type _entity: HierarchyObject | None
:param keep: Byte-presence qualifier handle. Default `None` omits it.
:type keep: LogicObject | LogicArrayObject | None
:param strb: Data/position-byte qualifier handle. Default `None` omits it.
:type strb: LogicObject | LogicArrayObject | None
:param user: Application metadata handle of positive logic width. Default `None`.
:type user: LogicObject | LogicArrayObject | None
:param id: Stream identifier handle of positive logic width. Default `None`.
:type id: LogicObject | LogicArrayObject | None
:param dest: Routing destination handle of positive logic width. Default `None`.
:type dest: LogicObject | LogicArrayObject | None
:returns: None.
:rtype: None
:raises SignalBindingError: A role has an unsuitable shape, aliases another role, or violates byte-lane requirements.
```

Public attributes have the same names and types as the handle parameters.
They cannot be reassigned. The private lookup context is not a stream signal.

## bind

```{py:method} AxiStreamBus.bind(entity: HierarchyObject | None = None, *, prefix: str = "", t_prefix: bool = True, data: bool | Signal | None = None, valid: Signal | None = None, ready: bool | Signal | None = None, last: bool | Signal = False, keep: bool | Signal = False, strb: bool | Signal = False, user: bool | Signal = False, id: bool | Signal = False, dest: bool | Signal = False) -> Self
:classmethod:

:param entity: Parent for child-name lookup. Default `None`; may be omitted when every selected signal is a handle.
:type entity: HierarchyObject | None
:param prefix: Generated-name stem, followed by `_` when non-empty. Default `""`.
:type prefix: str
:param t_prefix: Add `t` before each generated role name. Default `True`.
:type t_prefix: bool
:param data: `None` or `True` selects the generated name; `False` omits data; a name or handle overrides it. Default `None`.
:type data: bool | Signal | None
:param valid: Name or handle override. Default `None` selects the generated name. Valid cannot be omitted.
:type valid: Signal | None
:param ready: `None` or `True` selects the generated name; `False` omits ready; a name or handle overrides it. Default `None`.
:type ready: bool | Signal | None
:param last: `False` omits last; `True` selects the generated name; a name or handle binds it independently. Default `False`.
:type last: bool | Signal
:param keep: `False` omits keep; `True` selects the generated name; a name or handle binds it independently. Default `False`.
:type keep: bool | Signal
:param strb: `False` omits strb; `True` selects the generated name; a name or handle binds it independently. Default `False`.
:type strb: bool | Signal
:param user: `False` omits user; `True` selects the generated name; a name or handle binds it independently. Default `False`.
:type user: bool | Signal
:param id: `False` omits id; `True` selects the generated name; a name or handle binds it independently. Default `False`.
:type id: bool | Signal
:param dest: `False` omits dest; `True` selects the generated name; a name or handle binds it independently. Default `False`.
:type dest: bool | Signal
:returns: A validated bus with the selected handles and lookup context.
:rtype: Self
:raises SignalBindingError: Lookup, role shape, aliasing, or qualifier-layout validation fails.
```

Explicit names are used unchanged. Optional signals are never discovered by
probing for matching names. Generated names combine the stem, optional `t`,
and protocol role.

## resolve_clock

```{py:method} AxiStreamBus.resolve_clock(clock: Signal) -> LogicObject | LogicArrayObject

:param clock: Child name in the binding entity, or an already-bound one-bit logic handle.
:type clock: Signal
:returns: A scalar or one-bit vector clock handle, separate from the bus roles.
:rtype: LogicObject | LogicArrayObject
:raises SignalBindingError: Name lookup fails, the handle is not one-bit logic, or it aliases a bus role.
```

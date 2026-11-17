# HandlePayload

```{py:currentmodule} coaxi
```

Default synchronous payload adapter for logic leaves and named containers.
Containers are discovered once. Records use nested field-name mappings;
no packing or numeric conversion is performed.

```{py:class} HandlePayload(handle: SimHandleBase) -> None

:param handle: Scalar logic, logic-vector, or non-empty named-container payload handle.
:type handle: SimHandleBase
:returns: None.
:rtype: None
:raises TypeError: A leaf type is unsupported or a container is empty or inaccessible.
```

## read

```{py:method} HandlePayload.read() -> PayloadValue

:returns: A fresh `Logic`, `LogicArray`, or nested dictionary snapshot, including meta-values.
:rtype: PayloadValue
```

## drive

```{py:method} HandlePayload.drive(value: PayloadValue) -> None

:param value: Width-matched scalar/vector value, unsigned integer, or complete nested field mapping.
:type value: PayloadValue
:returns: None.
:rtype: None
:raises ValueError: Fields do not match, an integer is negative or out of range, or a logic value or width is invalid.
:raises TypeError: A leaf value has an unsupported type, including `None`.
```

Validates the entire payload before writing any leaf. Validation failure leaves
all leaves unchanged. Conversion errors include the failing HDL path.
Use `LogicArray.from_signed()` for negative integers.

## clear

```{py:method} HandlePayload.clear() -> None

:returns: None, after scheduling zero on every payload leaf.
:rtype: None
```

All methods are synchronous and do not advance simulation time.
Actual signal writes follow cocotb's write scheduling.

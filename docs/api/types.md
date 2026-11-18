# Types and numeric conversion

```{py:currentmodule} coaxi
```

## Signal

```{py:type} Signal
:annotation: = str | SimHandleBase
```

An HDL child name or an already-bound cocotb handle. Names are looked up
unchanged, including punctuation supported by cocotb.

## PayloadValue

```{py:type} PayloadValue
:annotation: = int | str | Logic | LogicArray | Mapping[str, PayloadValue]
```

Values accepted by `HandlePayload.drive()`. Integers are unsigned. Supply
one key per HDL field in a mapping. Reads return logic values or nested
dictionaries. A bus without `data` uses `None`.

## SidebandValue

```{py:type} SidebandValue
:annotation: = int | str | Logic | LogicArray
```

Unsigned integer or width-matched logic value for a sideband. Logic values
can include meta-values for tests that need them.

## to_unsigned

```{py:function} to_unsigned(value: LogicArray) -> int

:Parameters:
  - `value: LogicArray`

    Vector snapshot to interpret as unsigned.

:returns: The unsigned integer value.
:raises ValueError: Any bit is unresolved, including `X`, `U`, or `Z`.
```

## to_signed

```{py:function} to_signed(value: LogicArray) -> int

:Parameters:
  - `value: LogicArray`

    Vector snapshot to interpret as two's complement.

:returns: The signed integer value.
:raises ValueError: Any bit is unresolved, including `X`, `U`, or `Z`.
```

Both helpers allow weak `L` and `H` and reject unresolved values independently
of `COCOTB_RESOLVE_X`.

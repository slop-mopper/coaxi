# Signed

```{py:currentmodule} coaxi
```

````{py:class} Signed(value: LogicArray | Signed | Unsigned) -> None

Immutable VHDL-2008 `signed` value. The leftmost bit is the sign bit.

:Parameters:
  - `value: LogicArray | Signed | Unsigned`

    Bits and index range to copy. Constructor conversions reinterpret the bits;
    `Signed(Unsigned.from_int(255, width=8))` represents `-1`. Use `from_int()`
    to construct from a Python integer. Non-null index ranges must contain
    non-negative indices, as required by VHDL's `natural` index subtype.

:returns: `None`.

```{include} ../_numeric-methods.md
```
````

`Self` in the signatures denotes `Signed`. Properties and operator contracts
are in [Numeric values](../numeric.md).

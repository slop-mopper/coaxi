# Unsigned

```{py:currentmodule} coaxi
```

````{py:class} Unsigned(value: LogicArray | Signed | Unsigned) -> None

Immutable VHDL-2008 `unsigned` value. The leftmost bit is the most significant.

:Parameters:
  - `value: LogicArray | Signed | Unsigned`

    Bits and index range to copy. Constructor conversions reinterpret the bits;
    `Unsigned(Signed.from_int(-1, width=8))` represents `255`. Use `from_int()`
    to construct from a Python integer. Non-null index ranges must contain
    non-negative indices, as required by VHDL's `natural` index subtype.

:returns: `None`.

```{include} ../_numeric-methods.md
```
````

`Self` in the signatures denotes `Unsigned`. Properties and operator contracts
are in [Numeric values](../numeric.md).

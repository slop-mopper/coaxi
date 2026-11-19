# Unsigned

```{py:currentmodule} coaxi
```

Immutable VHDL-2008 `unsigned` value. The leftmost bit is the most significant.

````{py:class} Unsigned(value: Literal[0], *, width: int) -> None

:Parameters:
  - `value: Literal[0]`

    Python integer `0`. Use `from_int()` for other integers or booleans.

  - `width: int`

    Non-negative bit count. The value has range `width - 1 downto 0`, or
    `0 downto 1` at zero width.

:returns: `None`.
:raises TypeError: `value` is not integer `0`, neither width name is supplied,
    or the bit count is non-integer or boolean.
:raises ValueError: `width` is negative.

```{py:class} Unsigned(value: Literal[0], *, w: int) -> None
:no-index:

:Parameters:
  - `value: Literal[0]`

    Python integer `0`.

  - `w: int`

    Alias for `width`, with the same constraints.

:returns: `None`.
:raises TypeError: Both `width` and `w` are supplied.
```

```{py:class} Unsigned(value: LogicArray | Signed | Unsigned) -> None
:no-index:

:Parameters:
  - `value: LogicArray | Signed | Unsigned`

    Bits and index range to copy. Non-null ranges require non-negative indices.
    The bits are reinterpreted as unsigned:
    `Unsigned(Signed.from_int(-1, width=8))` represents `255`.

:returns: `None`.
:raises TypeError: `width` or `w` is supplied with a vector.
:raises ValueError: A non-null range has a negative index.
```

```{include} ../_numeric-methods.md
```
````

`Self` in the signatures denotes `Unsigned`. Properties and operator contracts
are in [Numeric values](../numeric.md).

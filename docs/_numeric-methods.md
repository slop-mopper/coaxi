## Conversion and resizing

```{py:method} from_int(value: int, *, width: int) -> Self
:classmethod:

:Parameters:
  - `value: int`

    Python integer, including `False` as zero and `True` as one.
    `Unsigned` requires a non-negative value.

  - `width: int`

    Non-negative bit count; booleans raise `TypeError`.
    At positive widths, the integer must fit the type.
    At zero width, return a null vector regardless of the integer's magnitude.

:returns: A value with range `width - 1 downto 0`, or `0 downto 1` at zero width.
:raises OverflowError: The integer does not fit a positive width.
:raises TypeError: `value` is not an integer, or `width` is not an integer or is a boolean.
:raises ValueError: `width` is negative, or an `Unsigned` input value is negative.
```

```{py:method} to_int() -> int

:returns: The arbitrary-precision Python integer interpretation. Weak `L` and `H`
    become `0` and `1`. A null vector warns and returns zero.
:raises ValueError: A bit is unresolved, independently of `COCOTB_RESOLVE_X`.
```

```{py:method} to_logic_array() -> LogicArray

:returns: An independent cocotb array with the same bits and index range.
```

```{py:method} as_signed() -> Signed

:returns: A `Signed` interpretation of the same bits and range, equivalent to `Signed(self)`.
```

```{py:method} as_unsigned() -> Unsigned

:returns: An `Unsigned` interpretation of the same bits and range, equivalent to `Unsigned(self)`.
```

```{py:method} resize(width: int) -> Self

:Parameters:
  - `width: int`

    Non-negative result bit count; booleans raise `TypeError`.
    Unsigned widening adds zeros; signed widening
    copies the raw sign bit. Unsigned narrowing keeps the low bits. Signed
    narrowing keeps the original sign and the lowest `width - 1` bits.

:returns: A resized value with descending range. Zero width gives `0 downto 1`;
    resizing a null input to positive width gives zeros.
```

## Remainder and modulus

```{py:method} mod(other: Self | int) -> Self

:Parameters:
  - `other: Self | int`

    Divisor of the same numeric type, or a VHDL scalar integer operand.

:returns: VHDL `mod`, equivalent to `%`. Vector/vector width follows the divisor;
    an integer overload returns this value's width.
:raises ZeroDivisionError: The resolved divisor is zero.
```

```{py:method} rem(other: Self | int) -> Self

:Parameters:
  - `other: Self | int`

    Divisor of the same numeric type, or a VHDL scalar integer operand.

:returns: VHDL `rem`, whose nonzero result follows the dividend's sign.
    Vector/vector width follows the divisor; an integer overload returns this value's width.
:raises ZeroDivisionError: The resolved divisor is zero.
```

```{py:method} rrem(other: int) -> Self

:Parameters:
  - `other: int`

    Integer dividend for `other rem self`.

:returns: The scalar/vector VHDL remainder, with this value's width.
:raises ZeroDivisionError: This value is a resolved zero divisor.
:raises ValueError: The unsigned overload encounters a null vector, or the
    integer dividend needs more bits than a non-null vector. The package's
    array assignment then has unequal lengths. Resolved zero division is
    checked before the non-null length error.
```

## Matching comparisons

Matching equality treats `-` as a wildcard. A `U` scalar comparison produces
`U`, and an `X` scalar comparison produces `X`, even if another bit differs.
Matching ordering rejects `-`, returns `X` for other unresolved values, and
interprets weak `L` and `H` numerically. Null operands warn and return `X`.
Integer operands undergo checked conversion at this value's width.

```{py:method} match_eq(other: Self | int) -> Logic

:Parameters:
  - `other: Self | int`

    Right operand for VHDL `?=`.

:returns: The VHDL matching-equality logic value.
```

```{py:method} match_ne(other: Self | int) -> Logic

:Parameters:
  - `other: Self | int`

    Right operand for VHDL `?/=`.

:returns: The VHDL matching-inequality logic value.
```

```{py:method} match_lt(other: Self | int) -> Logic

:Parameters:
  - `other: Self | int`

    Right operand for VHDL `?<`.

:returns: The VHDL matching less-than logic value.
:raises ValueError: Either operand contains `-`.
```

```{py:method} match_le(other: Self | int) -> Logic

:Parameters:
  - `other: Self | int`

    Right operand for VHDL `?<=`.

:returns: The VHDL matching less-than-or-equal logic value.
:raises ValueError: Either operand contains `-`.
```

```{py:method} match_gt(other: Self | int) -> Logic

:Parameters:
  - `other: Self | int`

    Right operand for VHDL `?>`.

:returns: The VHDL matching greater-than logic value.
:raises ValueError: Either operand contains `-`.
```

```{py:method} match_ge(other: Self | int) -> Logic

:Parameters:
  - `other: Self | int`

    Right operand for VHDL `?>=`.

:returns: The VHDL matching greater-than-or-equal logic value.
:raises ValueError: Either operand contains `-`.
```

## Logic

Logical vector operands require the same numeric type and equal lengths.
A scalar `Logic` operand broadcasts across all bits. All nine IEEE logic
states participate in the logic tables.

```{py:method} nand(other: Self | Logic) -> Self

:Parameters:
  - `other: Self | Logic`

    Vector or broadcast scalar for VHDL `nand`.

:returns: Elementwise NAND, with the logical result range described below.
:raises ValueError: Vector lengths differ.
```

```{py:method} nor(other: Self | Logic) -> Self

:Parameters:
  - `other: Self | Logic`

    Vector or broadcast scalar for VHDL `nor`.

:returns: Elementwise NOR, with the logical result range described below.
:raises ValueError: Vector lengths differ.
```

```{py:method} xnor(other: Self | Logic) -> Self

:Parameters:
  - `other: Self | Logic`

    Vector or broadcast scalar for VHDL `xnor`.

:returns: Elementwise XNOR, with the logical result range described below.
:raises ValueError: Vector lengths differ.
```

Vector/vector logical results and `~x` use `width - 1 downto 0`, including
`-1 downto 0` for null vectors. Scalar/vector logical results use `1 to width`,
including `1 to 0` for null vectors.

```{py:method} and_reduce() -> Logic

:returns: VHDL reduction AND; a null vector produces `1`.
```

```{py:method} nand_reduce() -> Logic

:returns: VHDL reduction NAND; a null vector produces `0`.
```

```{py:method} or_reduce() -> Logic

:returns: VHDL reduction OR; a null vector produces `0`.
```

```{py:method} nor_reduce() -> Logic

:returns: VHDL reduction NOR; a null vector produces `1`.
```

```{py:method} xor_reduce() -> Logic

:returns: VHDL reduction XOR; a null vector produces `0`.
```

```{py:method} xnor_reduce() -> Logic

:returns: VHDL reduction XNOR; a null vector produces `1`.
```

## Shifts and rotations

Movement copies raw logic states. Results use `width - 1 downto 0`, with
`0 downto 1` for null vectors. Signed arithmetic-right shifts keep the input
range when the count is zero or the input has one bit. All movement counts
require integers other than booleans; `True` and `False` raise `TypeError`,
including for null inputs.

```{py:method} shift_left(count: int) -> Self

:Parameters:
  - `count: int`

    Non-negative number of bit positions.

:returns: A same-width left shift, filling with zero; equivalent to `<<`.
```

```{py:method} shift_right(count: int) -> Self

:Parameters:
  - `count: int`

    Non-negative number of bit positions.

:returns: A same-width right shift, filling with the raw sign for `Signed`
    and zero for `Unsigned`; equivalent to `>>`.
```

```{py:method} rotate_left(count: int) -> Self

:Parameters:
  - `count: int`

    Non-negative number of bit positions, reduced modulo the nonzero width.

:returns: A same-width left rotation.
```

```{py:method} rotate_right(count: int) -> Self

:Parameters:
  - `count: int`

    Non-negative number of bit positions, reduced modulo the nonzero width.

:returns: A same-width right rotation.
```

```{py:method} sll(count: int) -> Self

:Parameters:
  - `count: int`

    Signed bit-position count. A negative count reverses direction.

:returns: VHDL logical left shift, filling with zero in either direction.
```

```{py:method} srl(count: int) -> Self

:Parameters:
  - `count: int`

    Signed bit-position count. A negative count reverses direction.

:returns: VHDL logical right shift, filling with zero in either direction.
```

```{py:method} sla(count: int) -> Self

:Parameters:
  - `count: int`

    Signed bit-position count. A negative count reverses direction.

:returns: VHDL arithmetic left shift. Left movement fills with zero;
    right movement copies the sign for `Signed` and fills with zero for `Unsigned`.
```

```{py:method} sra(count: int) -> Self

:Parameters:
  - `count: int`

    Signed bit-position count. A negative count reverses direction.

:returns: VHDL arithmetic right shift. Right movement copies the sign for `Signed`
    and fills with zero for `Unsigned`; left movement fills with zero.
```

```{py:method} rol(count: int) -> Self

:Parameters:
  - `count: int`

    Signed bit-position count. A negative count rotates right.

:returns: VHDL left rotation.
```

```{py:method} ror(count: int) -> Self

:Parameters:
  - `count: int`

    Signed bit-position count. A negative count rotates left.

:returns: VHDL right rotation.
```

## Concatenation

```{py:method} concat(other: Self | Logic) -> Self

:Parameters:
  - `other: Self | Logic`

    Same-type vector or scalar logic value placed after this value's bits.

:returns: Raw concatenation with range `0 to total_width - 1`. If both vectors
    are null, the result has the right operand's range.
```

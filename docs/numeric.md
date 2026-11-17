# Numeric values

{py:class}`coaxi.Signed` and {py:class}`coaxi.Unsigned` model VHDL-2008
`ieee.numeric_std` integer vectors. Values contain a width, index range, and
logic states. Arithmetic follows the package's result-width rules and wraps
when the result exceeds that width.

## Construction and conversion

```{doctest}
>>> from cocotb.types import Logic, LogicArray, Range
>>> from coaxi import Signed, Unsigned, NumericStdWarning
>>> u = Unsigned.from_int(255, width=8)
>>> s = Signed(u)
>>> int(u), int(s), int(Unsigned(s))
(255, -1, 255)
>>> str(s.to_logic_array())
'11111111'
>>> Signed.from_int(-3, width=8).to_int()
-3
>>> Unsigned.from_int(256, width=8)
Traceback (most recent call last):
...
OverflowError: 256 does not fit Unsigned with width 8
```

Constructors accept `LogicArray`, `Signed`, or `Unsigned`, copying all bits
and the input range. Non-null indices must be non-negative, following the
package's `natural` index subtype. Conversion between signedness reinterprets the bits.
Use `from_int()` for Python integers; positive widths are checked.
Unsigned input integers must be non-negative. Width-zero conversion returns
a null vector, following VHDL, even when the input integer is nonzero.

`from_int()` accepts `False` as zero and `True` as one, with the usual range
checks. Widths and shift/rotation counts require integers other than booleans;
passing `True` or `False` for these parameters raises `TypeError`, including
when operating on a null vector.

```{doctest}
>>> str(Unsigned.from_int(True, width=8))
'00000001'
>>> Unsigned.from_int(0, width=False)
Traceback (most recent call last):
...
TypeError: expected a Python integer, not bool
```

`to_int()` and `int(x)` interpret weak `L` and `H` numerically and raise
`ValueError` for other meta-values. A null vector warns and converts to zero.
Python integer conversions support arbitrary precision. Conversion of a
resolved, non-null value produces no warnings. The VHDL package body can warn
while converting a one-bit signed `-1` through an internal scalar addition;
Python conversion returns `-1` without that intermediate operation.

`to_logic_array()` returns a separate mutable array. Mutating an input or
exported array does not change the numeric value. Use the exported array when
driving cocotb handles or the default coaxi payload adapter:

```python
sample = Signed(dut.sample.value)
result = sample * Signed.from_int(3, width=8)
dut.result.value = result.to_logic_array()
await source.send(sample.to_logic_array())
```

## Widths and integer overloads

For same-type vector operands of widths `L` and `R`:

| Operation | Result width |
|---|---:|
| `+`, binary `-` | `max(L, R)` |
| `*` | `L + R` |
| `/` | `L` |
| `%`, `mod`, `rem` | `R` |
| Signed unary `-`, `abs` | Input width |
| Shifts and rotations | Input width |
| Binary logical operations | Input width; vector lengths must match |

Signed and unsigned vector operands require an explicit constructor conversion
before they can be combined.

```{doctest}
>>> (u + 1).to_int(), (u * 2).to_int(), (u * 2).width
(0, 510, 16)
>>> (u.resize(9) + 1).to_int()
256
>>> (u + 1).resize(9).to_int()
0
>>> (Signed.from_int(127, width=8) + 1).to_int()
-128
```

`+`, `-`, and `*` convert an integer operand to the vector's width first.
That input conversion raises `OverflowError` if it cannot fit, in either
operand order. Multiplication then produces twice the vector width.
VHDL permits truncating these input conversions with a warning; coaxi's
checked-conversion policy deliberately raises instead.

Division, remainder, and modulus use different scalar implementations, with
wider temporaries where required. They return the vector's width and can warn
when narrowing an arithmetic result. Ordinary integer comparisons compare
out-of-range integers numerically, without a truncating input conversion.
Matching comparisons convert an integer at the vector's width.

Scalar/vector operand order is supported for Python operators:

```{doctest}
>>> a = Signed.from_int(-7, width=8)
>>> (3 + a).to_int(), (3 - a).to_int()
(-4, 10)
>>> (a / 3).to_int(), a.rem(3).to_int(), (a % 3).to_int()
(-2, -1, 2)
>>> a.rrem(3).to_int()
3
```

Division truncates towards zero. A nonzero `rem` follows the dividend's sign;
a nonzero `mod` follows the divisor's sign. `/` returns a numeric vector.
`//` and exponentiation are unsupported.

VHDL's scalar division has a shortcut: a divisor needing more bits than the
vector produces zero before vector division. Package compatibility includes
that result:

```{doctest}
>>> minimum = Signed.from_int(-8, width=4)
>>> (minimum / 8).to_int()
0
>>> (minimum / Signed.from_int(8, width=5)).to_int()
-1
```

Signed `mod` also tests the raw dividend sign after calculating magnitudes:
`Signed(LogicArray("H011")) % Signed.from_int(3, width=4)` produces `2`;
using literal sign `1` in `"1011"` produces `1`.

## Indexing, resizing, and logic

The leftmost bit is most significant, including ascending input ranges.
Indices are HDL indices; slices include both endpoints and follow the
input direction. `x[:]` copies the whole value, including a null value.
Indexing returns `Logic`; slicing returns the same numeric type.

```{doctest}
>>> x = Signed(LogicArray("01111111", Range(8, "to", 15)))
>>> str(x[8:11]), x[8]
('0111', Logic('0'))
>>> str(x.resize(4)), str(x[12:15])
('0111', '1111')
```

Signed `resize()` narrowing keeps the original sign bit and the low
`new_width - 1` bits. Unsigned narrowing keeps the low bits. Widening adds
raw sign bits or zeros. Resize results use a descending range.

Bitwise `&`, `|`, `^`, and `~` use the IEEE logic tables. Named `nand`,
`nor`, and `xnor` methods provide the other binary operators.
A `Logic` operand broadcasts; Python integers are not logical operands.
`and_reduce()`, `nand_reduce()`, `or_reduce()`, `nor_reduce()`, `xor_reduce()`,
and `xnor_reduce()` return a single `Logic`.

`<<` and `>>` map to `shift_left()` and `shift_right()`, with non-negative
counts. Signed right shift copies the raw sign. The named VHDL operators
`sll`, `srl`, `sla`, `sra`, `rol`, and `ror` accept negative counts to reverse
direction. In particular, `srl()` fills with zero even for signed values.

Most numeric results use a descending range. Scalar logical results use
`1 to width`, and nonempty concatenation uses `0 to total_width - 1`.
Signed arithmetic-right shift keeps the input range at count zero or
width one. The class references describe operation-specific null ranges.

## Meta-values and diagnostics

Vector arithmetic normalises `L/H` to `0/1`. Another meta-value in either
non-null operand produces an all-`X` result, including multiplication by zero.
These arithmetic paths do not warn. The oversized scalar-divisor shortcut
returns zero before inspecting meta-values. Movement, resize, and signedness
conversion copy raw logic states.

Ordinary comparisons warn on unresolved or null operands. `==` and all
ordering comparisons return `False`; `!=` returns `True`. Consequently,
an unresolved value is unequal to itself. Numeric vectors are unhashable.
Matching comparisons are separate methods returning `Logic`, with VHDL
wildcard and meta-value rules.

```{doctest}
>>> import warnings
>>> x = Signed(LogicArray("0X01"))
>>> str(x * 0), str(x & Logic("0"))
('XXXXXXXX', '0000')
>>> str(x / 256)
'0000'
>>> with warnings.catch_warnings(record=True) as messages:
...     warnings.simplefilter("always", NumericStdWarning)
...     equal = x == x
>>> equal, len(messages), messages[0].category is NumericStdWarning
(False, 1, True)
```

Filter {py:class}`coaxi.NumericStdWarning` with Python's `warnings` module,
including promotion to an exception. Error-severity operations raise Python
exceptions: resolved division by zero raises `ZeroDivisionError`, and invalid
operations such as mismatched logical lengths raise `ValueError`. Null inputs
follow each package operation's early-return or failure path.

## Operator signatures

`Self` means the numeric type of the left vector operand. The signatures
below apply to both types, except unary negation and absolute value,
which apply to `Signed`.

```python
def __add__(other: Self | int | Logic) -> Self: ...
def __radd__(other: int | Logic) -> Self: ...
def __sub__(other: Self | int | Logic) -> Self: ...
def __rsub__(other: int | Logic) -> Self: ...
def __mul__(other: Self | int) -> Self: ...
def __rmul__(other: int) -> Self: ...
def __truediv__(other: Self | int) -> Self: ...
def __rtruediv__(other: int) -> Self: ...
def __mod__(other: Self | int) -> Self: ...
def __rmod__(other: int) -> Self: ...
def __eq__(other: object) -> bool: ...
def __ne__(other: object) -> bool: ...
def __lt__(other: Self | int) -> bool: ...
def __le__(other: Self | int) -> bool: ...
def __gt__(other: Self | int) -> bool: ...
def __ge__(other: Self | int) -> bool: ...
def __and__(other: Self | Logic) -> Self: ...
def __rand__(other: Logic) -> Self: ...
def __or__(other: Self | Logic) -> Self: ...
def __ror__(other: Logic) -> Self: ...
def __xor__(other: Self | Logic) -> Self: ...
def __rxor__(other: Logic) -> Self: ...
def __invert__() -> Self: ...
def __lshift__(count: int) -> Self: ...
def __rshift__(count: int) -> Self: ...
def __neg__() -> Self: ...
def __abs__() -> Self: ...
def __int__() -> int: ...
def __bool__() -> bool: ...
def __len__() -> int: ...
def __str__() -> str: ...
def __repr__() -> str: ...
def __iter__() -> Iterator[Logic]: ...
def __getitem__(item: int | slice) -> Logic | Self: ...
```

:Parameters:
  - `other: Self | int | Logic | object`

    Right operand, or the left scalar for reflected methods. Arithmetic accepts
    same-type vectors and the scalar types in each signature. `Logic` arithmetic
    has VHDL's single-bit addition/subtraction overloads. Comparison methods
    require the same numeric type or an integer, including `==` and `!=`;
    other objects raise `TypeError`.

  - `count: int`

    Non-negative shift count in bit positions.

  - `item: int | slice`

    HDL index, or an inclusive slice following the input direction. Slice steps
    are unsupported.

:Returns:
  Arithmetic, bitwise, and movement operators return a new value using the
  width and range rules above. Comparisons return `bool`. `int()` performs
  explicit numeric conversion; `len()` returns width; `str()` returns logic
  characters; `repr()` includes type and range; iteration yields left-to-right
  `Logic` values; indexing returns `Logic`; slicing returns the same type.
  Truth testing always raises `TypeError`; write a comparison for `if`.

Properties are read-only:

| Attribute | Type | Meaning |
|---|---|---|
| `width` | `int` | Number of bits, including zero. |
| `range` | `Range` | Independent cocotb range, including direction. |
| `is_resolvable` | `bool` | All bits are `0`, `1`, `L`, or `H`. |

The types supply no `__index__` conversion. Use `to_int()` explicitly where
a Python index is required. Fixed-point formats, rounding, and saturation
remain outside these integer types.

## Validation

The regression compares Python values against NVC's VHDL-2008 package with C
intrinsics both enabled and disabled. It checks bits, ranges, results, and
warning presence. Two null-range differences in NVC 1.21.1 are handled
explicitly in the oracle tests: its C `resize` intrinsic returns `-1 downto 0`
at zero width, and concatenating two null vectors produces `0 to -1`.
coaxi follows the IEEE package's `0 downto 1` resize result and the language
rule that two null operands yield the right operand's range.

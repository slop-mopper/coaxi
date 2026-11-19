# Numeric values

{py:class}`coaxi.Signed` and {py:class}`coaxi.Unsigned` model VHDL-2008
`ieee.numeric_std` integer vectors. Arithmetic uses VHDL result widths and
wraps when a result does not fit.

## Construction and conversion

```{doctest}
>>> from cocotb.types import Logic, LogicArray, Range
>>> from coaxi import Signed, Unsigned, NumericStdWarning
>>> str(Signed(0, width=8)), str(Unsigned(0, w=4))
('00000000', '0000')
>>> str(Unsigned.from_int(3, w=4).resize(w=6))
'000011'
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

Construct from integer `0` with a width to initialise every bit to zero.
A width of zero gives a null vector with range `0 downto 1`. Use either
`width` or `w` for zero construction, `from_int()`, and `resize()`. Supplying
both names raises `TypeError`. `resize(8)` also accepts the width positionally.

When constructing from a `LogicArray`, `Signed`, or `Unsigned`, the constructor
copies the bits and range from the input, so omit the width. Non-null indices
must be non-negative, following the package's `natural` index subtype.
Changing signedness reinterprets the bits.

Use `from_int()` for general Python integers. At positive widths it raises
`OverflowError` if the integer does not fit. At zero width it returns a null
vector, even for a nonzero integer. `Unsigned.from_int()` rejects negative
integers at any width.

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
Resolved non-null vectors convert without warnings or a width limit.

`to_logic_array()` returns a separate mutable array. Mutating an input or
exported array does not change the numeric value. Use the exported array when
driving cocotb handles or the default coaxi payload adapter. Here an 8-bit
`sample` times an 8-bit coefficient produces a 16-bit `result`:

```python
sample = Signed(dut.sample.value)
result = sample * Signed.from_int(3, width=8)
dut.result.value = result.to_logic_array()
await source.send(sample.to_logic_array())
```

## Widths and integer overloads

For non-null operands of the same type, with widths `L` and `R`:

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
If the integer does not fit, the operation raises `OverflowError` before
calculating, in either operand order. VHDL can truncate that input with a
warning. Arithmetic results can still wrap. Multiplication produces twice
the vector width.

Division, remainder, and modulus use different scalar implementations, with
wider temporaries where required. They return the vector's width and can warn
when narrowing an arithmetic result. Ordinary comparisons use the integer's
full value, though `Unsigned` rejects negative integers. Matching comparisons
convert the integer at the vector's width.

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

In `vector / int`, a divisor that needs more bits than the vector produces
zero before vector division:

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

`Self` is the type of the vector whose method is called. Unary negation and
absolute value apply only to `Signed`.

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

Use `to_int()` where Python requires an integer index. See
[Calculate an expected HDL result](examples/arithmetic.md) for multiplication,
signed resize, and counter wrap.

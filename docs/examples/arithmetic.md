# Calculate an expected HDL result

Multiply an 8-bit signed sample by an 8-bit signed coefficient. The product
is 16 bits wide. Resize it if the DUT also calls VHDL's signed `resize`.

```{doctest}
>>> from cocotb.types import LogicArray
>>> from coaxi import Signed, Unsigned
>>> sample = Signed(LogicArray("11110100"))  # -12
>>> gain = Signed.from_int(3, width=8)
>>> product = sample * gain
>>> product.width, int(product)
(16, -36)
>>> expected = product.resize(8).to_logic_array()
>>> str(expected), expected.to_signed()
('11011100', -36)
```

Compare `expected` with the DUT output bits. Match the DUT's operation
and width: signed `resize` keeps the original sign bit and the low bits;
it does not saturate the result or always match a low-bit slice.

Adding an integer to an unsigned counter keeps the counter width and wraps.
Widen the counter before adding to keep the carry:

```{doctest}
>>> counter = Unsigned.from_int(255, width=8)
>>> int(counter + 1), int(counter.resize(9) + 1)
(0, 256)
```

Run the examples in Python or use
`uv run --locked --group docs sphinx-build -M doctest docs docs/_build -n -W`.
For unresolved logic and other operations, see [Numeric values](../numeric.md).

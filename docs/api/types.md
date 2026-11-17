# Types and numeric conversion

```{py:currentmodule} coaxi
```

## Signal

```{py:type} Signal
:annotation: = str | SimHandleBase
```

An HDL child name or an already-bound cocotb handle. Names are looked up
unchanged and are not restricted to Python identifiers.

## PayloadValue

```{py:type} PayloadValue
:annotation: = int | str | Logic | LogicArray | Mapping[str, PayloadValue]
```

Default-adapter input type. Integers are unsigned, and mappings describe
complete named-container fields. Reads produce logic snapshots or nested
dictionaries, without integer conversion. `None` is separate from this alias
and is used only on data-less buses.

## SidebandValue

```{py:type} SidebandValue
:annotation: = int | str | Logic | LogicArray
```

Unsigned integer or width-matched logic value for source metadata.
Deliberate meta-values are supported.

## to_unsigned

```{py:function} to_unsigned(value: LogicArray) -> int

:param value: Vector snapshot to interpret as unsigned.
:type value: LogicArray
:returns: The unsigned integer value.
:rtype: int
:raises ValueError: Any bit is unresolved, including `X`, `U`, or `Z`.
```

## to_signed

```{py:function} to_signed(value: LogicArray) -> int

:param value: Vector snapshot to interpret as two's complement.
:type value: LogicArray
:returns: The signed integer value.
:rtype: int
:raises ValueError: Any bit is unresolved, including `X`, `U`, or `Z`.
```

Both helpers allow weak `L` and `H` and reject unresolved values independently
of `COCOTB_RESOLVE_X`. They do not drive signals or advance simulation time.

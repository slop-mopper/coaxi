# IQ samples as a dataclass

Send a frame of Python `IQ` samples through a VHDL loopback. Each sample has
two signed 16-bit fields. The adapter lets the test compare `IQ` values
directly. The default adapter can send the same record as a dictionary.
The HDL wires the streams together without buffering, so send and receive
must run concurrently.

## VHDL: `iq_loopback.vhd`

```{literalinclude} ../../examples/iq_loopback.vhd
:language: vhdl
:lines: 5-
```

## Python: `custom_payload.py`

Bind both buses before constructing their adapters. Each `IQPayload`
looks up `i` and `q` on its own `data` handle and takes the widths and
indices from those signals. `drive()` converts both integers before writing
either field. `read()` builds a new `IQ` and raises `ValueError` on unresolved
bits. The source uses `clear()` to write zeros during initialisation and
cleanup; the sink never writes the record.

```{literalinclude} ../../examples/custom_payload.py
:language: python
:lines: 7-
```

```console
uv run --locked pytest -q tests/test_simulation.py -k custom_payload
```

In another cocotb project, compile
{download}`iq_loopback.vhd <../../examples/iq_loopback.vhd>` as VHDL-2008 and
select `iq_loopback` as the top level. Put
{download}`custom_payload.py <../../examples/custom_payload.py>` on the
Python import path and set `COCOTB_TEST_MODULES=custom_payload`.
For your DUT, change the bindings and the adapter's field lookups and
conversions. `keep` and `strb` require a byte-aligned vector; leave them
unbound on a record bus.

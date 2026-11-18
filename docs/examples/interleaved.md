# Interleaved packets and byte qualifiers

Send the first beat of packet A, all of packet B, then the last beat of A.
The sink groups transfers by `(id, dest)` and returns B first because B
finishes first. Here `dest` is unbound and counts as zero for grouping.

```{literalinclude} ../../examples/interleaved.py
:language: python
:lines: 7-
```

```console
uv run --locked pytest -q tests/test_simulation.py -k interleaved
```

The `sb` signals in
{download}`stream_dut.vhd <../../tests/hdl/stream_dut.vhd>` share a 16-bit
bus. `keep=0b01` marks only the low byte present; omitted `strb` follows
`keep`. `recv_frame()` returns the full-width payload and the sampled
qualifiers. It does not remove null bytes.

Use individual `send()` calls to alternate packet IDs. `send_frame()` keeps
one ID and destination for the whole frame. Keep IDs binary when using
`recv_frame()`.

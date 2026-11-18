# Sidebands and byte qualifiers

Select sidebands when binding. Use {py:class}`coaxi.AxiStreamSidebands` to
override their values on a send:

```python
from coaxi import AxiStreamSidebands

await source.send(
	0x1234,
	last=True,
	sidebands=AxiStreamSidebands(keep=0b01, user=3),
)
```

This send needs 16-bit `data`, `last`, `keep`, and at least two bits of `user`.
Omit `sidebands` or set a field to `None` to use its default on a bound signal:

| Signal | Default |
|---|---|
| `keep` | All lanes present |
| `strb` | Effective `keep` |
| `user`, `id`, `dest` | Zero |

Explicit metadata for an absent signal is an error. Integers must be unsigned
and fit the signal width. Logic strings and logic values must match its width.
Meta-valued sidebands are supported for deliberate tests.

Receives return the sampled logic values, or `None` for an unbound signal.

## Byte lanes

With `data` present, `keep` and `strb` require byte-aligned logic-vector data and
one qualifier bit per byte. The rightmost qualifier bit describes the least
significant byte, independently of the HDL index range.
Binding checks the HDL `data` handle even with a custom adapter.

| `keep` | `strb` | Byte meaning |
|---|---|---|
| 1 | 1 | Data byte |
| 1 | 0 | Position byte |
| 0 | 0 | Null byte |
| 0 | 1 | Reserved; rejected |

Absent `keep` means every lane is present. Absent `strb` follows effective `keep`.
For a literal reserved pair, `send()` raises `ValueError` before driving;
the sink raises `ProtocolValueError` after acceptance. The sink returns
meta-valued qualifiers as sampled. Check their validity in the test.

Without `data`, `keep` defines its own lane count; `strb` is forbidden.
`last`, `user`, `id`, and `dest` support any payload shape.

## Frame metadata

When passing `sidebands` to `send_frame()`, supply one entry per payload:

```python
await source.send_frame(
	[0x1234, 0x56],
	sidebands=[
		AxiStreamSidebands(id=2, keep=0b11),
		AxiStreamSidebands(id=2, keep=0b01),
	],
)
```

This frame needs `last`, two-bit `keep`, and at least two bits of `id`.
`send_frame()` uses one binary `(id, dest)` pair for the whole packet;
unbound identifiers count as zero. Keep both sequences unchanged while
sending. If a later entry is invalid, the peer may have accepted earlier beats.

See [Interleaved packets and byte qualifiers](examples/interleaved.md) for
sending by ID with `send()` and collecting by ID with `recv_frame()`.

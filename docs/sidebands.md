# Sidebands and byte qualifiers

All sidebands are selected explicitly when binding.
Ordinary sends need no metadata object, even when sideband signals are bound.
Use {py:class}`coaxi.AxiStreamSidebands` to override individual values:

```python
from coaxi import AxiStreamSidebands

await source.send(
	0x1234,
	last=True,
	sidebands=AxiStreamSidebands(keep=0b01, user=3),
)
```

This assumes a 16-bit data bus with last, keep, and a sufficiently wide user
signal. Omitted source metadata uses these defaults on bound signals:

| Signal | Default |
|---|---|
| keep | All lanes present |
| strb | Effective keep |
| user, id, dest | Zero |

Explicit metadata for an absent signal is an error. Integers must be unsigned
and fit the signal width. Logic strings and logic values must match its width.
Meta-valued sidebands are supported for deliberate tests.

Reception produces raw logic snapshots. A missing signal appears as `None`,
without substituting its effective protocol default. No byte compaction,
packet routing, or application-specific interpretation is performed.

## Byte lanes

With data present, keep/strb require byte-aligned logic-vector data and one
qualifier bit per byte. The rightmost qualifier bit describes the least
significant byte, independently of the HDL index range. Records and custom
payload adapters do not supply an inferred byte layout.

| keep | strb | Byte meaning |
|---|---|---|
| 1 | 1 | Data byte |
| 1 | 0 | Position byte |
| 0 | 0 | Null byte |
| 0 | 1 | Reserved; rejected |

Absent keep means every lane is present. Absent strb follows effective keep.
A literal reserved pair is rejected before a single send begins and after
acceptance on reception. Meta-valued qualifier pairs stay as raw values;
accepting them does not establish that they are valid protocol traffic.

With no data signal, keep can define its own lane count, but strb is not allowed.
Last, user, id, and dest do not depend on the data shape.

## Frame metadata

A frame may supply one metadata value per payload:

```python
await source.send_frame(
	[0x1234, 0x56],
	sidebands=[
		AxiStreamSidebands(id=2, keep=0b11),
		AxiStreamSidebands(id=2, keep=0b01),
	],
)
```

This assumes bound last, id, and two-bit keep. Frame helpers require literal
binary identifiers and a constant effective `(id, dest)` for each packet.
Payload and metadata validation occurs as each transfer is prepared, so an
in-progress frame error can follow an already accepted prefix.
Do not mutate the sequences or their values while sending.

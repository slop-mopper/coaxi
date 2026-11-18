# Signal binding

{py:meth}`coaxi.AxiStreamBus.bind` accepts a child name or a cocotb handle
for each signal. It looks up explicit names as supplied, including case
and punctuation.

## Naming defaults and overrides

Standard AXI-Stream names:

```python
bus = AxiStreamBus.bind(dut, prefix="input", last=True)
# input_tdata, input_tvalid, input_tready, input_tlast
```

Names without the `t`:

```python
bus = AxiStreamBus.bind(dut, prefix="output", t_prefix=False)
# output_data, output_valid, output_ready; no optional signals
```

Override individual signals and use generated names for the rest:

```python
bus = AxiStreamBus.bind(
	dut,
	prefix="input",
	valid="sample_available",
	ready=dut.consumer_accepts,
	last="end_of_packet",
)
```

If all signals are handles, omit the entity:

```python
bus = AxiStreamBus.bind(
	data=dut.iq_word_in,
	valid=dut.sample_available,
	ready=dut.consumer_accepts,
	last=dut.end_of_packet,
)
source = AxiStreamSource(bus, clock=dut.beat_clock)
```

When binding without an entity, pass `clock` and `reset` as handles too.

## Optional signals

`bind()` generates names for `data`, `valid`, and `ready` by default.
Select `last`, `keep`, `strb`, `user`, `id`, and `dest` when present:

```python
bus = AxiStreamBus.bind(dut, prefix="s", last=True, keep=True, user="tags")
```

`data` and `ready` can each be omitted:

```python
bus = AxiStreamBus.bind(dut, valid="tick", data=False, ready=False)
```

A source without `data` sends `None`. See
[Capture without `ready`](examples/no-ready.md) for a bus with neither signal.

`None` in `bind()` requests a generated `data` or `ready` name.
In the direct handle constructor, `None` denotes absence.

## Handle constraints

`valid`, `ready`, `last`, `clock`, and `reset` use scalar logic or a one-bit
logic vector. One-bit vectors can have non-zero HDL indices.
`user`, `id`, and `dest` use scalar logic or any non-empty logic vector.

`keep` and `strb` need a byte-lane layout. With `data` present, its handle
must be a non-empty, byte-aligned logic vector, with one qualifier bit per
byte. This layout is required with custom adapters too.
Without `data`, `keep` defines the lane count from its own width; `strb` is forbidden.

Use separate signals for each stream role, `clock`, and `reset`.
Bus construction rejects roles with the same HDL path. Clock resolution checks
`clock` aliases; endpoint construction checks `reset` aliases and mutability.
The caller must also check for overlaps between a container and its fields,
or a vector and its bits.

See {py:meth}`coaxi.AxiStreamBus.bind` for the selector types and defaults.

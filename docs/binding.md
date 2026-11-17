# Signal binding

{py:class}`coaxi.AxiStreamBus` associates protocol roles with HDL handles.
No HDL naming convention is required. Names can be unrelated, have different
case, or contain punctuation supported by cocotb.

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

Each role can override its generated name independently:

```python
bus = AxiStreamBus.bind(
	dut,
	prefix="input",
	valid="sample_available",
	ready=dut.consumer_accepts,
	last="end_of_packet",
)
```

The other roles still use their defaults. Explicit names receive no added
prefix or suffix and no case changes. A name is looked up as a child of the
binding entity, without using Python attribute syntax.

Fully explicit handles need no entity:

```python
bus = AxiStreamBus.bind(
	data=dut.iq_word_in,
	valid=dut.sample_available,
	ready=dut.consumer_accepts,
	last=dut.end_of_packet,
)
source = AxiStreamSource(bus, clock=dut.beat_clock)
```

Direct construction with handles is also supported. Use clock and reset
handles with a directly constructed bus; name lookup normally uses the entity
supplied to `bind()`.

## Optional signals

Only data, valid, and ready have generated defaults enabled initially.
Last, keep, strb, user, id, and dest must be selected explicitly. The presence
of a matching HDL name does not enable a sideband.

```python
bus = AxiStreamBus.bind(dut, prefix="s", last=True, keep=True, user="tags")
```

Data and ready can each be omitted:

```python
bus = AxiStreamBus.bind(dut, valid="tick", data=False, ready=False)
```

A data-less source sends `None`. With no ready signal, every rising edge
with valid asserted accepts a transfer, and the sink captures continuously
after initialisation. See [Streams without ready](transfers.md#streams-without-ready).

`None` in `bind()` requests a generated data or ready name. It does not
omit that signal. In the direct handle constructor, `None` denotes absence.

## Handle constraints

Valid, ready, last, clock, and reset use scalar logic or a one-bit logic
vector. One-bit vectors can have non-zero HDL indices.
User, id, and dest use scalar logic or any non-empty logic vector.

Keep and strb need a byte-lane layout. With data present, the data handle
must be a non-empty, byte-aligned logic vector, with one qualifier bit per
byte. A record has no inferred byte layout, even with a custom adapter.
Without data, keep defines the lane count from its own width; strb is forbidden.

Stream roles, clock, and reset must not overlap. Bus construction rejects
roles with the same HDL path. Clock resolution checks clock aliases; endpoint
construction checks reset aliases and mutability. These checks cannot detect
every overlap between a container and one of its fields, or a vector and one
of its bits. The caller must avoid those overlaps.

See {py:meth}`coaxi.AxiStreamBus.bind` for the selector types and defaults.

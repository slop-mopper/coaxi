# test_numeric_vhdl.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Compare numeric values with an independent NVC VHDL-2008 numeric_std oracle."""

import operator
import random
import subprocess
import warnings
from collections.abc import Callable
from pathlib import Path

import pytest
from cocotb.types import Logic, LogicArray, Range

from coaxi import NumericStdWarning, Signed, Unsigned

type _Value = Signed | Unsigned | Logic | bool

_HEADER = """-- numeric_oracle.vhd
-- SPDX-License-Identifier: CC0-1.0
-- This file was created by an AI model: openai/gpt-6.1-sol
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity numeric_oracle is end;
architecture test of numeric_oracle is
  function bits(text : string; ascending : boolean) return std_logic_vector is
    variable d : std_logic_vector(text'length-1 downto 0);
    variable a : std_logic_vector(3 to text'length+2);
  begin
    for i in text'range loop
      d(text'length-i) := std_logic'value("'" & text(i) & "'");
    end loop;
    a := d;
    if ascending then return a; else return d; end if;
  end;
  function us(text : string; ascending : boolean := false) return unsigned is
  begin return unsigned(bits(text, ascending)); end;
  function si(text : string; ascending : boolean := false) return signed is
  begin return signed(bits(text, ascending)); end;
  procedure emit(id : natural; value : std_logic_vector) is
  begin
    report "RESULT|" & integer'image(id) & "|" & to_string(value) & "|" &
      integer'image(value'left) & "|" & boolean'image(value'ascending) & "|" & integer'image(value'right);
  end;
  procedure emit(id : natural; value : unsigned) is
  begin
    report "RESULT|" & integer'image(id) & "|" & to_string(value) & "|" &
      integer'image(value'left) & "|" & boolean'image(value'ascending) & "|" & integer'image(value'right);
  end;
  procedure emit(id : natural; value : signed) is
  begin
    report "RESULT|" & integer'image(id) & "|" & to_string(value) & "|" &
      integer'image(value'left) & "|" & boolean'image(value'ascending) & "|" & integer'image(value'right);
  end;
  procedure emit(id : natural; value : std_logic) is
  begin report "RESULT|" & integer'image(id) & "|" & std_logic'image(value); end;
  procedure emit(id : natural; value : boolean) is
  begin report "RESULT|" & integer'image(id) & "|" & boolean'image(value); end;
begin
  process begin
"""


def _encoding(value: _Value) -> str:
	if isinstance(value, (Signed, Unsigned)):
		bounds = value.range
		return f"{value!s}|{bounds.left}|{str(bounds.direction == 'to').lower()}|{bounds.right}"
	if isinstance(value, Logic):
		return f"'{value!s}'"
	return str(value).lower()


def _vector(text: str, kind: type[Signed] | type[Unsigned], ascending: bool = False) -> tuple[Signed | Unsigned, str]:
	bounds = Range(3, "to", len(text) + 2) if ascending else Range(len(text) - 1, "downto", 0)
	value = kind(LogicArray(text, bounds))
	return value, f'{"si" if kind is Signed else "us"}("{text}", {str(ascending).lower()})'


@pytest.mark.parametrize("intrinsics", ["0", "1"])
@pytest.mark.parametrize("kind", [Signed, Unsigned])
def test_numeric_std_oracle(
	tmp_path: Path,
	kind: type[Signed] | type[Unsigned],
	intrinsics: str,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Compare bits, ranges, Boolean/logic results, and warning presence with NVC."""
	# NVC's C resize intrinsic gives a different null range from the IEEE body.
	# Exercise both implementations, regardless of the inherited environment.
	monkeypatch.setenv("NVC_JIT_INTRINSICS", intrinsics)
	seed = 0x51_6E_ED
	random_source = random.Random(seed)
	rows: list[tuple[str, str, bool]] = []

	def add(expression: str, evaluate: Callable[[], _Value]) -> None:
		with warnings.catch_warnings(record=True) as caught:
			warnings.simplefilter("always", NumericStdWarning)
			try:
				value = evaluate()
			except (OverflowError, ZeroDivisionError):
				return  # Checked inputs and zero division have separate tests.
			except ValueError as exc:
				assert any(
					reason in str(exc)
					for reason in (
						"matching ordering",
						"scalar Logic arithmetic",
						"array length mismatch",
					)
				), (expression, exc)
				return  # Each package error path has a separate failing-oracle test.
		rows.append((expression, _encoding(value), any(issubclass(w.category, NumericStdWarning) for w in caught)))

	operators = [
		("+", operator.add),
		("-", operator.sub),
		("*", operator.mul),
		("/", operator.truediv),
		("mod", operator.mod),
		("rem", lambda a, b: a.rem(b)),
		("=", operator.eq),
		("/=", operator.ne),
		("<", operator.lt),
		("<=", operator.le),
		(">", operator.gt),
		(">=", operator.ge),
	]
	logical = [
		("and", operator.and_),
		("or", operator.or_),
		("xor", operator.xor),
		("nand", lambda a, b: a.nand(b)),
		("nor", lambda a, b: a.nor(b)),
		("xnor", lambda a, b: a.xnor(b)),
	]
	matching = [
		("?=", "match_eq"),
		("?/=", "match_ne"),
		("?<", "match_lt"),
		("?<=", "match_le"),
		("?>", "match_gt"),
		("?>=", "match_ge"),
	]

	# Exhaust all resolved vector pairs through three bits, across unequal widths.
	vectors = [format(value, f"0{width}b") for width in range(1, 4) for value in range(1 << width)]
	pairs = [(a, b) for a in vectors for b in vectors]
	# Reproducible larger operands, including widths beyond the simulator INTEGER type.
	for _ in range(48):
		wa, wb = random_source.choice([4, 8, 17, 33, 65, 129, 257]), random_source.choice([4, 8, 17, 33, 65, 129, 257])
		pairs.append(
			(format(random_source.getrandbits(wa), f"0{wa}b"), format(random_source.getrandbits(wb), f"0{wb}b"))
		)
	# Every nine-state scalar pair, plus multi-bit cases where U/X override mismatches.
	pairs += [(a, b) for a in "UX01ZWLH-" for b in "UX01ZWLH-"]
	pairs += [(a, b) for a in ["U0", "X0", "H011", "1011", "", "0UX1"] for b in ["U1", "X1", "0011", "", "0000"]]
	for index, (ta, tb) in enumerate(pairs):
		a, ea = _vector(ta, kind, index % 2 == 0)
		b, eb = _vector(tb, kind, index % 3 == 0)
		for symbol, function in operators:
			add(f"({ea} {symbol} {eb})", lambda f=function, a=a, b=b: f(a, b))
		for symbol, method in matching:
			add(f"({ea} {symbol} {eb})", lambda m=method, a=a, b=b: getattr(a, m)(b))
		if len(ta) == len(tb):
			for symbol, function in logical:
				add(f"({ea} {symbol} {eb})", lambda f=function, a=a, b=b: f(a, b))
		add(f"({ea} & {eb})", lambda a=a, b=b: a.concat(b))

	for ta in ["", "0", "1", "L", "H", "U", "10", "0111", "1000", "H011", "U01X", "10-ZWLH"]:
		a, ea = _vector(ta, kind, True)
		add(ea, lambda a=a: a)
		add(f"(not {ea})", lambda a=a: ~a)
		if kind is Signed:
			add(f"(-{ea})", lambda a=a: -a)
			add(f"(abs {ea})", lambda a=a: abs(a))
		for width in [0, 1, 2, 5, 12]:
			add(f"resize({ea}, {width})", lambda a=a, w=width: a.resize(w))
		for count in [-19, -2, -1, 0, 1, 2, 19]:
			for symbol in ["sll", "srl", "sla", "sra", "rol", "ror"]:
				add(f"({ea} {symbol} ({count}))", lambda a=a, m=symbol, c=count: getattr(a, m)(c))
			if count >= 0:
				for method in ["shift_left", "shift_right", "rotate_left", "rotate_right"]:
					add(f"{method}({ea}, {count})", lambda a=a, m=method, c=count: getattr(a, m)(c))
		for symbol in ["and", "or", "xor", "nand", "nor", "xnor"]:
			add(f"({symbol} {ea})", lambda a=a, m=symbol: getattr(a, m + "_reduce")())
		for char in "UX01ZWLH-":
			b = Logic(char)
			add(f"({ea} & '{char}')", lambda a=a, b=b: a.concat(b))
			for symbol, function in logical:
				add(f"({ea} {symbol} '{char}')", lambda f=function, a=a, b=b: f(a, b))
				if symbol in ("and", "or", "xor"):
					add(f"('{char}' {symbol} {ea})", lambda f=function, a=a, b=b: f(b, a))
				else:
					add(f"('{char}' {symbol} {ea})", lambda f=function, a=a, b=b: f(a, b))
			for symbol, function in operators[:2]:
				add(f"({ea} {symbol} '{char}')", lambda f=function, a=a, b=b: f(a, b))
				add(f"('{char}' {symbol} {ea})", lambda f=function, a=a, b=b: f(b, a))
		for integer in [-257, -129, -8, -1, 0, 1, 7, 8, 25, 256] if kind is Signed else [0, 1, 7, 8, 25, 256]:
			for symbol, function in operators:
				add(f"({ea} {symbol} ({integer}))", lambda f=function, a=a, i=integer: f(a, i))
				if symbol == "rem":
					add(f"(({integer}) rem {ea})", lambda a=a, i=integer: a.rrem(i))
				else:
					add(f"(({integer}) {symbol} {ea})", lambda f=function, a=a, i=integer: f(i, a))
			for symbol, method in matching:
				add(f"({ea} {symbol} ({integer}))", lambda m=method, a=a, i=integer: getattr(a, m)(i))
	# Width-zero integer conversions are intentional exceptions to range checking.
	for integer in [-100, 0, 100] if kind is Signed else [0, 100]:
		add(
			f"to_{'signed' if kind is Signed else 'unsigned'}({integer}, 0)",
			lambda i=integer: kind.from_int(i, width=0),
		)

	source = (
		_HEADER
		+ "\n".join(
			f'    report "START|{index}"; emit({index}, {expression});' for index, (expression, _, _) in enumerate(rows)
		)
		+ '\n    report "DONE"; wait;\n  end process;\nend;\n'
	)
	path = tmp_path / "numeric_oracle.vhd"
	path.write_text(source, encoding="utf-8")
	for arguments in [["-a", str(path)], ["-e", "numeric_oracle"]]:
		result = subprocess.run(
			["nvc", "--std=2008", "-M", "128m", *arguments],
			cwd=tmp_path,
			capture_output=True,
			text=True,
			timeout=120,
			check=False,
		)
		assert result.returncode == 0, result.stdout + result.stderr
	result = subprocess.run(
		["nvc", "--std=2008", "-M", "128m", "-r", "numeric_oracle", "--stop-time=1ns"],
		cwd=tmp_path,
		capture_output=True,
		text=True,
		timeout=120,
		check=False,
	)
	output = result.stdout + result.stderr
	assert result.returncode == 0, output[-12000:]
	found: dict[int, tuple[str, bool]] = {}
	warned = False
	for line in output.splitlines():
		if "START|" in line:
			warned = False
		elif "RESULT|" in line:
			number, _, value = line.split("RESULT|", 1)[1].partition("|")
			found[int(number)] = (value, warned)
		elif "NUMERIC_STD" in line.upper() and "warning" in line.lower():
			warned = True
	assert len(found) == len(rows), (kind.__name__, seed, len(found), len(rows), output[-4000:])
	mismatches = [
		(expression, found[index], (expected, warning))
		for index, (expression, expected, warning) in enumerate(rows)
		if found[index] != (expected, warning)
	]

	# Narrow, explicit allowances for NVC's null-range discrepancies. Every bit,
	# warning, and non-null range is still checked. Unit tests require IEEE ranges.
	# resize: numeric_std R.1/R.2 return NAS/NAU (0 downto 1), whereas NVC
	# r1.21.1 jit-intrin.c uses newsize-1. Disabling intrinsics tests the body.
	# Concatenation: LRM 9.2.5 says two null arrays yield the right operand;
	# NVC instead constructs 0 to -1. See also nickg/nvc issue #1711.
	def known_null_range(row: tuple[str, tuple[str, bool], tuple[str, bool]]) -> bool:
		expression, (actual, actual_warning), (expected, expected_warning) = row
		if actual_warning != expected_warning:
			return False
		if intrinsics == "1" and expression.startswith("resize(") and expression.endswith(", 0)"):
			return actual == "|-1|false|0" and expected == "|0|false|1"
		if " & " in expression and expected.startswith("|"):
			return actual == "|0|true|-1"
		return False

	unexpected = [row for row in mismatches if not known_null_range(row)]
	assert len(rows) > 8000
	assert not unexpected, f"{kind.__name__}, seed={seed}, {len(unexpected)} mismatches:\n" + "\n".join(
		map(str, unexpected[:20])
	)

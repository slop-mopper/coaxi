-- numeric_dut.vhd
-- SPDX-License-Identifier: CC0-1.0
-- This file was created by an AI model: openai/gpt-6.1-sol

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity numeric_dut is
	port (
		a, b : in signed(7 downto 0);
		u, v : in unsigned(7 downto 0);
		sum_s : out signed(7 downto 0);
		product_s : out signed(15 downto 0);
		sum_u : out unsigned(7 downto 0);
		product_u : out unsigned(15 downto 0);
		logic_s : out signed(7 downto 0);
		shift_s : out signed(7 downto 0)
	);
end entity;

architecture test of numeric_dut is
begin
	sum_s <= a + b;
	product_s <= a * b;
	sum_u <= u + v;
	product_u <= u * v;
	logic_s <= a and b;
	shift_s <= shift_right(a, 2);
end architecture;

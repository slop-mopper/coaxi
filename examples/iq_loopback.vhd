-- iq_loopback.vhd
-- SPDX-License-Identifier: CC0-1.0
-- This file was created by an AI model: openai/gpt-6.2-sol

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package iq_types is
	type iq_t is record
		i : signed(15 downto 0);
		q : signed(15 downto 0);
	end record;
end package;

library ieee;
use ieee.std_logic_1164.all;
use work.iq_types.all;

entity iq_loopback is
	port (
		clk : in std_logic;
		s_tdata : in iq_t;
		s_tvalid, s_tlast : in std_logic;
		s_tready : out std_logic;
		m_tdata : out iq_t;
		m_tvalid, m_tlast : out std_logic;
		m_tready : in std_logic
	);
end entity;

architecture loopback of iq_loopback is
begin
	m_tdata <= s_tdata;
	m_tvalid <= s_tvalid;
	m_tlast <= s_tlast;
	s_tready <= m_tready;
end architecture;

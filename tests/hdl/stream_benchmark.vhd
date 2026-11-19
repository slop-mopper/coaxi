-- stream_benchmark.vhd
-- SPDX-License-Identifier: CC0-1.0
-- This file was created by an AI model: openai/gpt-6.2-sol

library ieee;
use ieee.std_logic_1164.all;

entity stream_benchmark is
end entity;

architecture test of stream_benchmark is
	signal clock, reset : std_logic := '0';
	signal s_tdata, m_tdata : std_logic_vector(15 downto 0) := (others => '0');
	signal s_tvalid, s_tready, s_tlast : std_logic := '0';
	signal m_tvalid, m_tready, m_tlast : std_logic := '0';
	signal occupied : std_logic := '0';
	signal cycles, accepted, retired, first_cycle, last_cycle : natural := 0;
begin
	s_tready <= not occupied or m_tready;
	m_tvalid <= occupied;

	process (clock)
	begin
		if rising_edge(clock) then
			cycles <= cycles + 1;
			if reset = '1' then
				occupied <= '0';
				accepted <= 0;
				retired <= 0;
			else
				if s_tready = '1' then
					occupied <= s_tvalid;
					if s_tvalid = '1' then
						s_tlast_check: assert s_tlast = '0' or s_tlast = '1' severity failure;
						m_tdata <= s_tdata;
						m_tlast <= s_tlast;
						accepted <= accepted + 1;
					end if;
				end if;
				if m_tvalid = '1' and m_tready = '1' then
					if retired = 0 then
						first_cycle <= cycles;
					end if;
					last_cycle <= cycles;
					retired <= retired + 1;
				end if;
			end if;
		end if;
	end process;
end architecture;

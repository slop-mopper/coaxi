-- stream_benchmark.vhd
-- SPDX-License-Identifier: CC0-1.0
-- This file was created by an AI model: openai/gpt-6.2-sol

library ieee;
use ieee.std_logic_1164.all;

entity stream_benchmark is
	generic (
		data_width : positive := 16;
		stall_period : natural := 0;
		check_drive_phase : boolean := false
	);
end entity;

architecture test of stream_benchmark is
	signal clock, reset : std_logic := '0';
	signal s_tdata, m_tdata : std_logic_vector(data_width - 1 downto 0) := (others => '0');
	signal s_tvalid, s_tready, s_tlast : std_logic := '0';
	signal m_tvalid, m_tready, m_tlast : std_logic := '0';
	signal occupied : std_logic := '0';
	signal cycles, accepted, retired, first_cycle, last_cycle : natural := 0;
	signal rising_drives, falling_drives : natural := 0;
	signal first_offer_high, last_clear_high : std_logic := 'X';
	signal first_ready_high, last_ready_clear_high : std_logic := 'X';
begin
	s_tready <= '0' when stall_period /= 0 and cycles mod stall_period = 0
		else not occupied or m_tready;
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
				elsif m_tready = '1' then
					occupied <= '0';
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

	phase_check : if check_drive_phase generate
		process (s_tdata, s_tvalid, s_tlast, m_tready)
		begin
			if now /= 0 ns then
				assert clock'last_event = 0 ns report "stream drive away from a clock edge" severity failure;
				if clock = '1' then
					rising_drives <= rising_drives + 1;
				else
					falling_drives <= falling_drives + 1;
				end if;
				if s_tvalid'event then
					if s_tvalid = '1' and first_offer_high = 'X' then
						first_offer_high <= clock;
					elsif s_tvalid = '0' then
						last_clear_high <= clock;
					end if;
				end if;
				if m_tready'event then
					if m_tready = '1' and first_ready_high = 'X' then
						first_ready_high <= clock;
					elsif m_tready = '0' then
						last_ready_clear_high <= clock;
					end if;
				end if;
			end if;
		end process;
	end generate;
end architecture;

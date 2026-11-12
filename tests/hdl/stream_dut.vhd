-- stream_dut.vhd
-- SPDX-License-Identifier: CC0-1.0
-- This file was created by an AI model: openai/gpt-6.1-sol

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity stream_dut is
end entity;

architecture test of stream_dut is
	type IQ_t is record
		i : signed(15 downto 0);
		q : signed(15 downto 0);
	end record;

	signal beat_clock : std_logic := '0';
	signal wipe_registers : std_logic := '1';
	signal allow_input : std_logic := '0';

	signal s_tdata : std_logic_vector(15 downto 0) := (others => '0');
	signal s_tvalid, s_tready, s_tlast : std_logic := '0';
	signal m_data : std_logic_vector(15 downto 0) := (others => '0');
	signal m_valid, m_ready, m_last : std_logic := '0';
	signal occupied : std_logic := '0';
	signal accepted, retired : natural := 0;

	signal plain_data : std_logic_vector(7 downto 0) := (others => '0');
	signal plain_valid, plain_ready : std_logic := '0';
	signal iq_word_in : IQ_t := (i => (others => '0'), q => (others => '0'));
	signal sample_available, consumer_accepts, end_of_packet : std_logic := '0';
	signal \lane.payload[0]\ : std_logic_vector(7 downto 0) := (others => '0');
	signal \offer-now!\, \take-it?\ : std_logic := '0';

	signal scalar_value : std_logic := '0';
	signal single_clock : std_logic_vector(7 downto 7) := "0";
	signal single_valid : std_logic_vector(2 to 2) := "0";
	signal single_ready : std_logic_vector(4 downto 4) := "0";
	signal single_last : std_logic_vector(9 to 9) := "0";

	signal s_tkeep, m_keep : std_logic_vector(7 downto 6) := "00";
	signal s_tstrb, m_strb : std_logic_vector(3 to 4) := "00";
	signal s_tuser, m_user : std_logic_vector(0 to 4) := "00000";
	signal s_tid, m_id : std_logic_vector(10 downto 0) := (others => '0');
	signal s_tdest, m_dest : std_logic_vector(0 to 8) := (others => '0');
	signal sb_tdata : std_logic_vector(15 downto 0) := (others => '0');
	signal sb_tvalid, sb_tready, sb_tlast : std_logic := '0';
	signal sb_tkeep : std_logic_vector(7 downto 6) := "00";
	signal sb_tstrb : std_logic_vector(3 to 4) := "00";
	signal sb_tuser : std_logic_vector(0 to 4) := "00000";
	signal sb_tid : std_logic_vector(10 downto 0) := (others => '0');
	signal sb_tdest : std_logic_vector(0 to 8) := (others => '0');
	signal byte_keep : std_logic := '0';
	signal byte_strb : std_logic_vector(8 to 8) := "0";
	signal short_data : std_logic_vector(6 downto 0) := (others => '0');
	signal \recover-now!\ : std_logic := '1';
	signal reset_lane : std_logic_vector(5 to 5) := "0";
begin
	s_tready <= allow_input and (not occupied or m_ready);
	m_valid <= occupied;

	process (beat_clock)
	begin
		if rising_edge(beat_clock) then
			if wipe_registers = '1' then
				occupied <= '0';
				m_data <= (others => '0');
				m_last <= '0';
				m_keep <= (others => '0');
				m_strb <= (others => '0');
				m_user <= (others => '0');
				m_id <= (others => '0');
				m_dest <= (others => '0');
				accepted <= 0;
				retired <= 0;
			else
				if s_tready = '1' then
					occupied <= s_tvalid;
					if s_tvalid = '1' then
						m_data <= s_tdata;
						m_last <= s_tlast;
						m_keep <= s_tkeep;
						m_strb <= s_tstrb;
						m_user <= s_tuser;
						m_id <= s_tid;
						m_dest <= s_tdest;
						accepted <= accepted + 1;
					end if;
				elsif m_ready = '1' then
					occupied <= '0';
				end if;
				if m_valid = '1' and m_ready = '1' then
					retired <= retired + 1;
				end if;
			end if;
		end if;
	end process;
end architecture;

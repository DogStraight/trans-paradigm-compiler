/*
 * Copyright (c) 2018, Marcelo Samsoniuk
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * * Redistributions of source code must retain the above copyright notice, this
 *   list of conditions and the following disclaimer.
 *
 * * Redistributions in binary form must reproduce the above copyright notice,
 *   this list of conditions and the following disclaimer in the documentation
 *   and/or other materials provided with the distribution.
 *
 * * Neither the name of the copyright holder nor the names of its
 *   contributors may be used to endorse or promote products derived from
 *   this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

`timescale 1ns / 1ps

// implemented opcodes:

`define LUI     7'b01101_11      // lui   rd,imm[31:12]
`define AUIPC   7'b00101_11      // auipc rd,imm[31:12]
`define JAL     7'b11011_11      // jal   rd,imm[xxxxx]
`define JALR    7'b11001_11      // jalr  rd,rs1,imm[11:0]
`define BCC     7'b11000_11      // bcc   rs1,rs2,imm[12:1]
`define LCC     7'b00000_11      // lxx   rd,rs1,imm[11:0]
`define SCC     7'b01000_11      // sxx   rs1,rs2,imm[11:0]
`define MCC     7'b00100_11      // xxxi  rd,rs1,imm[11:0]
`define RCC     7'b01100_11      // xxx   rd,rs1,rs2
`define SYS     7'b11100_11      // exx, csrxx, mret

// proprietary extension (custom-0)
`define CUS     7'b00010_11      // cus   rd,rs1,rs2,fc3,fct5

// not implemented opcodes:
//`define FCC     7'b00011_11      // fencex


// configuration file

/*
 * Copyright (c) 2018, Marcelo Samsoniuk
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * * Redistributions of source code must retain the above copyright notice, this
 *   list of conditions and the following disclaimer.
 *
 * * Redistributions in binary form must reproduce the above copyright notice,
 *   this list of conditions and the following disclaimer in the documentation
 *   and/or other materials provided with the distribution.
 *
 * * Neither the name of the copyright holder nor the names of its
 *   contributors may be used to endorse or promote products derived from
 *   this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

//`timescale 1ns / 1ps

// to port to a new board, use TESTMODE to test:
// - the reset button is working
// - the LED is blinking at 1Hz
// - the UART is looped
//`define __TESTMODE__

////////////////////////////////////////////////////////////////////////////////
// darkriscv configuration
////////////////////////////////////////////////////////////////////////////////

// pipeline stages:
//
// 2-stage version: core and memory in different clock edges result in less
// clock performance, but less losses when the program counter changes
// (pipeline flush = 1 clock).  Works like a 4-stage pipeline and remember
// the 68040 clock scheme, with instruction per clock = 1.  alternatively,
// it is possible work w/ 1 wait-state and 1 clock edge, but with a penalty
// in performance (instruction per clock = 0.5).
//
// 3-stage version: core and memory in the same clock edge require one extra
// stage in the pipeline, but keep a good performance most of time
// (instruction per clock = 1).  of course, read operations require 1
// wait-state, which means sometimes the read performance is reduced.
`define __3STAGE__

// RV32I vs RV32E:
//
// The difference between the RV32I and RV32E regarding the logic space is
// minimal in typical applications with modern 5 or 6 input LUT based FPGAs,
// but the RV32E is better with old 4 input LUT based FPGAs.
//`define __RV32E__

// BIG-ENDIAN:
//
// Although the core itself is bi-endian, the SoC, peripherals and firmware
// needs to be in sync in order to work correctly, so it is possible 
// enable or disable the big-endian mode, which is usefull for network
// processing and other communication related stuff.
//`define __BIG__

// muti-threading support:
//
// Decreases clock performance by 20% (80MHz), but enables two or more
// contexts (threads) in the core. The threads work in symmetrical way,
// which means that they will start with the same exactly core parameters
// (same initial PC, same initial SP, etc). The boot.s code is designed
// to handle this difference and set each thread to different
// applications.
// Notes:
// a) threading is currently supported only in the 3-stage pipeline version.
// b) the old experimental "interrupt mode" was removed, which means that
//    the multi-thread mode does not make anything "visible" other than
//    increment the oport register.
// c) the threading in the non-interrupt mode switches when the program flow
//    changes, i.e. every jal instruction. When the core is idle, it is
//    probably in a jal loop.
// The number of threads must be 2**n (i.e. THREADS = 3 means 8 threads)
//`define __THREADS__ 3

// coprocessor interface
//
// The coprocessor interface allows to add new instructions to
// the custom-0 opcode without modifying the core itself
// the CPR_REQ is asserted when the custom opcode is matched
// the fct3/fct7 are outputted alongside with rs1/rs2/rd current values
// the RDW is the value written in the next cycle to the target register
// the user may use HLT to implement multi-cycle accelerators
//`define __COPROCESSOR__

`ifdef __COPROCESSOR__

// mac instruction:
//
// The mac instruction is similar to other register to register
// instructions, but with a different opcode 7'h1111111.  the format is mac
// rd,r1,r2, but is not currently possible encode in asm, by this way it is
// available in licb as int mac(int rd, short r1, short r2).  Although it
// can be used to accelerate the mul/div operations, the mac operation is
// designed for DSP applications.  with some effort (low level machine
// code), it is possible peak 100MMAC/s @100MHz.
//`define __MAC16X16__

`endif

// flexbuzz interface (for compatibility):
//
// A new data bus interface similar to a well known c*ldfire bus interface,
// in a way that part of the bus routing is moved to the core, in a way that
// is possible support different bus widths (8, 16 or 32 bit) and endians
// more easily (the new interface is natively big-endian, but the endian can
// be adjusted in the bus interface dinamically).  Similarly to the standard
// 32-bit interface, the external logic must detect the RD/WR operation
// quick enough and assert HLT in order to insert wait-states and perform
// the required multiplexing to fit the DLEN operand size in the data bus
// width available.  As far as other blocks were added, in special
// DarkBridge, DarkRAM and DarkCache, such bus proved not so good, since we
// had to duplicate lots of code on that blocks, so we reverted to the
// previous concept and keep this option only for compatibility.
//`define __FLEXBUZZ__

// CSR support
// 
// enable this to use CSR registers...  INTERRUPT and EBREAK use this in
// order to read some special exception registers.  Also, THREADS use this in
// order to identify the core number.  
//`define __CSR__

`ifdef __CSR__

// Performance Counters
//
// The Performance Counters are a set of 64-bit registers that counts the
//number of clocks and number of instructions executed, so is possible
//measure the core performance.
//`define __CSR_ESSENTIAL__

// interrupt support
//
// The interrupt support in the core uses the machine registers mtvec and
// mepc, which means support the control special register instruction csrrw,
// in a way that is possible read/write the mtvec and mepc.
// the interrupt itself works like the thread switch, with the difference
// that:
// a) the PC will be saved in the mepc register
// b)the PC will receive the mtvec value
// c) single interrupt, which means that the mtvec offset is always zero
// The interrupt support cannot be used with threading (because makes no
// much sense?)... also, it requires the 3 stage pipeline (again, makes no
// much sense use it with the 2-stage pipeline).
//`define __INTERRUPT__

// ebreak support
// 
// ebreak enable live debug w/ gdb, with break points, single-step, etc...
// it basically consists in a single instruction that replace the normal
// instruction, so an exception will be triggered, which is like an interrupt,
// but with no real interrupt source.
//`define __EBREAK__

`endif

// MUL support
//
// experimental and partial M-extension support, MUL/MULH/MULHSU/MULHU
// only...  in case of DIV/REM, trap and emulate by software is the current
// option!
//`define __MEXT__

// DBNZ support
//
// experimental custom instruction that decrement and branch if non-zero,
// found on other popular microprocessors!  as addition, it does not flush
// the pipeline, so it can run 1 or 2 additional instructions without
// performance impact, depending on pipeline length configuration.  as far
// as the tail length depends on pipeline setup, it is highly dependent of
// hand optimizations and must be used very carefuly!
//      jalr = imm[11:0] | rs1 | 000 | rd | 1100111
//      dbnz = imm[11:0] | rs1 | 000 | rd | 1100111, rs1 == rd
// example:
//                      ; x1 = len, x2 = sptr, x3 = dptr
//      loop:
//      lw x4,(x2)          ; x4 = *sptr
//      sw x4,(x3)          ; *dptr = x4
//      .word 0xff8090e7    ; dbnz x1,x1,test
//      addi x2,x2,4        ; sptr++
//      addi x3,x3,4        ; dptr++
//
//`define __DBNZ__

// instruction trace:
//
// prints the PC, the respective instruction and some useful information,
// skipping halt and flush, in order to track the instruction execution
// sequence.  traces are very useful to debug, since is possible dump the
// traces from a working core in order to debug a non-working core.  when
// trace is enabled, the UART print is blocked, also, the trace does not
// dump data when the core is in reset.
// the trace file is stored on "sim/darksocv.txt"
//`define __TRACE__
//`define __TRACEFULL__

// performance measurement:
//
// The performance measurement can be done in the simulation level by
// eabling the __PERFMETER__ define, in order to check how the clock cycles
// are used in the core. The report is displayed when the FINISH_REQ signal
// is actived by the UART.
// the performance counters does not count when the core is in reset.
`define __PERFMETER__

// initial PC
//
// Typically, the PC is set [by HW] to address 0, representing the start of
// ROM memory and the SP is set [by SW] to the final of RAM memory.  In the
// linker, the start of ROM memory matches with the .text area, which is
// defined in the boot.c code and the start of RAM memory matches with the
// .data and other volatile data, in a way that the stack can be positioned
// in the top of RAM and does not match with the .data.
`define __RESETPC__ 32'd0

////////////////////////////////////////////////////////////////////////////////
// darksocv configuration:
////////////////////////////////////////////////////////////////////////////////

// harvard architecture
// 
// darkriscv core is *always* harvard, but it possible multiplex the instr. 
// and data buses over the time on the SoC level, in a way that it mimics a 
// classic von neumann architecture, which is useful for single-port memory, 
// such as SDRAMs, PSRAM, etc. when multiplexed, the instruction fetch turns
// to be very slow, so caches are essential with this scenario!
`define __HARVARD__

// cache depth
// 
// when enabled, the caches will try map and store the read operations, in a 
// way that future read operations in the same address will be faster! it is
// specially applicable to non-harvard SoC configuration, since that the
// harvard SoC configuration is faster than the cache!
// the cache depth N means that the each cache will be 32-bit x 2^N
`ifndef __HARVARD__
    `define __LUTCACHE__
    `define __CDEPTH__ 6
    `define __ICACHE__
    `define __DCACHE__
    `define __RMW_CYCLE__
`endif

// interactive simulation:
//
// When enabled, will trick the simulator in order to enable interactive
// access via the stdin, in a way that is possible type interactive commands,
// which will make your simulator crazy! unfortunately, it works only with
// iverilog... at least, Xilinx ISIM does not liket the $fgetc()
//`define __INTERACTIVE__

// icarus register debug:
//
// As most people observed, the icarus verilog does not dump the register
// bank because icarus does not dump arrays by default. However, it is possible
// activate this special option in order to dump the register bank. This
// makes no effect in other simulators, but it appears as a warning.
//`define __REGDUMP__

// memory size:
//
// The current test firmware requires 8KB of memory, but it depends of the
// memory layout: whenthe I-bus and D-bus are both attached in the same BRAM,
// it is possible assume that 8kB is enough, but when the I-bus and D-bus are
// attached to separate memories, the I-BRAM requires around 5KB and the
// D-BRAM requires about 1.5KB. A safe solution is just simply and set the
// size as the same.
// The size is defined as 2**MLEN, i.e. the address bits used in the memory.
// WARNING: this setup must match with the src/darksocv.ld.src file!
`define MLEN 13 // 13: 8kB for darkshell
                // 15: 32kB, for coremark

// read-modify-write cycle:
//
// Generate RMW cycles when writing in the memory. This option basically
// makes the read and write cycle symmetric and may work better in the cases
// when the 32-bit memory does not support separate write enables for
// separate 16-bit and 8-bit words. Typically, the RMW cycle results in a
// decrease of 5% in the performance (not the clock, but the instruction
// pipeline eficiency) due to memory wait-states.
//`define __RMW_CYCLE__

// bram wait states
// 
// to simulate high latency memories, is possible set the number of wait-states
// for bram here! case not configured, wait-states defaults to 1.
//`define __WAITSTATE__ 3

// UART speed is set in bits per second, typically 115200 bps:
//`define __UARTSPEED__ 115200

// UART queue:
//
// Optional RX/TX queue for communication oriented applications. The concept
// foreseen 256 bytes for TX and RX, in a way that frames up to 128 bytes can
// be easily exchanged via UART. the queue size is defined as 2**N:
//`define __UARTQUEUE__ 8 // not working well, need check...

////////////////////////////////////////////////////////////////////////////////
// board definition:
////////////////////////////////////////////////////////////////////////////////

// The board is automatically defined in the xst/xise files via Makefile or
// ISE. Case it is not the case, please define you board name here:
//`define AVNET_MICROBOARD_LX9
//`define XILINX_AC701_A200
//`define QMTECH_SDRAM_LX16

// the following defines are automatically defined:

`ifdef __ICARUS__
    `define SIMULATION 1
`endif

`ifdef XILINX_ISIM
    `define SIMULATION 2
`endif

`ifdef MODEL_TECH
    `define SIMULATION 3
`endif

`ifdef XILINX_SIMULATOR
    `define SIMULATION 4
`endif

// the board definition is done on the tool, otherwise we assume simulation

`ifdef AVNET_MICROBOARD_LX9
    `define BOARD_ID 1
    //`define BOARD_CK 100000000
    //`define BOARD_CK 66666666
    //`define BOARD_CK 40000000
    // example of DCM logic:
    `define BOARD_CK_REF 100000000
    `define BOARD_CK_MUL 6
    `ifdef __3STAGE__
        `define BOARD_CK_DIV 6 // 3-stage, 1-ws, 9=66MHz 6=100MHz
    `else
        `define BOARD_CK_DIV 9 // 2-stage, 1-ws, 9=66MHz 6=100MHz
    `endif
    `define XILINX6CLK 1
`endif

`ifdef XILINX_AC701_A200
    `define BOARD_ID 2
    //`define BOARD_CK 90000000
    `define BOARD_CK_REF 90000000
    `define BOARD_CK_MUL 4
    `define BOARD_CK_DIV 2
`endif

`ifdef QMTECH_SDRAM_LX16
    `define BOARD_ID 3
    `define BOARD_CK_REF 50000000
    `define BOARD_CK_MUL 4
    `define BOARD_CK_DIV 2
    `define INVRES 1
    `define XILINX6CLK 1
`endif

`ifdef QMTECH_SPARTAN7_S15
    `define BOARD_ID 4
    `define BOARD_CK_REF 50000000
    `define BOARD_CK_MUL 20
    `define BOARD_CK_DIV 10
    `define XILINX7CLK 1
    `define VIVADO 1
    `define INVRES 1
`endif

`ifdef LATTICE_BREVIA2_XP2
    `define BOARD_ID 5
    `define BOARD_CK 50000000
    `define INVRES 1
`endif

`ifdef LATTICE_ECP5_COLORLIGHTI9
    `define LATTICE_ECP5_PLL_REF25MHZ 1
    `define BOARD_ID 14
    `define BOARD_CK 125_000_000 // cause we use a pll with 25MHz ref clks
    `define INVRES 1
`endif

`ifdef LATTICE_ECP5_COLORLIGHTI5
    `define LATTICE_ECP5_PLL_REF25MHZ 1
    `define BOARD_ID 15
    `define BOARD_CK 125_000_000 // cause we use a pll with 25MHz ref clks
    `define INVRES 1
`endif

`ifdef LATTICE_ECP5_ULX3S
    `define LATTICE_ECP5_PLL_REF25MHZ 1
    `define BOARD_ID 16
    `define BOARD_CK 125_000_000 // cause we use a pll with 25MHz ref clks
    `define INVRES 1
`endif

`ifdef LATTICE_ICE40_BREAKOUT_HX8K
    `define BOARD_ID 17
    `define BOARD_CK 65_000_000 // cause we use a pll with 25MHz ref clks
    `define INVRES 1
`endif


`ifdef PISWORDS_RS485_LX9
    `define BOARD_ID 6
    `define BOARD_CK_REF 50000000
    `define BOARD_CK_MUL 4
    `define BOARD_CK_DIV 2
    `define INVRES 1
    `define XILINX6CLK 1
`endif

`ifdef DIGILENT_SPARTAN3_S200
    `define BOARD_ID 7
    `define BOARD_CK 50000000
    `define __RMW_CYCLE__
`endif

`ifdef ALIEXPRESS_HPC40GBE_K420
    `define BOARD_ID 8
    //`define BOARD_CK 200000000
    `define BOARD_CK_REF 100000000
    `define BOARD_CK_MUL 12
    `define BOARD_CK_DIV 5
    `define XILINX7CLK 1
    `define INVRES 1
`endif

`ifdef QMTECH_ARTIX7_A35
    `define BOARD_ID 9
    `define BOARD_CK_REF 50000000
    `define BOARD_CK_MUL 20
    `define BOARD_CK_DIV 10
    `define XILINX7CLK 1
    `define VIVADO 1
    `define INVRES 1
`endif

`ifdef ALIEXPRESS_HPC40GBE_XKCU040
    `define BOARD_ID 10
    //`define BOARD_CK 200000000
    `define BOARD_CK_REF 100000000
    `define BOARD_CK_MUL 8  // x8/2 = 400MHZ (overclock!)
    `define BOARD_CK_DIV 2  // vivado reco. = 250MHz
    `define XILINX7CLK 1
    `define INVRES 1
`endif

`ifdef PAPILIO_DUO_LOGICSTART
    `define BOARD_ID 11
    `define BOARD_CK_REF 32000000
    `define BOARD_CK_MUL 2
    `define BOARD_CK_DIV 2
    `define XILINX6CLK 1
`endif

`ifdef QMTECH_KINTEX7_K325
    `define BOARD_ID 12
    `define BOARD_CK_REF 50000000
    `define BOARD_CK_MUL 20
    `define BOARD_CK_DIV 4
    `define XILINX7CLK 1
    `define INVRES 1
`endif

`ifdef SCARAB_MINISPARTAN6_PLUS_LX9
    `define BOARD_ID 13
    `define BOARD_CK_REF 50000000
    `define BOARD_CK_MUL 4
    `define BOARD_CK_DIV 2
    // `define INVRES 0
    `define XILINX6CLK 1
`endif

`ifdef QMTECH_CYCLONE10_CL016
    `define BOARD_ID 17
    `define BOARD_CK 50000000
	 `define INVRES 1
	 `define MIFBRAM 1
    `define __RMW_CYCLE__
`endif

`ifdef PISSWORDS_CH34X_LX16
    `define BOARD_ID 0 // 18
    `ifdef __3STAGE__
        `define BOARD_CK_REF 50000000
        `define BOARD_CK_MUL 2
        `define BOARD_CK_DIV 2
        `define XILINX6CLK 1
    `else
        `define BOARD_CK 50000000
    `endif
    `define INVRES 1
    // this is the main test board! :D 
    // so I would enable some features directly here:    
    //`define __SDRAM__ 1
    //`define __LUTCACHE__
    //`define __CDEPTH__ 6
    //`define __ICACHE__
    //`define __DCACHE__
    //`undef __HARVARD__
    //`define __MEXT__
`endif

`ifdef MAX1000_MAX10
    `define BOARD_ID 19
    `define BOARD_CK 32000000
`endif

`ifdef DE10NANO_CYCLONEV_MISTER
    `define BOARD_ID 20
    `define BOARD_CK 50000000
`endif

`ifndef BOARD_ID
    `define BOARD_ID 0
    `define BOARD_CK 100000000
    //`define __SDRAM__ 1
`endif

`ifdef BOARD_CK_REF
    `define BOARD_CK (`BOARD_CK_REF * `BOARD_CK_MUL / `BOARD_CK_DIV)
`endif

// darkuart baudrate automtically calculated according to board clock:

`ifndef __UARTSPEED__
  `define __UARTSPEED__ 115200
`endif

`define  __BAUD__ ((`BOARD_CK/`__UARTSPEED__))

// register number depends of CPU type RV32[EI] and number of threads

`ifdef __THREADS__

    `ifdef __RV32E__
        `define RLEN 16*(2**`__THREADS__)
    `else
        `define RLEN 32*(2**`__THREADS__)
    `endif
    
    `define __CSR__ 
`else
    `ifdef __RV32E__
        `define RLEN 16
    `else
        `define RLEN 32
    `endif
`endif

`ifdef __INTERRUPT__
    `define __CSR__
`endif

`ifdef __EBREAK__
    `define __CSR__
`endif


module darkriscv
#(
    parameter CPTR = 0
)
(
    input             CLK,   // clock
    input             RES,   // reset

`ifdef __INTERRUPT__
    input             IRQ,   // interrupt request
`endif

    // instr-bus

    output            IDREQ, // inst req
    output     [31:0] IADDR, // inst addr bus
    input      [31:0] IDATA, // inst data bus
    input             IDACK, // inst ack
    input             IBERR, // inst bus error

    // ddata-bus

    output            DDREQ,// data req
    output     [31:0] DADDR,// data addr bus
    output     [ 2:0] DLEN, // data length
    output     [ 3:0] DBE,  // data byte enable
    output            DRW,  // data read/write
    output            DRD,  // data read
    output            DWR,  // data write
    output     [31:0] DATAO,// data bus (output)
    input      [31:0] DATAI,// data bus (input)
    input             DDACK,// data ack
    input             DBERR,// data bus error
    
`ifdef SIMULATION
    input             ESIMREQ,  // end simulation req
    output reg        ESIMACK = 0,  // end simulation ack
`endif

`ifdef __COPROCESSOR__
    output            CPR_REQ,
    output     [ 2:0] CPR_FCT3,
    output     [ 6:0] CPR_FCT7,
    output     [31:0] CPR_RS1,
    output     [31:0] CPR_RS2,
    output     [31:0] CPR_RDR,
    input      [31:0] CPR_RDW,
    input             CPR_ACK,
`endif

    output [3:0]  DEBUG       // old-school osciloscope based debug! :)
);

    // dummy 32-bit words w/ all-0s and all-1s:

    wire [31:0] ALL0  = 0;
    wire [31:0] ALL1  = -1;

    // core reset logic

    reg XRES = 1;

`ifdef __THREADS__
    reg [`__THREADS__-1:0] TPTR = 0;     // thread ptr
    reg [`__THREADS__-1:0] RESMODE = -1;
`endif

    always@(posedge CLK)
    begin
`ifdef __THREADS__
        RESMODE <= RES ? -1 : RESMODE ? RESMODE-1 : 0;
        XRES <= |RESMODE;
`else
        XRES <= RES;
`endif
    end

    // pipeline flow control when halted (HLT=1)
    
    wire HLT = 
`ifdef __COPROCESSOR__
                (CPR_REQ?!CPR_ACK:0)||  // when CPR_REQ=1, wait CPR_ACK
`endif
                (DDREQ?!DDACK:0)||      // wheh DDREQ=1, wait DDACK
                (IDREQ?!IDACK:0);       // when IDREQ=1, wait IDACK

    // instruction fetch logic

`ifdef __THREADS__
        reg [31:0] IFPC [0:(2**`__THREADS__)-1];        // 32-bit program counter IF stage
`else
        reg [31:0] IFPC;                                // 32-bit program counter IF state
`endif

    assign IDREQ   = !XRES;

    `ifdef __THREADS__
        assign IADDR = IFPC[TPTR];
    `else
        assign IADDR = IFPC;
    `endif

    // switch IDATA according to the endian

`ifdef __BIG__
    wire [31:0] IDATA1 = {IDATA[7:0],IDATA[15:8],IDATA[23:16],IDATA[31:24]};
`else
    wire [31:0] IDATA1 = IDATA;
`endif



    // only for halt control
    reg        HLT2   = 0;
    reg [31:0] IDATA2 = 0;

    always@(posedge CLK)
    begin
        HLT2 <= HLT;
        
        // clock in IDATA2 when HLT transitions
        if(HLT2^HLT) IDATA2 <= IDATA1;
    end

    // HLT-aware instruction data for decode stage
    wire[31:0] IDATAX = XRES ? 0 :
                        HLT2 ? IDATA2 :
                               IDATA1;

    // decode: IDATA is break apart as described in the RV32I specification

`ifdef __3STAGE__

    // eXecute stage instruction data (next pipeline stage)
    reg [31:0] XIDATA;

    reg XLUI, XAUIPC, XJAL, XJALR, XBCC, XLCC, XSCC, XMCC, XRCC, XCUS, XSYS; //, XFCC;

`ifdef __DBNZ__
    reg XDBNZ;
`endif

    reg [31:0] XSIMM;
    reg [31:0] XUIMM;

    always@(posedge CLK)
    begin
        XIDATA <= HLT ? XIDATA : IDATAX;

        XLUI   <= HLT ? XLUI   : IDATAX[6:0]==`LUI;
        XAUIPC <= HLT ? XAUIPC : IDATAX[6:0]==`AUIPC;
        XJAL   <= HLT ? XJAL   : IDATAX[6:0]==`JAL;
`ifdef __DBNZ__
        XJALR  <= HLT ? XJALR  : IDATAX[6:0]==`JALR && IDATAX[14:12]==0;
        XDBNZ  <= HLT ? XDBNZ  : IDATAX[6:0]==`JALR && IDATAX[14:12]==1;
`else
        XJALR  <= HLT ? XJALR  : IDATAX[6:0]==`JALR;
`endif
        XBCC   <= HLT ? XBCC   : IDATAX[6:0]==`BCC;
        XLCC   <= HLT ? XLCC   : IDATAX[6:0]==`LCC;
        XSCC   <= HLT ? XSCC   : IDATAX[6:0]==`SCC;
        XMCC   <= HLT ? XMCC   : IDATAX[6:0]==`MCC;

        XRCC   <= HLT ? XRCC   : IDATAX[6:0]==`RCC;
        XCUS   <= HLT ? XCUS   : IDATAX[6:0]==`CUS;
        //XFCC   <= HLT ? XFCC   : IDATAX[6:0]==`FCC;
        XSYS   <= HLT ? XSYS   : IDATAX[6:0]==`SYS;

        // sign extended immediate, according to the instruction type:

        XSIMM  <= HLT ? XSIMM :
                 IDATAX[6:0]==`SCC ? { IDATAX[31] ? ALL1[31:12]:ALL0[31:12], IDATAX[31:25],IDATAX[11:7] } : // s-type
                 IDATAX[6:0]==`BCC ? { IDATAX[31] ? ALL1[31:13]:ALL0[31:13], IDATAX[31],IDATAX[7],IDATAX[30:25],IDATAX[11:8],ALL0[0] } : // b-type
                 IDATAX[6:0]==`JAL ? { IDATAX[31] ? ALL1[31:21]:ALL0[31:21], IDATAX[31], IDATAX[19:12], IDATAX[20], IDATAX[30:21], ALL0[0] } : // j-type
                 IDATAX[6:0]==`LUI||
                 IDATAX[6:0]==`AUIPC ? { IDATAX[31:12], ALL0[11:0] } : // u-type
                                      { IDATAX[31] ? ALL1[31:12]:ALL0[31:12], IDATAX[31:20] }; // i-type

        // zero-extended (unsigned) immediate, according to the instruction type:

        XUIMM  <= HLT ? XUIMM :
                 IDATAX[6:0]==`SCC ? { ALL0[31:12], IDATAX[31:25],IDATAX[11:7] } : // s-type
                 IDATAX[6:0]==`BCC ? { ALL0[31:13], IDATAX[31],IDATAX[7],IDATAX[30:25],IDATAX[11:8],ALL0[0] } : // b-type
                 IDATAX[6:0]==`JAL ? { ALL0[31:21], IDATAX[31], IDATAX[19:12], IDATAX[20], IDATAX[30:21], ALL0[0] } : // j-type
                 IDATAX[6:0]==`LUI||
                 IDATAX[6:0]==`AUIPC ? { IDATAX[31:12], ALL0[11:0] } : // u-type
                                      { ALL0[31:12], IDATAX[31:20] }; // i-type
    end

    // how many cycles left to start instruction execution
    reg [1:0] FLUSH = -1;  // flush instruction pipeline

`else

    wire [31:0] XIDATA;

    wire XLUI, XAUIPC, XJAL, XJALR, XBCC, XLCC, XSCC, XMCC, XRCC, XCUS, XSYS; //, XFCC, XSYS;

`ifdef __DBNZ__
    reg XDBNZ;
`endif

    wire [31:0] XSIMM;
    wire [31:0] XUIMM;

    assign XIDATA = IDATAX;

    assign XLUI   = IDATAX[6:0]==`LUI;
    assign XAUIPC = IDATAX[6:0]==`AUIPC;
    assign XJAL   = IDATAX[6:0]==`JAL;
`ifdef __DBNZ__
    assign XJALR  = IDATAX[6:0]==`JALR && IDATAX[14:12]==0;
    assign XDBNZ  = IDATAX[6:0]==`JALR && IDATAX[14:12]==1;
`else
    assign XJALR  = IDATAX[6:0]==`JALR;
`endif
    assign XBCC   = IDATAX[6:0]==`BCC;
    assign XLCC   = IDATAX[6:0]==`LCC;
    assign XSCC   = IDATAX[6:0]==`SCC;
    assign XMCC   = IDATAX[6:0]==`MCC;

    assign XRCC   = IDATAX[6:0]==`RCC;
    assign XCUS   = IDATAX[6:0]==`CUS;
    //assign XFCC   <= IDATAX[6:0]==`FCC;
    assign XSYS   = IDATAX[6:0]==`SYS;

    // sign extended immediate, according to the instruction type:

    assign XSIMM  = 
                     IDATAX[6:0]==`SCC ? { IDATAX[31] ? ALL1[31:12]:ALL0[31:12], IDATAX[31:25],IDATAX[11:7] } : // s-type
                     IDATAX[6:0]==`BCC ? { IDATAX[31] ? ALL1[31:13]:ALL0[31:13], IDATAX[31],IDATAX[7],IDATAX[30:25],IDATAX[11:8],ALL0[0] } : // b-type
                     IDATAX[6:0]==`JAL ? { IDATAX[31] ? ALL1[31:21]:ALL0[31:21], IDATAX[31], IDATAX[19:12], IDATAX[20], IDATAX[30:21], ALL0[0] } : // j-type
                     IDATAX[6:0]==`LUI||
                     IDATAX[6:0]==`AUIPC ? { IDATAX[31:12], ALL0[11:0] } : // u-type
                                          { IDATAX[31] ? ALL1[31:12]:ALL0[31:12], IDATAX[31:20] }; // i-type

    // zero-extended (unsigned) immediate, according to the instruction type:

    assign XUIMM  = 
                     IDATAX[6:0]==`SCC ? { ALL0[31:12], IDATAX[31:25],IDATAX[11:7] } : // s-type
                     IDATAX[6:0]==`BCC ? { ALL0[31:13], IDATAX[31],IDATAX[7],IDATAX[30:25],IDATAX[11:8],ALL0[0] } : // b-type
                     IDATAX[6:0]==`JAL ? { ALL0[31:21], IDATAX[31], IDATAX[19:12], IDATAX[20], IDATAX[30:21], ALL0[0] } : // j-type
                     IDATAX[6:0]==`LUI||
                     IDATAX[6:0]==`AUIPC ? { IDATAX[31:12], ALL0[11:0] } : // u-type
                                          { ALL0[31:12], IDATAX[31:20] }; // i-type

    reg FLUSH = -1;  // flush instruction pipeline

`endif

`ifdef __THREADS__
    `ifdef __RV32E__
        wire [`__THREADS__+3:0] DPTR   = XRES ? { RESMODE, 4'd0 } : { TPTR, XIDATA[10: 7] }; // set SP_RESET when RES==1
        wire [`__THREADS__+3:0] S1PTR  = { TPTR, XIDATA[18:15] };
        wire [`__THREADS__+3:0] S2PTR  = { TPTR, XIDATA[23:20] };
    `else
        wire [`__THREADS__+4:0] DPTR   = XRES ? { RESMODE, 5'd0 } : { TPTR, XIDATA[11: 7] }; // set SP_RESET when RES==1
        wire [`__THREADS__+4:0] S1PTR  = { TPTR, XIDATA[19:15] };
        wire [`__THREADS__+4:0] S2PTR  = { TPTR, XIDATA[24:20] };
    `endif
`else
    `ifdef __RV32E__
        wire [3:0] DPTR   = XIDATA[10: 7]; // set SP_RESET when RES==1
        wire [3:0] S1PTR  = XIDATA[18:15];
        wire [3:0] S2PTR  = XIDATA[23:20];
    `else
        wire [4:0] DPTR   = XIDATA[11: 7]; // set SP_RESET when RES==1
        wire [4:0] S1PTR  = XIDATA[19:15];
        wire [4:0] S2PTR  = XIDATA[24:20];
    `endif
`endif

    wire [6:0] OPCODE = FLUSH ? 0 : XIDATA[6:0]; // unused
    wire [2:0] FCT3   = XIDATA[14:12];
    wire [6:0] FCT7   = XIDATA[31:25];

    wire [31:0] SIMM  = XSIMM;
    wire [31:0] UIMM  = XUIMM;

    // main opcode decoder:

    wire    LUI = FLUSH ? 0 : XLUI;   // OPCODE==7'b0110111;
    wire  AUIPC = FLUSH ? 0 : XAUIPC; // OPCODE==7'b0010111;
    wire    JAL = FLUSH ? 0 : XJAL;   // OPCODE==7'b1101111;
    wire   JALR = FLUSH ? 0 : XJALR;  // OPCODE==7'b1100111;
`ifdef __DBNZ__
    wire   DBNZ = FLUSH ? 0 : XDBNZ;  // OPCODE==7'b1100111;
`endif
    wire    BCC = FLUSH ? 0 : XBCC; // OPCODE==7'b1100011; //FCT3
    wire    LCC = FLUSH ? 0 : XLCC; // OPCODE==7'b0000011; //FCT3
    wire    SCC = FLUSH ? 0 : XSCC; // OPCODE==7'b0100011; //FCT3
    wire    MCC = FLUSH ? 0 : XMCC; // OPCODE==7'b0010011; //FCT3

    wire    RCC = FLUSH ? 0 : XRCC; // OPCODE==7'b0110011; //FCT3
    wire    CUS = FLUSH ? 0 : XCUS; // OPCODE==7'b0110011; //FCT3
    //wire    FCC = FLUSH ? 0 : XFCC; // OPCODE==7'b0001111; //FCT3
    wire    SYS = FLUSH ? 0 : XSYS; // OPCODE==7'b1110011; //FCT3



    reg [31:0] REGS [0:`RLEN-1];	// synthesis attribute ram_style of REGS is "distributed";

`ifdef __3STAGE__
    reg [31:0] IDPC;            // 32-bit program counter for ID stage
`else
    `ifdef __THREADS__
        wire [31:0] IDPC = IFPC[TPTR];
    `else
        wire [31:0] IDPC = IFPC;    // 2-stage, combinational ID stage
    `endif
`endif
    reg [31:0] PC;		            // 32-bit program counter for EX stage

`ifdef SIMULATION
    integer i;
    
    initial for(i=0;i!=`RLEN;i=i+1) REGS[i] = 0;
`endif

    // source-1 and source-2 register selection

    wire          [31:0] U1REG = REGS[S1PTR];
    wire          [31:0] U2REG = REGS[S2PTR];
    wire          [31:0] DREG  = REGS[DPTR];

    wire signed   [31:0] S1REG = U1REG;
    wire signed   [31:0] S2REG = U2REG;


    // SL-group of instructions (OPCODE==7'b0100011 for S, OPCODE==7'b0000011 for L)

`ifdef __FLEXBUZZ__

    wire [31:0] LDATA = FCT3[1:0]==0 ? { FCT3[2]==0&&DATAI[ 7] ? ALL1[31: 8]:ALL0[31: 8] , DATAI[ 7: 0] } :
                        FCT3[1:0]==1 ? { FCT3[2]==0&&DATAI[15] ? ALL1[31:16]:ALL0[31:16] , DATAI[15: 0] } :
                                        DATAI;

    wire [31:0] SDATA = U2REG;

`else
    `ifdef __BIG__

        wire [31:0] LDATA = FCT3==0||FCT3==4 ? ( DADDR[1:0]==0 ? { FCT3==0&&DATAI[31] ? ALL1[31: 8]:ALL0[31: 8] , DATAI[31:24] } :
                                                 DADDR[1:0]==1 ? { FCT3==0&&DATAI[23] ? ALL1[31: 8]:ALL0[31: 8] , DATAI[23:16] } :
                                                 DADDR[1:0]==2 ? { FCT3==0&&DATAI[15] ? ALL1[31: 8]:ALL0[31: 8] , DATAI[15: 8] } :
                                                                 { FCT3==0&&DATAI[ 7] ? ALL1[31: 8]:ALL0[31: 8] , DATAI[ 7: 0] } ):
                            FCT3==1||FCT3==5 ? ( DADDR[1]==0   ? { FCT3==1&&DATAI[31] ? ALL1[31:16]:ALL0[31:16] , DATAI[31:16] } :
                                                                 { FCT3==1&&DATAI[15] ? ALL1[31:16]:ALL0[31:16] , DATAI[15: 0] } ) :
                                                 DATAI;

        wire [31:0] SDATA = FCT3==0 ? ( DADDR[1:0]==0 ? { U2REG[ 7: 0], ALL0 [23:0] } :
                                        DADDR[1:0]==1 ? { ALL0 [31:24], U2REG[ 7:0], ALL0[15:0] } :
                                        DADDR[1:0]==2 ? { ALL0 [31:16], U2REG[ 7:0], ALL0[7:0] } :
                                                        { ALL0 [31: 8], U2REG[ 7:0] } ) :
                            FCT3==1 ? ( DADDR[1]==0   ? { U2REG[15: 0], ALL0 [15:0] } :
                                                        { ALL0 [31:16], U2REG[15:0] } ) :
                                        U2REG;

    `else

        wire [31:0] LDATA = FCT3==0||FCT3==4 ? ( DADDR[1:0]==3 ? { FCT3==0&&DATAI[31] ? ALL1[31: 8]:ALL0[31: 8] , DATAI[31:24] } :
                                                 DADDR[1:0]==2 ? { FCT3==0&&DATAI[23] ? ALL1[31: 8]:ALL0[31: 8] , DATAI[23:16] } :
                                                 DADDR[1:0]==1 ? { FCT3==0&&DATAI[15] ? ALL1[31: 8]:ALL0[31: 8] , DATAI[15: 8] } :
                                                                 { FCT3==0&&DATAI[ 7] ? ALL1[31: 8]:ALL0[31: 8] , DATAI[ 7: 0] } ):
                            FCT3==1||FCT3==5 ? ( DADDR[1]==1   ? { FCT3==1&&DATAI[31] ? ALL1[31:16]:ALL0[31:16] , DATAI[31:16] } :
                                                                 { FCT3==1&&DATAI[15] ? ALL1[31:16]:ALL0[31:16] , DATAI[15: 0] } ) :
                                                 DATAI;

        wire [31:0] SDATA = FCT3==0 ? ( DADDR[1:0]==3 ? { U2REG[ 7: 0], ALL0 [23:0] } :
                                        DADDR[1:0]==2 ? { ALL0 [31:24], U2REG[ 7:0], ALL0[15:0] } :
                                        DADDR[1:0]==1 ? { ALL0 [31:16], U2REG[ 7:0], ALL0[7:0] } :
                                                        { ALL0 [31: 8], U2REG[ 7:0] } ) :
                            FCT3==1 ? ( DADDR[1]==1   ? { U2REG[15: 0], ALL0 [15:0] } :
                                                        { ALL0 [31:16], U2REG[15:0] } ) :
                                        U2REG;
    `endif
`endif

    // C-group: CSRRW

    wire EBRK = SYS && FCT3==0 && XIDATA[31:20]==12'b000000000001; // ebreak always decodable, for simulation

    // exceptions

    wire IERR = FLUSH ? 0 : !(XLUI||XAUIPC||XJAL||XJALR||XBCC||XLCC||XSCC||XMCC||XRCC||XCUS||XSYS);

    wire DBER = DBERR;
    wire IBER = IBERR;
    wire DAER = DLEN==2 ? DADDR[0]!=0 : DLEN==4 ? DADDR[1:0]!=0 : 0;
    wire IAER = IADDR[1:0]!=0;

`ifdef __CSR__

    wire CSRX  = SYS && FCT3[1:0];

    `ifdef __INTERRUPT__
        reg [31:0] MSTATUS  = 0;
        reg [31:0] MSCRATCH = 0;
        reg [31:0] MCAUSE   = 0;
        reg [31:0] MEPC     = 0;
        reg [31:0] MTVEC    = 0;
        reg [31:0] MIE      = 0;
        reg [31:0] MIP      = 0;

        wire MRET = SYS && FCT3==0 && XIDATA[31:20]==12'b001100000010;
    `endif

    `ifdef __EBREAK__
        reg [31:0] SSTATUS  = 0;
        reg [31:0] SSCRATCH = 0;
        reg [31:0] SCAUSE   = 0;
        reg [31:0] SEPC     = 0;
        reg [31:0] STVEC    = 0;
        reg [31:0] SIE      = 0;
        reg [31:0] SIP      = 0;

        wire SRET = SYS && FCT3==0 && XIDATA[31:20]==12'b000100000010;
    `endif

    `ifdef __CSR_ESSENTIAL__
		reg [63:0] CSRCLK = 0;
		reg [63:0] CSRINS = 0;
		always@(posedge CLK)
		begin
			if(!XRES)
			begin
				CSRCLK = CSRCLK+1;
				if(!HLT & !(|FLUSH))
					CSRINS = CSRINS+1;
			end
		end
    `endif

    wire [31:0] CRDATA = 
    `ifdef __THREADS__    
                        XIDATA[31:20]==12'hf14 ? { CPTR, TPTR } : // core/thread number
    `else
                        XIDATA[31:20]==12'hf14 ? CPTR  : // core number
    `endif    
    `ifdef __INTERRUPT__
                        XIDATA[31:20]==12'h344 ? MIP      : // machine interrupt pending
                        XIDATA[31:20]==12'h304 ? MIE      : // machine interrupt enable
                        XIDATA[31:20]==12'h341 ? MEPC     : // machine exception PC
                        XIDATA[31:20]==12'h342 ? MCAUSE   : // machine expection cause
                        XIDATA[31:20]==12'h305 ? MTVEC    : // machine vector table
                        XIDATA[31:20]==12'h300 ? MSTATUS  : // machine status
                        XIDATA[31:20]==12'h340 ? MSCRATCH : // machine status
    `endif
    `ifdef __EBREAK__
                        XIDATA[31:20]==12'h144 ? SIP      : // machine interrupt pending
                        XIDATA[31:20]==12'h104 ? SIE      : // machine interrupt enable
                        XIDATA[31:20]==12'h141 ? SEPC     : // machine exception PC
                        XIDATA[31:20]==12'h142 ? SCAUSE   : // machine expection cause
                        XIDATA[31:20]==12'h105 ? STVEC    : // machine vector table
                        XIDATA[31:20]==12'h100 ? SSTATUS  : // machine status
                        XIDATA[31:20]==12'h140 ? SSCRATCH : // machine status
    `endif
    `ifdef __CSR_ESSENTIAL__
						XIDATA[31:20]==12'hC00 ? CSRCLK[31:0]  :
						XIDATA[31:20]==12'hC02 ? CSRINS[31:0]  :
						XIDATA[31:20]==12'hC80 ? CSRCLK[63:32] :
						XIDATA[31:20]==12'hC82 ? CSRINS[63:32] :
    `endif
                                                 0;	 // unknown

    wire [31:0] WRDATA = FCT3[1:0]==3 ? (CRDATA & ~CRMASK) : FCT3[1:0]==2 ? (CRDATA | CRMASK) : CRMASK;
    wire [31:0] CRMASK = FCT3[2] ? XIDATA[19:15] : U1REG;
   
`endif


    // RM-group of instructions (OPCODEs==7'b0010011/7'b0110011), merged! src=immediate(M)/register(R)

    wire signed [31:0] S2REGX = XMCC ? SIMM : S2REG;
    wire        [31:0] U2REGX = XMCC ? SIMM : U2REG;

`ifdef __MEXT__

    wire MEXT = XRCC && FCT7[0];

    wire signed [63:0] MEXT_PROD_SS = S1REG*S2REG; // MUL/MULH
    wire signed [63:0] MEXT_PROD_SU = S1REG*U2REG; // MULHSU
    wire        [63:0] MEXT_PROD_UU = U1REG*U2REG; // MULHU
`endif

    wire [31:0] RMDATA =
`ifdef __MEXT__
                         MEXT ? (
                             FCT3==3'b000 ? MEXT_PROD_SS[31:0]  :           // MUL   -> low 32 bits
                             FCT3==3'b001 ? MEXT_PROD_SS[63:32] :           // MULH
                             FCT3==3'b010 ? MEXT_PROD_SU[63:32] :           // MULHSU
                             FCT3==3'b011 ? MEXT_PROD_UU[63:32] :           // MULHU
                                            32'b0 ) :
`endif
                         FCT3==7 ? U1REG&S2REGX :
                         FCT3==6 ? U1REG|S2REGX :
                         FCT3==4 ? U1REG^S2REGX :
                         FCT3==3 ? U1REG<U2REGX : // unsigned
                         FCT3==2 ? S1REG<S2REGX : // signed
                         FCT3==0 ? (XRCC&&FCT7[5] ? U1REG-S2REGX : U1REG+S2REGX) :
                         FCT3==1 ? S1REG<<U2REGX[4:0] :
                         //FCT3==5 ?
                         !FCT7[5] ? S1REG>>U2REGX[4:0] :
`ifdef MODEL_TECH
                                   -((-S1REG)>>U2REGX[4:0]); // workaround for modelsim
`else
                                   $signed(S1REG>>>U2REGX[4:0]);  // (FCT7[5] ? U1REG>>>U2REG[4:0] :
`endif

`ifdef __COPROCESSOR__
    assign CPR_REQ = CUS;
    assign CPR_FCT3 = FCT3;
    assign CPR_FCT7 = FCT7;
    assign CPR_RS1 = U1REG;
    assign CPR_RS2 = U2REG;
    assign CPR_RDR = DREG;
`endif

    // J/B-group of instructions (OPCODE==7'b1100011)

    wire BMUX       = FCT3==7 && U1REG>=U2REG  || // bgeu
                      FCT3==6 && U1REG< U2REGX || // bltu
                      FCT3==5 && S1REG>=S2REG  || // bge
                      FCT3==4 && S1REG< S2REGX || // blt
                      FCT3==1 && U1REG!=U2REGX || // bne
                      FCT3==0 && U1REG==U2REGX; // beq

    wire [31:0] PCSIMM = PC+SIMM;
    wire        JREQ = JAL||JALR||(BCC && BMUX);
    wire [31:0] JVAL = JALR ? DADDR : PCSIMM; // SIMM + (JALR ? U1REG : PC);

`ifdef __DBNZ__
    wire DBNZT = DBNZ && S1REG!=0; // branch when not zero!
`endif

    always@(posedge CLK)
    begin
`ifdef __3STAGE__
        FLUSH <= XRES ? 2 :         // on reset wait 2 cycles (fill the pipeline)
                  HLT ? FLUSH :     // on halt do nothing
                FLUSH ? FLUSH-1 :   // if-nonzero -> decrement
    `ifdef __EBREAK__
          IERR||DBER||IBER||IAER||DAER ? 2 : // misc errors
                                  EBRK ? 2 : // ebreak jmps to system level, i.e. sepc = PC; PC = stvec
                                  SRET ? 2 : // sret returns from system level, i.e. PC = sepc
    `endif
    `ifdef __INTERRUPT__
                 MRET ? 2 :         // mret returns from interrupt, i.e. PC = mepc
    `endif
                 JREQ ? 2 : 0;      // flush the pipeline! (when jump requested)
`else
        FLUSH <= XRES ? 1 :         // on reset wait 1 cycle
                  HLT ? FLUSH :     // on halt do nothing
                  JREQ;             // flush the pipeline! (or not! when no jump)
`endif

`ifdef __INTERRUPT__

    `ifdef __EBREAK__
        MIP[11] <= IRQ&&MSTATUS[3]&&MIE[11]&&!SIP[1];
    `else
        MIP[11] <= IRQ&&MSTATUS[3]&&MIE[11];
    `endif
    
        if(XRES)
        begin
            MTVEC    <= 0;
            MEPC     <= 0;
            MIE      <= 0;
            MCAUSE   <= 0;
            MSTATUS  <= 0;
            MSCRATCH <= 0;
        end
        else
        if(!HLT && !FLUSH)
        begin
            if(CSRX)
            begin
                case(XIDATA[31:20])
                    12'h300: MSTATUS  <= WRDATA;
                    12'h340: MSCRATCH <= WRDATA;
                    12'h305: MTVEC    <= WRDATA;
                    12'h341: MEPC     <= WRDATA;
                    12'h304: MIE      <= WRDATA;
                endcase
            end
            else
            if(MIP[11] && JREQ)
            begin
                MEPC   <= JVAL;             // interrupt saves the next PC!
                MSTATUS[3] <= 0;            // no interrupts when handling ebreak!
                MSTATUS[7] <= MSTATUS[3];   // copy old MIE bit
                MCAUSE <= 32'h8000000b;     // ext interrupt
            end
            else
            if(MRET)
            begin
                MSTATUS[3] <= MSTATUS[7]; // return last MIE bit
            end
        end
`endif

`ifdef __EBREAK__
   
        if(XRES)
        begin
            STVEC    <= 0;
            SEPC     <= 0;
            SIE      <= 0;
            SIP      <= 0;
            SCAUSE   <= 0;
            SSTATUS  <= 0;
            SSCRATCH <= 0;
        end
        else
        if(!HLT||!FLUSH)
        begin
            if(IAER||IBER||IERR||EBRK||DAER||DBER) // ebreak cannot be blocked!
            begin
                SEPC   <= PC;               // ebreak saves the current PC!
                SSTATUS[1] <= 0;            // no interrupts when handling ebreak!
                SSTATUS[5] <= SSTATUS[1];   // copy old MIE bit
                
                SCAUSE <=      IAER ? 32'd0 :
                               IBER ? 32'd1 :
                               IERR ? 32'd2 :
                               EBRK ? 32'd3 : 
                          DAER&&DRD ? 32'd4 :
                          DBER&&DRD ? 32'd5 :
                          DAER&&DWR ? 32'd6 :
                          DBER&&DWR ? 32'd7 :
                                    -1;
                          
                SIP[1] <= 1;                // set when ebreak!
            end
            else
            if(CSRX)
            begin
                case(XIDATA[31:20])
                    12'h100: SSTATUS  <= WRDATA;
                    12'h140: SSCRATCH <= WRDATA;
                    12'h105: STVEC    <= WRDATA;
                    12'h141: SEPC     <= WRDATA;
                    12'h104: SIE      <= WRDATA;
                endcase
            end
            else
            if(SRET)
            begin
                SSTATUS[3] <= SSTATUS[7]; // return last MIE bit
                SIP[1] <= 0;              //return from ebreak
            end
        end
        
`endif

`ifdef __RV32E__
        REGS[DPTR] <=   XRES||DPTR[3:0]==0 ? 0  :        // reset x0
`else
        REGS[DPTR] <=   XRES||DPTR[4:0]==0 ? 0  :        // reset x0
`endif
                       HLT ? DREG :        // halt
                       LCC ? LDATA :
                     AUIPC ? PCSIMM :
`ifdef __DBNZ__
                    DBNZT ? S1REG-1 :      // DBNZ decrement register
`endif
                      JAL||
                      JALR ? IDPC :
                       LUI ? SIMM :
                  MCC||RCC ? RMDATA:

`ifdef __COPROCESSOR__
                       CUS ? CPR_RDW :
`endif
`ifdef __CSR__
                       CSRX ? CRDATA :
`endif
                             DREG;

    `ifdef __THREADS__

        `ifdef __3STAGE__
            IDPC <= HLT ? IDPC : IFPC[TPTR];
        `endif

        IFPC[XRES ? RESMODE : TPTR] <=  XRES ? `__RESETPC__ :
                                         HLT ? IFPC[TPTR] :   // reset and halt
                                        JREQ ? JVAL :         // jmp/bra
        `ifdef __DBNZ__
                                       DBNZT ? JVAL :      // dbnz
        `endif
                                               IFPC[TPTR]+4;  // normal flow

        TPTR <= XRES ? 0 : HLT ? TPTR : JAL /*JREQ*/ ? TPTR+1 : TPTR;
                 //TPTR==0/*&& IREQ*/&&JREQ ? 1 :         // wait pipeflush to switch to irq
                 //TPTR==1/*&&!IREQ*/&&JREQ ? 0 : TPTR;  // wait pipeflush to return from irq

    `else
        `ifdef __3STAGE__
            IDPC <= HLT ? IDPC : IFPC;
        `endif

        IFPC <=  XRES ? `__RESETPC__ : HLT ? IFPC :   // reset and halt
        `ifdef __EBREAK__
                     SRET ? SEPC :  // return from system call
                     STVEC&&
                     (IAER||
                     IBER||
                     IERR||
                     EBRK||
                     DAER||
                     DBER) ? STVEC : // ebreak causes an system call                     
        `endif

        `ifdef __INTERRUPT__
                     MRET ? MEPC :  // return from interrupt
                    MIP[11]&&
                    JREQ ? MTVEC : // pending interrupt + pipeline flush
        `endif
                     JREQ ? JVAL :                    // jmp/bra
        `ifdef __DBNZ__
                    DBNZT ? JVAL :                    // dbnz
        `endif
                            IFPC+4;                   // normal flow

    `endif

        PC   <= HLT ? PC : IDPC; // EX stage program counter
    end

    // IO and memory interface

    assign DATAO = SDATA;
    assign DADDR = U1REG + SIMM;

    // based in the Scc and Lcc

    assign DRW      = !SCC;
    assign DLEN[0] = (SCC||LCC)&&FCT3[1:0]==0; // byte
    assign DLEN[1] = (SCC||LCC)&&FCT3[1:0]==1; // word
    assign DLEN[2] = (SCC||LCC)&&FCT3[1:0]==2; // long

`ifdef __BIG__

    assign DBE = FCT3==0||FCT3==4 ? ( DADDR[1:0]==0 ? 4'b1000 : // sb/lb
                                      DADDR[1:0]==1 ? 4'b0100 :
                                      DADDR[1:0]==2 ? 4'b0010 :
                                                      4'b0001 ) :
                 FCT3==1||FCT3==5 ? ( DADDR[1]==0   ? 4'b1100 : // sh/lh
                                                      4'b0011 ) :
                                                      4'b1111; // sw/lw
`else
    assign DBE = FCT3==0||FCT3==4 ? ( DADDR[1:0]==3 ? 4'b1000 : // sb/lb
                                      DADDR[1:0]==2 ? 4'b0100 :
                                      DADDR[1:0]==1 ? 4'b0010 :
                                                      4'b0001 ) :
                 FCT3==1||FCT3==5 ? ( DADDR[1]==1   ? 4'b1100 : // sh/lh
                                                      4'b0011 ) :
                                                      4'b1111; // sw/lw
`endif

    assign DWR     = SCC;
    assign DRD     = LCC;
    assign DDREQ   = SCC||LCC;

    
`ifdef __INTERRUPT__
    assign DEBUG = { IRQ, MIP, MIE, MRET };
`else
    assign DEBUG = { XRES, |FLUSH, SCC, LCC };
`endif

`ifdef SIMULATION

    `ifdef __PERFMETER__

        integer clocks=0, running=0, load=0, store=0, flush=0, halt=0;

    `ifdef __THREADS__
        integer thread[0:(2**`__THREADS__)-1],curtptr=0,cnttptr=0;
        integer j;

        initial for(j=0;j!=(2**`__THREADS__);j=j+1) thread[j] = 0;
    `endif

        always@(posedge CLK)
        begin
            if(!XRES)
            begin
                clocks = clocks+1;

                if(HLT)
                begin
                         if(SCC)	store = store+1;
                    else if(LCC)	load  = load +1;
                    else 		halt  = halt +1;
                end
                else
                if(|FLUSH)
                begin
                    flush=flush+1;
                end
                else
                begin

        `ifdef __THREADS__
                    for(j=0;j!=(2**`__THREADS__);j=j+1)
                            thread[j] = thread[j]+(j==TPTR?1:0);

                    if(TPTR!=curtptr)
                    begin
                        curtptr = TPTR;
                        cnttptr = cnttptr+1;
                    end
        `endif
                    running = running +1;
                end

                if(ESIMREQ)
                begin
                    $display("****************************************************************************");
                    $display("DarkRISCV Pipeline Report (%0d clocks, %0d instr, CPI = %.2f):",
                        clocks,running,1.0*clocks/running);

                    $display("core%0d: %0d%% run, %0d%% wait (%0d%% i-bus, %0d%% d-bus/rd, %0d%% d-bus/wr), %0d%% flush",
                        CPTR,
                        100.0*running/clocks,
                        100.0*(load+store+halt)/clocks,
                        100.0*halt/clocks,
                        100.0*load/clocks,
                        100.0*store/clocks,
                        100.0*flush/clocks);

         `ifdef __THREADS__
                    for(j=0;j!=(2**`__THREADS__);j=j+1) $display("  thread%0d: %0d%% running",j,100.0*thread[j]/clocks);

                    $display("%0d thread switches, %0d clocks/threads",cnttptr,clocks/cnttptr);
         `endif
                    $display("****************************************************************************");
                    $finish();
                end
            end
        `ifndef __EBREAK__
            if(!HLT&&!FLUSH&&EBRK)
            begin
                $display("breakpoint at %x",PC);
                $stop();
            end
        `endif        
            if(!HLT && !FLUSH && (XIDATA===32'dx || XIDATA[6:0]==0))
            begin
                $display("invalid XIDATA=%x at %x %s",XIDATA,PC,XIDATA[6:0]==0?"(check for ENDIAN on rtl/config.vh and src/config.mk)":"");
                $finish();  
            end
            
            if(LCC&&!HLT&&!FLUSH&&( (DLEN==4 && DATAI[31:0]===32'dx)||
                                    (DLEN==2 && DATAI[15:0]===16'dx)||
                                    (DLEN==1 && DATAI[ 7:0]=== 8'dx)))
            begin
                $display("invalid DATAI@%x at %x",DADDR,PC);
                $finish();
            end
            
        `ifdef __TRACE__
            if(!XRES)
            begin
            `ifdef __TRACEFULL__
                if(FLUSH)
                    $display("trace: %x:%x       flushed",PC,XIDATA);
                else
                if(HLT)
                begin
                    //$display("%x:%x       %s halted       %x:%x",PC,XIDATA,LCC?"lx":"sx",DADDR,LCC?LDATA:DATAO);
                    $display("trace: %x:%x       halted",PC,XIDATA);
                end
                else
            `else
                if(!FLUSH && !HLT)
            `endif
                begin
                    case(XIDATA[6:0])
                        `LUI:     $display("trace: %x:%x lui   %%x%0x,%0x",                PC,XIDATA,DPTR,$signed(SIMM));
                        `AUIPC:   $display("trace: %x:%x auipc %%x%0x,PC[%0x]",            PC,XIDATA,DPTR,$signed(SIMM));
                        `JAL:     $display("trace: %x:%x jal   %%x%0x,%0x",                PC,XIDATA,DPTR,$signed(SIMM));
                        `JALR:    $display("trace: %x:%x jalr  %%x%0x,%%x%0x,%0d",         PC,XIDATA,DPTR,S1PTR,$signed(SIMM));
                        `BCC:     $display("trace: %x:%x bcc   %%x%0x,%%x%0x,PC[%0d]",     PC,XIDATA,S1PTR,S2PTR,$signed(SIMM));
                        `LCC:     $display("trace: %x:%x lx    %%x%0x,%%x%0x[%0d]\t%x:%x",  PC,XIDATA,DPTR,S1PTR,$signed(SIMM),DADDR,LDATA);
                        `SCC:     $display("trace: %x:%x sx    %%x%0x,%%x%0x[%0d]\t%x:%x",  PC,XIDATA,DPTR,S1PTR,$signed(SIMM),DADDR,DATAO);
                        `MCC:     $display("trace: %x:%x alui  %%x%0x,%%x%0x,%0d",         PC,XIDATA,DPTR,S1PTR,$signed(SIMM));
                        `RCC:     $display("trace: %x:%x alu   %%x%0x,%%x%0x,%%x%0x",      PC,XIDATA,DPTR,S1PTR,S2PTR);
                        `SYS:     $display("trace: %x:%x sys   (no decode)",               PC,XIDATA);
                        `CUS:     $display("trace: %x:%x cus   (no decode)",               PC,XIDATA);
                        default:  $display("trace: %x:%x ???   (no decode)",               PC,XIDATA);
                    endcase
                end
            end        
        `endif
        
        end

    `else
        always@(posedge CLK) if(ESIMREQ) ESIMACK <= 1;
    `endif


`endif

endmodule

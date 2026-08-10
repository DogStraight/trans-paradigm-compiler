`define ENABLED
`ifdef ENABLED
`define CHOSEN 1
`else
`define REJECTED 2
`endif

module m;
    wire a;
endmodule

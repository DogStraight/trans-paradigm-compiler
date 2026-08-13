`define OPT1

module m;
    `ifdef OPT1
        wire sel1;
    `elsif OPT2
        wire sel2;
    `else
        wire sel3;
    `endif
endmodule

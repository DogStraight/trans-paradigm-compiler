`define A

module m;
    `ifdef A
        wire a;
        `ifdef B
            wire b;
        `else
            wire b2;
        `endif
    `else
        wire a2;
    `endif
endmodule

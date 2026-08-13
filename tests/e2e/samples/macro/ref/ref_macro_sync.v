`define W 8
`define BW 8
module sync_test(
    input [`W-1:0] addr,       // macro W → 8, sync: "["
    output [`BW-1:0] data,     // macro BW → 8, sync: "["
    output [7:0] literal       // literal 7:0, NOT a macro
);
    wire [`W-1:0] sig_a;       // macro W → 8, sync: "["
    wire [`BW-1:0] sig_b;      // macro BW → 8, sync: "["
    assign sig_a = `W'd0;      // macro W → 8, sync: "="
    assign sig_b = `BW'd0;     // macro BW → 8, sync: "="
endmodule

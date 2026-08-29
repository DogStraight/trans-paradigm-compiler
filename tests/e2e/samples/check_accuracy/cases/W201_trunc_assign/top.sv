module top (
    input  wire [11:0] data_i,
    output wire [7:0]  out_o
);
    assign out_o = data_i;  // 12 位 → 8 位截断
endmodule

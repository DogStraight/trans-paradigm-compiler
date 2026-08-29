module top (
    input  wire [11:0] data_i,
    output wire [7:0]  out_o
);
    assign out_o[3:0] = data_i;  // LHS 位选 4 位 < 12 位截断
endmodule

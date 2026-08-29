module top (
    input  wire [7:0]  a_i,
    output wire [11:0] out_o
);
    assign out_o = a_i;  // 8 位 → 12 位扩展（安全，不报）
endmodule

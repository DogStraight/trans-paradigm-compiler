module top (
    input  wire [7:0] a_i,
    output reg  [3:0] q_r
);
    always @(*) q_r = a_i;  // 8 位 → 4 位截断（阻塞赋值）
endmodule

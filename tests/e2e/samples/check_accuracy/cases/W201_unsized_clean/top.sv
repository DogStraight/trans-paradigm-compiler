module top (
    input  wire       clk_i,
    input  wire [7:0] a_i,
    output reg  [7:0] acc_r
);
    always @(posedge clk_i) begin
        acc_r <= acc_r + 1;  // unsized 常数 → RHS 未知，保守不报
    end
    always @(*) begin
        acc_r = a_i;  // 等宽
    end
endmodule

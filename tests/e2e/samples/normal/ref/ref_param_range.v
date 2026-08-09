// Test: parameter with range [msb:lsb] — 来自 picorv32 特征
// picorv32 大量使用 parameter [ 0:0] NAME = val 带范围声明
module param_range #(
    parameter [ 0:0] A = 1,
    parameter [31:0] B = 32'h 0000_0000,
    parameter [ 7:0] C = 8'h ff
) (
    input clk
);
    always @(posedge clk) begin
    end
endmodule

// Test 4: 纯组合逻辑 — 多操作、连续赋值
// 功能: 位宽转换 + 算术运算
module alu #( parameter W = 8 )(
    input wire [W - 1:0] a,
    input wire [W - 1:0] b,
    input wire [2:0] op,
    output reg [W - 1:0] result,
    output reg zero,
    output reg overflow);

    wire [W - 1:0] sum;
    wire [W - 1:0] diff;
    wire [W - 1:0] and_w;
    wire [W - 1:0] or_w;
    wire [W - 1:0] xor_w;
    assign sum = a + b;
    assign diff = a - b;
    assign and_w = a & b;
    assign or_w = a | b;
    assign xor_w = a ^ b;
    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    case (op)
        3'd0: if (/* ERROR: result = sum ; */) /* ERROR: result = sum ; */
        3'd1: if (/* ERROR: result = diff ; */) /* ERROR: result = diff ; */
        3'd2: if (/* ERROR: result = and_w ; */) /* ERROR: result = and_w ; */
        3'd3: if (/* ERROR: result = or_w ; */) /* ERROR: result = or_w ; */
        3'd4: if (/* ERROR: result = xor_w ; */) /* ERROR: result = xor_w ; */
        default: if (/* ERROR: result = { W { 1'b0 } } ; */) /* ERROR: result = { W { 1'b0 } } ; */
    endcase
    zero = (result == {W{1'b0}});
    overflow = (a[W - 1] == b[W - 1]) && (result[W - 1] != a[W - 1]);
    /* ERROR: end */
endmodule

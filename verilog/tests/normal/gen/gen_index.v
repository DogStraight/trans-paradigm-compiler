// Test: IndexedId 数组索引
// 功能: 使用索引表达式读取
module index_test(
    input wire [7:0] data,
    input wire [2:0] idx,
    output reg [7:0] out);

    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    out = data[idx];
    /* ERROR: end */
endmodule

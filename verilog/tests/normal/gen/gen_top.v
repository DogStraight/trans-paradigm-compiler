// Test 3: 带接口的模块 — 多层次模块实例化
// 功能: 顶层模块，实例化子模块
module sub_adder (
input wire [7:0] a
,
input wire [7:0] b
,
input wire ci
,
output wire [7:0] sum
,
output wire co
) ;
assign {co, sum} = a + b + ci;
endmodule
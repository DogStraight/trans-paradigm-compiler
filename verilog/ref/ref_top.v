// Test 3: 带接口的模块 — 多层次模块实例化
// 功能: 顶层模块，实例化子模块

module sub_adder (
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire       ci,
    output wire [7:0] sum,
    output wire       co
);

    assign {co, sum} = a + b + ci;

endmodule


module top #(
    parameter DATA_WIDTH = 8
)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire [DATA_WIDTH-1:0] a,
    input  wire [DATA_WIDTH-1:0] b,
    output wire [DATA_WIDTH-1:0] result
);

    wire [DATA_WIDTH-1:0] sum_wire;
    wire                  co_wire;

    sub_adder #(
        .WIDTH(DATA_WIDTH)
    ) u_adder (
        .a(a),
        .b(b),
        .ci(1'b0),
        .sum(sum_wire),
        .co(co_wire)
    );

    assign result = sum_wire;

endmodule

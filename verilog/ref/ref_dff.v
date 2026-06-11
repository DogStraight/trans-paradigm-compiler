// Test 5: 最小模块 — 仅端口和连续赋值
// 功能: 简单的 D 触发器

module dff (
    input  wire clk,
    input  wire rst_n,
    input  wire d,
    output reg  q
);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            q <= 1'b0;
        else
            q <= d;
    end

endmodule

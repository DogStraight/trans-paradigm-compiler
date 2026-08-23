// edge clean（fuzz 回归 2026-08-22）: 空参数列表 #() —— 曾解析不了（ParameterList
// 的 ParamDecl 必需）导致静默截断；修复后必须成功。
`timescale 1 ns / 1 ps
module timescale_test #() (
    input clk
);
    always @(posedge clk) begin
    end
endmodule

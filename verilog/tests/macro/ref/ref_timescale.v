// Test: `timescale directive at top level — 来自 picorv32 特征
`timescale 1 ns / 1 ps

module timescale_test #() (
    input clk
);
    always @(posedge clk) begin
    end
endmodule

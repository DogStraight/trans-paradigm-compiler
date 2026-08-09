// Test: hex number literal with space between base and value — 来自 picorv32 特征
// picorv32 使用 32'h ffff_ffff 格式（'h 后跟空格再跟数值）
module param_hex_space #(
    parameter [31:0] MASK = 32'h ffff_ffff,
    parameter [31:0] ADDR = 32'h 0000_0010,
    parameter [31:0] DATA = 32'h dead_beef
)( input clk);

    always @(posedge clk) begin
    end
    
endmodule

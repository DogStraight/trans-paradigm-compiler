// generate 语法测试
/* ERROR: module generate_test # ( */
parameter DATA_WIDTH = 8
/* ERROR: , */
parameter NUM_STAGES = 4
/* ERROR: ) ( */
input wire clk
/* ERROR: , */
input wire [DATA_WIDTH - 1:0] data_in
/* ERROR: , */
output wire [DATA_WIDTH - 1:0] data_out
/* ERROR: ) ; */
wire [DATA_WIDTH - 1:0] pipe[0:NUM_STAGES - 1];
// generate for: 流水线寄存器 — 逐级传递
/* ERROR: generate */
genvar g;
for (g = 0; g < NUM_STAGES; g = g + 1) 
    if (/* ERROR: begin : stage */) /* ERROR: begin : stage */
if (g == 0) begin
    assign pipe[g] = data_in;
end
else if (/* ERROR: begin */) /* ERROR: begin */
assign pipe[g] = pipe[g - 1];
/* ERROR: end */
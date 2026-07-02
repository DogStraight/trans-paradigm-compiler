// complex_pipeline_processor.v
// 复杂流水线处理器，包含 generate 结构、函数、任务、内存阵列
/* ERROR: module complex_pipeline_processor # ( */
parameter DATA_WIDTH = 8
/* ERROR: , */
parameter NUM_STAGES = 4
/* ERROR: , */
parameter MEM_DEPTH = 16
/* ERROR: ) ( */
input wire clk
/* ERROR: , */
input wire rst_n
/* ERROR: , */
input wire start
/* ERROR: , */
input wire [DATA_WIDTH - 1:0] data_in
/* ERROR: , */
output reg done
/* ERROR: , */
output reg [DATA_WIDTH - 1:0] result
/* ERROR: ) ; */
// ********** 函数和任务声明 (可综合) **********
// 函数: 奇偶校验
function automatic parity( input [DATA_WIDTH - 1:0] d);
    integer j;
    reg p;
    begin
        p = 1'b0;
        for (j = 0; j < DATA_WIDTH; j = j + 1) 
            if (/* ERROR: p = p ^ d [ j ] ; */) /* ERROR: p = p ^ d [ j ] ; */
        parity = p;
    end
endfunction

// 任务: 交换两个信号
task automatic swap(
    input reg [DATA_WIDTH - 1:0] a, b,
    output reg [DATA_WIDTH - 1:0] swapped_a,
    output reg [DATA_WIDTH - 1:0] swapped_b);
    begin
        swapped_a = b;
        swapped_b = a;
    end
endtask

// ********** 参数本地重定义 **********
localparam STAGES = (NUM_STAGES < 2) ? 2 : NUM_STAGES;
localparam LOG2_MEM = $clog2(MEM_DEPTH);
// ********** 所有 reg 声明均带初始值 **********
reg [1:0] state = 2'b0;
reg [1:0] next_state = 2'b0;
reg [STAGES - 1:0] valid_pipe = {STAGES{1'b0}};
reg [DATA_WIDTH - 1:0] data_pipe[0:STAGES - 1];
reg [LOG2_MEM - 1:0] mem_addr = {LOG2_MEM{1'b0}};
reg [DATA_WIDTH - 1:0] mem_read = {DATA_WIDTH{1'b0}};
reg [DATA_WIDTH - 1:0] mem_write = {DATA_WIDTH{1'b0}};
reg mem_we = 1'b0;
reg [DATA_WIDTH - 1:0] internal_reg = {DATA_WIDTH{1'b0}};
reg [DATA_WIDTH - 1:0] swapped_reg_a = {DATA_WIDTH{1'b0}};
reg [DATA_WIDTH - 1:0] swapped_reg_b = {DATA_WIDTH{1'b0}};
reg [3:0] cycle_cnt = 4'd0;
// 二维内存阵列 (初始值全部为0)
reg [DATA_WIDTH - 1:0] memory[0:MEM_DEPTH - 1];
integer i;
// 内存初始化 (可综合复位)
always @(posedge clk or negedge rst_n) if (/* ERROR: begin */) /* ERROR: begin */
if (!rst_n) begin
    for (i = 0; i < MEM_DEPTH; i = i + 1) 
        if (/* ERROR: memory [ i ] <= { DATA_WIDTH { 1'b0 } } ; */) /* ERROR: memory [ i ] <= { DATA_WIDTH { 1'b0 } } ; */
end
else if (/* ERROR: end */) /* ERROR: end */
// ********** generate 结构: 产生多个数据复制模块 **********
// 位宽扩展模块 (组合逻辑)
wire [DATA_WIDTH * 2 - 1:0] duplicated_data[0:STAGES - 1];
/* ERROR: generate */
genvar g;
for (g = 0; g < STAGES; g = g + 1) 
    if (/* ERROR: begin : dup_gen */) /* ERROR: begin : dup_gen */
// 使用函数计算奇偶位并扩展
assign duplicated_data[g] = {{(DATA_WIDTH){parity(data_pipe[g])}},
    data_pipe[g]};
/* ERROR: end */
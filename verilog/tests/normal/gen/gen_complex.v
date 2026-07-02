// complex_pipeline_processor.v
// 复杂流水线处理器，包含 generate 结构、函数、任务、内存阵列
module complex_pipeline_processor #(
    parameter DATA_WIDTH = 8,
    parameter NUM_STAGES = 4,
    parameter MEM_DEPTH = 16
)(
    input wire clk,
    input wire rst_n,
    input wire start,
    input wire [DATA_WIDTH - 1:0] data_in,
    output reg done,
    output reg [DATA_WIDTH - 1:0] result);

    // ********** 函数和任务声明 (可综合) **********
    // 函数: 奇偶校验
    function automatic parity ( input [ DATA_WIDTH - 1 : 0 ] d ) ;
    integer j;
    reg p;
    begin
    p = 1'b0;
    for (j = 0; j < DATA_WIDTH; j = j + 1) 
        p = p ^ d[j];
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
        always @(posedge clk or negedge rst_n) begin
            if ( ! rst_n ) begin
            for (i = 0; i < MEM_DEPTH; i = i + 1) 
                memory[i] <= {DATA_WIDTH{1'b0}};
        end
        
        // ********** generate 结构: 产生多个数据复制模块 **********
        // 位宽扩展模块 (组合逻辑)
        wire [DATA_WIDTH * 2 - 1:0] duplicated_data[0:STAGES - 1];
        generate
            genvar g;
            for ( g = 0 ; g < STAGES ; g = g + 1 ) begin : dup_gen
            // 使用函数计算奇偶位并扩展
            assign duplicated_data[g] = {{(DATA_WIDTH){parity(data_pipe[g])}},
                data_pipe[g]};
            end
            endgenerate
            // 条件生成: 若 DATA_WIDTH > 4 则生成额外的校验逻辑
            generate
                if ( DATA_WIDTH > 4 ) begin : wide_data_gen
                wire [DATA_WIDTH - 1:0] parity_bus;
                assign parity_bus = {DATA_WIDTH{duplicated_data[0][DATA_WIDTH * 2 - 1]}};
                end else begin : narrow_data_gen
                // 空占位
                wire dummy = 1'b0;
                end
                endgenerate
                // ********** 状态机定义 **********
                localparam IDLE = 2'b00,
                    FETCH = 2'b01,
                    PROCESS = 2'b10,
                    WRITEBACK = 2'b11;
                // 状态寄存器
                always @ ( posedge clk or negedge rst_n ) begin
                if ( ! rst_n ) state <= IDLE ;
                else state <= next_state ;
                end
                // 次态逻辑
                always @ ( * ) begin
                next_state = state;
                case (state)
                    IDLE: if (start)
                        next_state = FETCH;
                    FETCH: next_state = PROCESS;
                    PROCESS: if (cycle_cnt == 4'd5)
                        next_state = WRITEBACK;
                    WRITEBACK: next_state = IDLE;
                    default: next_state = IDLE;
                endcase
                end
                // ********** 流水线寄存器 (带初始值) **********
                integer p;
                always @ ( posedge clk or negedge rst_n ) begin
                if ( ! rst_n ) begin
                valid_pipe <= {STAGES{1'b0}};
                for (p = 0; p < STAGES; p = p + 1) 
                    data_pipe[p] <= {DATA_WIDTH{1'b0}};
                end else begin
                // 移位流水线
                valid_pipe <= {valid_pipe[STAGES - 2:0],
                    (state == FETCH)};
                for (p = 0; p < STAGES - 1; p = p + 1) 
                    data_pipe[p + 1] <= data_pipe[p];
                if ( state == FETCH )
                data_pipe[0] <= data_in;
                end
                end
                // ********** 内存读写逻辑 **********
                always @ ( posedge clk or negedge rst_n ) begin
                if ( ! rst_n ) begin
                mem_addr <= {LOG2_MEM{1'b0}};
                mem_we <= 1'b0;
                mem_write <= {DATA_WIDTH{1'b0}};
                mem_read <= {DATA_WIDTH{1'b0}};
                end else begin
                // 写内存 (地址由流水线末级数据决定)
                if ( state == PROCESS && valid_pipe [ STAGES - 1 ] ) begin
                mem_addr <= data_pipe[STAGES - 1][LOG2_MEM - 1:0];
                mem_write <= data_pipe[STAGES - 1];
                mem_we <= 1'b1;
                end else begin
                mem_we <= 1'b0;
                end
                // 读内存 (组合后寄存器)
                mem_read <= memory[mem_addr];
                end
                end
                // 实际内存写入 (单独 always，确保写入正确)
                always @ ( posedge clk ) begin
                if ( mem_we )
                memory[mem_addr] <= mem_write;
                end
                // ********** 使用任务进行计算 **********
                always @ ( posedge clk or negedge rst_n ) begin
                if ( ! rst_n ) begin
                internal_reg <= {DATA_WIDTH{1'b0}};
                swapped_reg_a <= {DATA_WIDTH{1'b0}};
                swapped_reg_b <= {DATA_WIDTH{1'b0}};
                end else if ( state == PROCESS ) begin
                // 调用任务交换两个寄存器值
                swap(internal_reg,
                    mem_read,
                    swapped_reg_a,
                    swapped_reg_b);
                // 使用函数计算奇偶并更新内部寄存器
                internal_reg <= {parity(swapped_reg_a),
                    swapped_reg_b[DATA_WIDTH - 2:0]};
                end
                end
                // ********** 计数器 **********
                always @ ( posedge clk or negedge rst_n ) begin
                if ( ! rst_n )
                cycle_cnt <= 4'd0;
                else if ( state == PROCESS )
                cycle_cnt <= cycle_cnt + 4'd1;
                else
                cycle_cnt <= 4'd0;
                end
                // ********** 输出逻辑 **********
                always @ ( posedge clk or negedge rst_n ) begin
                if ( ! rst_n ) begin
                result <= {DATA_WIDTH{1'b0}};
                done <= 1'b0;
                end else if ( state == WRITEBACK ) begin
                result <= internal_reg;
                done <= 1'b1;
                end else begin
                done <= 1'b0;
                end
                end
            endgenerate
            
        endgenerate
        
    endtask
    
endmodule

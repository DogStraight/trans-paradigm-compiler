// generate 语法测试
module generate_test #(
    parameter DATA_WIDTH = 8,
    parameter NUM_STAGES = 4
)(
    input wire clk,
    input wire [DATA_WIDTH - 1:0] data_in,
    output wire [DATA_WIDTH - 1:0] data_out);

    wire [DATA_WIDTH - 1:0] pipe[0:NUM_STAGES - 1];
    // generate for: 流水线寄存器 — 逐级传递
    generate
        genvar g;
        for (g = 0; g < NUM_STAGES; g = g + 1) 
            begin: stage
                if (g == 0) begin
                    assign pipe[g] = data_in;
                end else begin
                    assign pipe[g] = pipe[g - 1];
                end
            end
    endgenerate
    
    // generate if/else: 根据位宽选择输出级
    generate
        if (DATA_WIDTH > 8) begin: wide
            assign data_out = pipe[NUM_STAGES - 1];
        end else begin: narrow
            assign data_out = pipe[0];
        end
    endgenerate
    
endmodule

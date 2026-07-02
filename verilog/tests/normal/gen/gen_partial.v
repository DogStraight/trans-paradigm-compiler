module complex_partial #(
    parameter DATA_WIDTH = 8,
    parameter NUM_STAGES = 4,
    parameter MEM_DEPTH = 16
)( input wire clk);

    localparam STAGES = (NUM_STAGES < 2) ? 2 : NUM_STAGES;
    localparam LOG2_MEM = $clog2(MEM_DEPTH);
    // 函数声明
    function automatic parity ( input [ DATA_WIDTH - 1 : 0 ] d ) ;
    reg p;
    begin
    p = 1'b0;
    parity = p;
    end
    endfunction
    // 任务声明
    task automatic swap(
        input reg [DATA_WIDTH - 1:0] a, b,
        output reg [DATA_WIDTH - 1:0] swapped_a,
        output reg [DATA_WIDTH - 1:0] swapped_b);
        begin
        swapped_a = b;
        swapped_b = a;
        end
        endtask
        reg [1:0] state = 2'b0;
        reg [3:0] cycle_cnt = 4'd0;
        integer i;
        always @(posedge clk or negedge rst_n) begin
            if ( ! rst_n ) begin
            for (i = 0; i < MEM_DEPTH; i = i + 1) 
                cycle_cnt <= 4'd0;
        end
        
        endmodule
    endtask
    
endmodule

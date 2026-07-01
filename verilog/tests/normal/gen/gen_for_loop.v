// Test: for 循环 + integer 声明 + 索引
// 功能: 优先级编码器
module priority_encoder(
    input wire [7:0] req,
    output reg [2:0] code,
    output reg valid);

    integer i;
    always @(*) begin
        code = 3'd0;
        valid = 1'b0;
        for (i = 0; i < 8; i = i + 1) 
            begin
                if (req[i]) begin
                    code = i;
                    valid = 1'b1;
                end
            end
    end
    
endmodule

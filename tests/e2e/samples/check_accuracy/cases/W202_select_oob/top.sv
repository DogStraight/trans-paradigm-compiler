module top;
    wire [7:0] vec;
    wire [15:0] c;
    assign vec = 8'd0;
    assign c = vec[15:0];  // 位选越界（8 位信号选 16 位范围）
endmodule

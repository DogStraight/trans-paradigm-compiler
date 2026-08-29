module top;
    wire [7:0] vec;
    wire c;
    assign vec = 8'd0;
    assign c = vec[8];  // 单索引越界（合法范围 0-7）
endmodule

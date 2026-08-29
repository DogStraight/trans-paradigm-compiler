module top (
    input wire [3:0] idx_i,
    output wire [7:0] out_o
);
    wire [7:0] vec;
    wire [7:0] c1;
    wire [7:0] c2;
    assign vec = 8'd0;
    assign c1 = vec[3:0];
    assign c2 = vec[0:7];
    assign out_o = vec[idx_i];  // 变量索引
endmodule

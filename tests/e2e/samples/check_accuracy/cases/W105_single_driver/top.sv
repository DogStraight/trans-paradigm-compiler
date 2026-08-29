module top (
    input  wire [3:0] a_i,
    input  wire [3:0] b_i,
    output wire [3:0] sum_o
);
    wire [3:0] sum_w;
    assign sum_w = a_i + b_i;
    assign sum_o = sum_w;
endmodule

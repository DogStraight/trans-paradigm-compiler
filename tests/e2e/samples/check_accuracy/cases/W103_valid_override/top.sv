module top(
    input  wire [15:0] a_i,
    input  wire [15:0] b_i,
    output wire [15:0] y_o
);
    adder #(.WIDTH(16)) u_adder (.a(a_i), .b(b_i), .y(y_o));
endmodule

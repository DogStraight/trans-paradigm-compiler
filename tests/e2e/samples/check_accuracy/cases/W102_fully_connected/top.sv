module top(
    input  wire [7:0] a_i,
    input  wire [7:0] b_i,
    output wire [7:0] y_o
);
    adder u_adder (.a(a_i), .b(b_i), .y(y_o));
endmodule

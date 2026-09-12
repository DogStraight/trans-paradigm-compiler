module top(
    input  wire [7:0] a_i,
    input  wire [7:0] b_i
);
    adder u_adder (.a(a_i), .b(b_i), .y(8'hFF));
endmodule

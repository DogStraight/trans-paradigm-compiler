module top;
    wire [7:0] a_sig;
    wire [7:0] b_sig;
    wire [7:0] y_sig;
    tri  io_tri;
    adder u_adder (
        .a_i(a_sig),
        .b_i(b_sig),
        .y_o(y_sig),
        .io_pin(io_tri)
    );
endmodule

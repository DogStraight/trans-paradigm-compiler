module top;
    wire [7:0] a_sig;
    wire [7:0] b_sig;
    adder u_adder (
        .a_i(a_sig),
        .b_i(b_sig)
    );
endmodule

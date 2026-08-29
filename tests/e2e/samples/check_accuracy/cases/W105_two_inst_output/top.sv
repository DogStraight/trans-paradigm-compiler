module top;
    wire [7:0] shared_w;
    adder u1 (.y_o(shared_w));
    adder u2 (.y_o(shared_w));
endmodule

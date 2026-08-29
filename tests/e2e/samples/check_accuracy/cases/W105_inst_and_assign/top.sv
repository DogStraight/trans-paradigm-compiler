module top;
    wire [7:0] shared_w;
    assign shared_w = 8'd1;
    adder u_adder (.y_o(shared_w));
endmodule

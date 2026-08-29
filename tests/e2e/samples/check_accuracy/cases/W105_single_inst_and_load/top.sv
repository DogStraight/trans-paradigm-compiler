module top (
    output wire [7:0] rdata_o
);
    wire [7:0] rdata_w;
    adder u1 (.y_o(rdata_w));
    assign rdata_o = rdata_w;
endmodule

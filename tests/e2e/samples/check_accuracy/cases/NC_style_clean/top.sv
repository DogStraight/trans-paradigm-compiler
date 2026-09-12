module top(
    input  wire a_i,
    output wire y_o
);
    wire data_w;

    assign data_w = a_i;
    assign y_o = data_w;
endmodule

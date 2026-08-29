module adder (
    input  wire [7:0] a_i,
    input  wire [7:0] b_i,
    output wire [7:0] y_o,
    inout  tri         io_pin
);
    assign y_o = a_i + b_i;
endmodule

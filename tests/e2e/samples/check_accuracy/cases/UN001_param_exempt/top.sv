module top #(
    parameter WIDTH = 8
) (
    input wire [WIDTH-1:0] a_i,
    output wire [WIDTH-1:0] y_o
);
    assign y_o = a_i;
endmodule

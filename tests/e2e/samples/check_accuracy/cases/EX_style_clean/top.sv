module top #(
    parameter [3:0] WIDTH = 4
)(
    input  wire [3:0] a,
    output wire [3:0] b
);
    assign b = a;
endmodule

module top #(
    parameter WIDTH = 8
)();
    localparam GOOD_LOCAL = 1;
    genvar I;

    generate
        for (I = 0; I < 4; I = I + 1) begin: g
        end
    endgenerate
endmodule

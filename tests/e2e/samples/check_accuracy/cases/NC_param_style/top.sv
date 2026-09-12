module top #(
    parameter width = 8
)();
    localparam bad_local = 1;
    genvar i;

    generate
        for (i = 0; i < 4; i = i + 1) begin: g
        end
    endgenerate
endmodule

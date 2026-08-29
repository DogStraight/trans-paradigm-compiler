module arbiter (
    input  wire req_a_i,
    input  wire req_b_i,
    output wire grant_o,
    output wire grant_sel
);
    wire grant_a;
    wire grant_b;
    assign grant_a = req_a_i;
    assign grant_b = req_b_i;
    assign grant_sel = grant_a | grant_b;
    assign grant_o = grant_sel;
endmodule

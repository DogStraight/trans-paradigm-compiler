module bus_ctrl (
    input  wire       clk_i,
    input  wire       rst_n_i,
    input  wire [7:0] addr_i,
    output wire [7:0] rdata_o
);
    wire [7:0] wdata_w;
    wire       we_w;
    wire [7:0] rdata_w;
    wire       grant_sel_w;
    wire       unused_legacy_w;
    reg  [7:0] reserved_r;

    reg_if u_reg (
        .clk_i(clk_i),
        .rst_n_i(rst_n_i),
        .addr_i(addr_i),
        .wdata_i(wdata_w),
        .we_i(we_w),
        .rdata_o(rdata_w)
    );
    arbiter u_arb (
        .req_a_i(wdata_w[0]),
        .req_b_i(we_w),
        .grant_o(grant_sel_w)
    );
    assign wdata_w = 8'h00;
    assign we_w = 1'b0;
    assign grant_sel_w = 1'b0;
    assign rdata_o = rdata_w;
endmodule

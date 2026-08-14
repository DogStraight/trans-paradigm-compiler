module nested_test(
    input clk,
    input rstn,
    wrap.slave wrap_in
);

endmodule

type wrap {
    slave : input upstream_tvalid, input upstream_tready, output upstream_tdata, output upstream_tkeep, output downstream_tvalid, output downstream_tready, input downstream_tdata, input downstream_tkeep;
}

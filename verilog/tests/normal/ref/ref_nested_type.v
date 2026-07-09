type axis {
    master : input tvalid, tready, output tdata, tkeep;
    slave : invert master;
}

type wrapper {
    master : axis.master upstream, axis.slave downstream;
}

module nested_test (
    input clk,
    input rstn,
    wrapper.master wrap_in
);
endmodule

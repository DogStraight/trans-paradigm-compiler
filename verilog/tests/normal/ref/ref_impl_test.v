module top();
    impl spi_master #(.MODE(0)) spi_inst (.clk(clk), .rst_n(rst_n));
endmodule

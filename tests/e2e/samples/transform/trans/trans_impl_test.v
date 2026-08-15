module top();

    spi_master spi_inst (
        .clk  (clk  ),
        .rst_n(rst_n)
    );

endmodule

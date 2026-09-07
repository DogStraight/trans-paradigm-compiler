module top(
    input clk,
    spi.master spi_io
);
    impl nosuch.master (.clk(clk)) => spi_io;
endmodule

type spi {
    master : input clk;
    slave  : input clk;
}

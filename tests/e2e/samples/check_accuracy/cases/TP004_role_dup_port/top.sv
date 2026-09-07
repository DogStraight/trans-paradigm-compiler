module top(
    input clk,
    spi.master spi_io
);
    impl spi.master (.clk(clk)) => spi_io;
endmodule

type spi {
    master : input clk, input clk;
    slave  : input clk;
}

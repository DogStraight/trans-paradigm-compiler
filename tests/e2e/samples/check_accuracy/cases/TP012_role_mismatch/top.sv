module top(
    input clk,
    spi.slave spi_io
);
    impl spi.master (.clk(clk)) => spi_io;
endmodule

type spi {
    master : input clk, output mosi;
    slave  : input clk, input mosi;
}

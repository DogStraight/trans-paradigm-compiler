module top(
    input clk,
    spi.master spi_io
);
    impl spi.master (.clk(clk)) => spi_io;
    impl spi.master (.clk(clk), .cs(cs_n)) => spi_io;
endmodule

type spi {
    master : input clk, output mosi, output cs;
    slave  : input clk, input mosi, output cs;
}

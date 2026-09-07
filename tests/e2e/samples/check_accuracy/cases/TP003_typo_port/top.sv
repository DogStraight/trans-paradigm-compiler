module top(
    input clk,
    spi.master spi_io
);
    impl spi.master (.clk(clk), .mosi_typo(data)) => spi_io;
endmodule

type spi {
    master : input clk, output mosi, output cs;
    slave  : input clk, input mosi, output cs;
}

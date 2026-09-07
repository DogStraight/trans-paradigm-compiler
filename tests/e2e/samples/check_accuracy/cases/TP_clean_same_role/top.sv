module top(
    input clk,
    spi.master spi_io
);
    impl spi.master (.clk(clk), .mosi(data), .cs(cs_n)) => spi_io;
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : input clk, input [7:0] mosi, output cs;
}

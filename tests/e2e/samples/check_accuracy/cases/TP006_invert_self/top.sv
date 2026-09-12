module top(
    input clk,
    spi.slave spi_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : invert slave;
}

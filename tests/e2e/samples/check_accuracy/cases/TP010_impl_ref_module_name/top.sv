module top(
    input clk,
    spi.master spi_io
);
    impl spi.master (.clk(clk)) => top;
endmodule

type spi {
    master : input clk, output mosi;
    slave  : input clk, input mosi;
}

module top(
    input clk,
    spi.master spi_io
);
    impl sci.master (.clk(clk)) => spi_io;
endmodule

type spi {
    master : input clk, output mosi;
    slave  : input clk, input mosi;
}

type sci {
    master : input clk, output tx;
    slave  : input clk, input tx;
}

module spi_invoker(
    input clk,
    input rstn,
    output spi_io_miso,
    input spi_io_clk,
    input spi_io_mosi,
    input spi_io_cs,
    output reg [7:0] spi_data,
    output reg spi_data_en);

    always @(posedge clk) begin
        if (!rstn) begin
            spi_data <= 8'b0;
            spi_data_en <= 1'b0;
        end else begin
            spi_data <= spi_data + 1'b1;
            spi_data_en <= 1'b1;
        end
    end
    
endmodule

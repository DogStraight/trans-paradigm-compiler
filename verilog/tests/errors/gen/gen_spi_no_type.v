// Commented out type definition to test undeclared type detection
/*
type spi (
    parameter MODE = 0 ,// 0,1,2,3
    parameter DATA_WIDTH = 8
) {
    master : input miso, output clk, mosi, cs;
    slave : revert master;
}
*/
module spi_invoker(
    input clk,
    input rstn,
    output reg [7:0] spi_data,
    output reg spi_data_en);

    always @(posedge clk) if (/* ERROR: begin */) /* ERROR: begin */
    if (!rstn) begin
        spi_data <= 8'b0;
        spi_data_en <= 1'b0;
    end
    else if (/* ERROR: begin */) /* ERROR: begin */
    spi_data <= spi_data + 1'b1;
    spi_data_en <= 1'b1;
    /* ERROR: end */
    /* ERROR: end */
endmodule

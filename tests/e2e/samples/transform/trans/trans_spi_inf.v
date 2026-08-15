module spi_invoker(
    input clk,
    input rstn,
    input  spi_io_miso,
    output spi_io_sck,
    output spi_io_mosi,
    output spi_io_cs,
    output reg [7:0] spi_data,
    output reg spi_data_en);

    // 通过 impl 绑定 spi_master 包装模块
    // spi_io 为 spi.master 类型，=> 表示自动连线
    spi_master u_spi_master_acb99d (
        .clk(clk),
        .rst_n(rstn),
        .data_in(spi_data),
        .data_in_en(spi_data_en),
        .data_out(spi_data),
        .data_out_en(spi_data_en),
        .miso(spi_io_miso),
        .sck(spi_io_sck),
        .mosi(spi_io_mosi),
        .cs(spi_io_cs)
    );
    
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

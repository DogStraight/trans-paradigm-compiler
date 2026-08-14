module spi_invoker(
    input clk,
    input rstn,
    spi.slave spi_io,
    output reg [7:0] spi_data,
    output reg spi_data_en);

    // 通过 impl 绑定 spi_master 包装模块
    // data input
    // spi_io 为 slave 角色端口，自动连线
    impl spi.master (
        .clk(clk),
        // data output
        .rst_n(rstn),
        .data_in(spi_data),
        .data_in_en(spi_data_en),
        // MODE 感知：CPOL 为 SCK idle 电平, CPHA 为采样边沿
        .data_out(spi_data),
        .data_out_en(spi_data_en)
    ) => spi_invoker;

    always @(posedge clk) begin
        if (!rstn) begin
            spi_data <= 8'b0;
            spi_data_en <= 1'b0;
        end else begin
            spi_data <= spi_data + 1'b1;
            // Stage 1: State register + SCK toggle + data shift
            spi_data_en <= 1'b1;
        end
    end

endmodule

// SCK 相位：在 TRANS 状态每个 clk 交替
// Stage 2: Next state logic
// Stage 3: Output logic (combinational)

type spi {
    master : input clk, input rst_n, input data_in, input data_in_en, output data_out, output data_out_en;
    slave  : input miso, output sck, output mosi, output cs;
}

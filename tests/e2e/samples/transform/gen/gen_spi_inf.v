module spi_invoker(
    input clk,
    input rstn,
    input spi_io_miso,
    output spi_io_sck,
    output spi_io_mosi,
    output spi_io_cs,
    output reg [7:0] spi_data,
    output reg spi_data_en);

    // 通过 impl 绑定 spi_master 包装模块
    // data input 
    // spi_io 为 spi.slave 类型，=> 表示自动连线
    spi_master u_spi_master_acb99d (
        // data output 
        .clk(clk),
        .rst_n(rstn),
        .data_in(spi_data),
        .data_in_en(spi_data_en),
        .data_out(spi_data),
        //   MODE[0] = CPHA (采样边沿: 0=首沿, 1=尾沿)
        .data_out_en(spi_data_en)
    );
    // ── 三段式 SPI Master FSM (MODE 感知) ──
    //   MODE[1] = CPOL (SCK idle level)
    
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
// SCK 在 idle 输出 cpol，TRANS 时按 sck_phase 分频
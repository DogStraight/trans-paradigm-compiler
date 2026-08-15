type spi (parameter MODE = 0, parameter DATA_WIDTH = 8) {
    master : input miso, output sck, mosi, cs;
    slave : invert master;

    impl[master](
        input clk,
        input rst_n,

        // data input 
        input [DATA_WIDTH-1:0] data_in,
        input data_in_en,

        // data output 
        output reg [DATA_WIDTH-1:0] data_out = {DATA_WIDTH{1'b0}},
        output reg data_out_en = 1'b0
    ){
        // ── 三段式 SPI Master FSM (MODE 感知) ──
        //   MODE[1] = CPOL (SCK idle level)
        //   MODE[0] = CPHA (采样边沿: 0=首沿, 1=尾沿)
        localparam IDLE = 2'b00;
        localparam TRANS = 2'b01;
        localparam DONE  = 2'b10;

        reg [1:0] state, next;
        reg [3:0] bit_cnt;
        reg [DATA_WIDTH-1:0] sreg;
        wire cpol = MODE[1];
        wire cpha = MODE[0];

        // Stage 1: State register + SCK toggle + data shift
        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                state <= IDLE;
                bit_cnt <= 0;
                sreg <= 0;
            end else begin
                state <= next;
                // SCK 分频：在 TRANS 状态每个 clk 周期翻转一次
                if (state == IDLE && data_in_en) begin
                    sreg <= data_in;
                    bit_cnt <= DATA_WIDTH - 1;
                end else if (state == TRANS && sck_phase) begin
                    sreg <= {sreg[DATA_WIDTH-2:0], miso};
                    if (bit_cnt != 0) bit_cnt <= bit_cnt - 1;
                end
            end
        end

        // SCK 相位：在 TRANS 状态每个 clk 交替
        reg sck_phase;
        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                sck_phase <= 1'b0;
            end else if (state == TRANS) begin
                sck_phase <= ~sck_phase;
            end else begin
                sck_phase <= 1'b0;
            end
        end

        // Stage 2: Next state logic
        always @(*) begin
            next = state;
            case (state)
                IDLE:   if (data_in_en) next = TRANS;
                TRANS:  if (bit_cnt == 0 && sck_phase) next = DONE;
                DONE:   next = IDLE;
            endcase
        end

        // Stage 3: Output logic (combinational)
        assign cs    = (state == IDLE || state == DONE);
        // SCK 在 idle 输出 cpol，TRANS 时按 sck_phase 分频
        assign sck   = (state == TRANS) ? (sck_phase ? cpol : ~cpol) : cpol;
        // MOSI 在 sck_phase 为低时更新（CPHA=0 领先半周期）
        assign mosi  = (state == TRANS) ? sreg[DATA_WIDTH-1] : 1'b0;

        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                data_out <= 0;
                data_out_en <= 1'b0;
            end else if (state == DONE) begin
                data_out <= sreg;
                data_out_en <= 1'b1;
            end else begin
                data_out_en <= 1'b0;
            end
        end
    }
}

module spi_invoker (
    input clk,
    input rstn,
    spi.master spi_io,
    output reg [7:0] spi_data,
    output reg spi_data_en
);
    // 通过 impl 绑定 spi_master 包装模块
    // spi_io 为 spi.master 类型，=> 表示自动连线
    impl spi.master #(.MODE(0), .DATA_WIDTH(8)) (
        .clk(clk),
        .rst_n(rstn),
        .data_in(spi_data),
        .data_in_en(spi_data_en),
        .data_out(spi_data),
        .data_out_en(spi_data_en)
    ) => spi_io;

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

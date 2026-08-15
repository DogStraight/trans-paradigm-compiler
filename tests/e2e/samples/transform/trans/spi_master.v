module spi_master #(
    parameter MODE = 0,
    parameter DATA_WIDTH = 8
)(
    input miso,
    output sck,
    output mosi,
    output cs,
    input clk,
    input rst_n,
    input [DATA_WIDTH - 1:0] data_in,
    input data_in_en,
    output reg [DATA_WIDTH - 1:0] data_out = {DATA_WIDTH{1'b0}},
    output reg data_out_en = 1'b0);

    localparam IDLE = 2'b00;
    localparam TRANS = 2'b01;
    localparam DONE = 2'b10;
    reg [1:0] state, next;
    reg [3:0] bit_cnt;
    reg [DATA_WIDTH - 1:0] sreg;
    wire cpol = MODE[1];
    wire cpha = MODE[0];
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
                if (bit_cnt != 0)
                    bit_cnt <= bit_cnt - 1;
            end
        end
    end
    
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
    
    always @(*) begin
        next = state;
        case (state)
            IDLE: if (data_in_en)
                next = TRANS;
            TRANS: if (bit_cnt == 0 && sck_phase)
                next = DONE;
            DONE: next = IDLE;
        endcase
    end
    
    assign cs = (state == IDLE || state == DONE);
    assign sck = (state == TRANS) ? (sck_phase ? cpol : ~cpol) : cpol;
    assign mosi = (state == TRANS) ? sreg[DATA_WIDTH-1] : 1'b0;
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
    
endmodule

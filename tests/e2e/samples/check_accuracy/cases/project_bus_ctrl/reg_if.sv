module reg_if (
    input  wire        clk_i,
    input  wire        rst_n_i,
    input  wire [7:0]  addr_i,
    input  wire [7:0]  wdata_i,
    input  wire        we_i,
    output reg  [7:0]  rdata_o
);
    reg [7:0] reg_a;
    reg [7:0] reg_b;
    always @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            reg_a <= 8'd0;
            reg_b <= 8'd0;
        end else if (we_i) begin
            case (addr_i)
                8'h00: reg_a <= wdata_i;
                8'h04: reg_b <= wdata_i;
            endcase
        end
    end
    assign rdata_o = (addr_i == 8'h00) ? reg_a : reg_b;
endmodule

module top (
    input  wire clk_i,
    input  wire rst_n_i,
    output reg  out_q
);
    wire data_w;
    reg  count_r;
    integer loop_i;

    assign data_w = clk_i;
    always @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            count_r <= 1'b0;
            out_q <= 1'b0;
        end else begin
            count_r <= data_w;
            out_q <= count_r;
        end
    end
    always @(posedge clk_i) begin
        loop_i <= loop_i + 1;
    end
endmodule

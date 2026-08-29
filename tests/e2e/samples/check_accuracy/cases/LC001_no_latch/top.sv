module top (
    input  wire clk_i,
    input  wire rst_n_i,
    input  wire en_i,
    output reg  out_r,
    output reg  q_r
);
    always @(*) begin
        if (en_i) begin
            out_r = 1'b1;
        end else begin
            out_r = 1'b0;
        end
    end
    always @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            q_r <= 1'b0;
        end
    end
endmodule

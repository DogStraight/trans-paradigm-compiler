`define W 8
module conflict_test(
    input clk,
    input rstn,
    input [`W-1:0] din,     // macro use: W→8
    output reg [7:0] dout    // literal 8 — should NOT become `W
);
    always @(posedge clk) begin
        if (!rstn)
            dout <= `W'd0;    // macro use: W→8
        else
            dout <= 8'd0;     // literal 8 — should NOT become `W
    end
endmodule

`define WIDTH 8
`include "defs.vh"
module counter(
    input clk,
    input rstn,
    output reg [`WIDTH-1:0] count
);
    always @(posedge clk) begin
        if (!rstn)
            count <= `WIDTH'b0;
        else
            count <= count + 1'b1;
    end
endmodule

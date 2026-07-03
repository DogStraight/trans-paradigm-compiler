module top(
    input clk,
    output reg [`W-1:0] data
);
    always @(posedge clk) begin
        data <= `W'b0;
    end
endmodule

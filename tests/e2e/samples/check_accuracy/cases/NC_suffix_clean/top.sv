module top(
    input  wire data_i,
    output wire result_o,
    output reg  y_r
);
    wire temp_w;

    assign temp_w = data_i;
    assign result_o = temp_w;
    always @(*) begin
        y_r = 1'b0;
    end
endmodule

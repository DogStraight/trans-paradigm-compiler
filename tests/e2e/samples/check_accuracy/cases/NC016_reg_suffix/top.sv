module top(
    output wire result_o
);
    reg y_w;

    always @(*) begin
        y_w = 1'b0;
    end
    assign result_o = y_w;
endmodule

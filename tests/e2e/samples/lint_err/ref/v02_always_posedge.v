module m(input clk, input rst);
    reg x;
    always @(posedge clk or posedge rst) begin
        if (rst)
            x <= 1'b0;
        else
            x <= 1'b1;
    end
endmodule

module top (
    input  wire [1:0] sel_i,
    output reg  [3:0] out_r
);
    always @(*) begin
        casez (sel_i)
            2'b0?: out_r = 4'd0;
        endcase
    end
endmodule

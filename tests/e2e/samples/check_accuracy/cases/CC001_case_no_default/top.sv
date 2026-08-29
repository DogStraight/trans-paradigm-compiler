module top (
    input  wire [1:0] sel_i,
    output reg  [3:0] out_r
);
    always @(*) begin
        case (sel_i)
            2'b00: out_r = 4'd0;
            2'b01: out_r = 4'd1;
            2'b10: out_r = 4'd2;
        endcase
    end
endmodule

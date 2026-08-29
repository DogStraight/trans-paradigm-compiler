module top (
    input  wire en_i,
    output reg  out_r
);
    always @(*) begin
        if (en_i) begin
            out_r = 1'b1;
        end
    end
endmodule

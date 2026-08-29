module top (
    input  wire a_i,
    input  wire b_i,
    output reg  out_r
);
    always @(a_i or b_i) begin
        if (a_i) begin
            out_r = b_i;
        end
    end
endmodule

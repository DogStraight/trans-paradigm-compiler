module top(
    input  wire a,
    input  wire b,
    output reg  y
);
    always @(*) begin
        y = a;
        y <= b;
    end
endmodule

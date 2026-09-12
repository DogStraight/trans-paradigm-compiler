module top(
    input  wire A_IN,
    output wire Y_OUT
);
    reg  Q_BAD;
    wire DATA_BUS;

    always @(*) begin
        Q_BAD = A_IN;
    end
    assign DATA_BUS = Q_BAD;
    assign Y_OUT = DATA_BUS;
endmodule

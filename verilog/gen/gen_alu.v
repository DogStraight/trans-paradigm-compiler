module alu #(parameter W = 8) (input wire [W - 1:0] a,
input wire [W - 1:0] b,
input wire [2:0] op,
output reg [W - 1:0] result,
output reg zero,
output reg overflow);
    wire [W - 1:0] sum;
    wire [W - 1:0] diff;
    wire [W - 1:0] and_w;
    wire [W - 1:0] or_w;
    wire [W - 1:0] xor_w;
    assign sum = a + b;
    assign diff = a - b;
    assign and_w = a & b;
    assign or_w = a | b;
    assign xor_w = a ^ b;
    always @(*) begin
        case (op)
            3'd0: result = sum;
            3'd1: result = diff;
            3'd2: result = and_w;
            3'd3: result = or_w;
            3'd4: result = xor_w;
            default: result = {W{1'b0}};
        endcase
        zero = (result == {W{1'b0}});
        overflow = (a[W - 1] == b[W - 1]) && (result[W - 1] != a[W - 1]);
    end
endmodule
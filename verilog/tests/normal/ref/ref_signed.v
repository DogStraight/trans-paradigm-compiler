module signed_test(
    input  signed [7:0] a,
    output signed [15:0] b,
    inout  signed [7:0] c
);
    wire signed [31:0] acc;
    reg  signed [15:0] accum;
    integer i;

    always @(*) begin
        accum = a + b;
    end

    function signed [31:0] add;
        input signed [15:0] x;
        input signed [15:0] y;
        begin
            add = x + y;
        end
    endfunction
endmodule

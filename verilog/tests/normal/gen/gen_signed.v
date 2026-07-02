module signed_test(
    input signed [7:0] a,
    output signed [15:0] b,
    inout signed [7:0] c);

    wire signed [31:0] acc;
    reg signed [15:0] accum;
    integer i;
    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    accum = a + b;
    /* ERROR: end */
    function signed /* ERROR: ; */ [31:0 /* ERROR: ; */] add /* ERROR: ; */(/* ERROR: ; */);
    endfunction
    
    input signed [15:0] x
    ;
    input signed [15:0] y
    ;
    begin
        add = x + y;
    end
    /* ERROR: endfunction */
endmodule

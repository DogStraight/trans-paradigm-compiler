// Test: nested single-statement if-else
module nested_if_test( input wire a, b, c, output reg x, y);

    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    if (a /* ERROR: if ( b ) */) /* ERROR: if ( b ) */ /* ERROR: if ( b ) */
    x = 1'b1;
    if (a /* ERROR: if ( b ) */) /* ERROR: if ( b ) */ /* ERROR: if ( b ) */
    x = 1'b1;
    /* ERROR: else */
    y = 1'b0;
    if (a) begin
        if (b /* ERROR: x = 1'b1 ; */) /* ERROR: x = 1'b1 ; */ /* ERROR: x = 1'b1 ; */
    end
    else if (/* ERROR: begin */) /* ERROR: begin */
    y = 1'b0;
    /* ERROR: end */
    /* ERROR: end */
endmodule

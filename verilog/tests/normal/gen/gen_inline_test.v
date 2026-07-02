module inline_test( input wire clk, output reg led);

    reg [31:0] counter;
    always @(posedge clk) if (/* ERROR: begin */) /* ERROR: begin */
    if (!clk) begin
        led <= 1'b0;
    end
    else if (/* ERROR: begin */) /* ERROR: begin */
    led <= ~led;
    /* ERROR: end */
    /* ERROR: end */
endmodule

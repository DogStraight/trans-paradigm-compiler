module inline_test( input wire clk, output reg led);

    reg [31:0] counter;
    always @(posedge clk) begin
        if (!clk) begin
            led <= 1'b0;
        end else begin
            led <= ~led;
        end
    end
    
endmodule

module inline_test( input wire clk, output reg led);

    reg [31:0] counter;
    always @ ( posedge clk ) begin
    if ( ! clk ) /* if comment */ begin
    led <= 1'b0;
    end else /* else comment */ begin
    led <= ~led;
    end
    end
endmodule

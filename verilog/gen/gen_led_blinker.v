module led_blinker(
    input wire clk,
    input wire rst_n,
    output reg led
);
    reg [31:0] counter;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            counter <= 32'd0;
            led <= 1'b0;
        end else if (counter == MAX_CNT) begin
            counter <= 32'd0;
            led <= ~led;
        end else begin
            counter <= counter + 32'd1;
        end
    end
endmodule
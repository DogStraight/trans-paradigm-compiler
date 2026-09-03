module inline_test(input wire clk, /* port comment */ output reg led);
    reg [31:0] counter /* decl comment */;
    always @(posedge clk) begin
        if (!clk) /* if comment */ begin
            led <= 1'b0;
        end else /* else comment */ begin
            led <= ~led + /* 中缀注释 */ 1'b0; /* stmt comment */
        end
    end
endmodule

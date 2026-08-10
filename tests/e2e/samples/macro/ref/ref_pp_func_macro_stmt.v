`define debug(debug_command) debug_command

module m;
    reg [31:0] reg_pc, next_pc;
    always @(posedge clk) begin
        `debug(reg_pc <= next_pc);
    end
endmodule

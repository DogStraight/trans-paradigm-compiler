module sim_loops();

    reg [7:0] i;
    initial begin
        i = 0;
        while (i < 100) i = i + 1'b1;
        repeat (10) begin
            i = i + 1'b1;
        end
    end
    
endmodule

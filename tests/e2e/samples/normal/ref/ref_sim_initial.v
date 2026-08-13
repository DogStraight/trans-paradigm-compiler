module sim_initial();

    reg [7:0] cnt;

    initial begin
        cnt = 8'd0;
        cnt = cnt + 1'b1;
    end

endmodule

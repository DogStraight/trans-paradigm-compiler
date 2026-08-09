module call_test(input clk);

    function add;
        input [7:0] x, y;
        begin
            add = x + y;
        end
    endfunction

    always @(*) begin
        result = add(a, b);
    end

endmodule

module func_wrapper();
    function automatic parity(input [7:0] d);
        reg p;
        begin
            p = 1'b0;
            parity = p;
        end
    endfunction
endmodule

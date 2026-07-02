module call_test( input clk);

    function [/* ERROR: ; */] add /* ERROR: ; */(/* ERROR: ; */);
    endfunction
    
    input [7:0] x, y
    ;
    begin
        add = x + y;
    end
    /* ERROR: endfunction */
    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    result = add(a, b);
    /* ERROR: end */
endmodule

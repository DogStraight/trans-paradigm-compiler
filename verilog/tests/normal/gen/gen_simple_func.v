module simple_func #( parameter W = 8 )(
    input wire [W - 1:0] a,
    output reg [W - 1:0] result);

    // ANSI 风格带参函数
    function automatic [W - 1:0] my_max(
        input [W - 1:0] x,
        input [W - 1:0] y);
        begin
            my_max = (x > y) ? x : y;
        end
    endfunction
    
    // ANSI 风格带参任务
    task automatic my_swap(
        input [W - 1:0] x,
        output [W - 1:0] y);
        begin
            y = x;
        end
    endtask
    
    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    result = my_max(a, a);
    /* ERROR: end */
endmodule

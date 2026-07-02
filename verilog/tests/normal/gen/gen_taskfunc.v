// Test: task 和 function 的域管理
module taskfunc_test #( parameter W = 8 )(
    input wire [W - 1:0] a,
    input wire [W - 1:0] b,
    output reg [W - 1:0] result);

    // 函数
    function automatic /* ERROR: ; */ [W - 1:0 /* ERROR: ; */] my_max /* ERROR: ; */(/* ERROR: ; */);
    endfunction
    
    input [W - 1:0] x
    ;
    input [W - 1:0] y
    ;
    begin
        if (x > y /* ERROR: my_max = x ; */) /* ERROR: my_max = x ; */ /* ERROR: my_max = x ; */
        /* ERROR: else */
        my_max = y;
    end
    /* ERROR: endfunction */
    // 任务
    task automatic /* ERROR: ; */ my_swap /* ERROR: ; */(/* ERROR: ; */);
    endtask
    
    input [W - 1:0] x
    ;
    output [W - 1:0] y
    ;
    begin
        y = x;
    end
    /* ERROR: endtask */
    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    result = my_max(a, b);
    /* ERROR: end */
endmodule

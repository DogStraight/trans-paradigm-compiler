// Test: task 和 function 的域管理
module taskfunc_test #(
    parameter W = 8
)(
    input  wire [W-1:0] a,
    input  wire [W-1:0] b,
    output reg  [W-1:0] result
);

    // 函数
    function automatic [W-1:0] my_max;
        input [W-1:0] x;
        input [W-1:0] y;
        begin
            if (x > y)
                my_max = x;
            else
                my_max = y;
        end
    endfunction

    // 任务
    task automatic my_swap;
        input  [W-1:0] x;
        output [W-1:0] y;
        begin
            y = x;
        end
    endtask

    always @(*) begin
        result = my_max(a, b);
    end

endmodule

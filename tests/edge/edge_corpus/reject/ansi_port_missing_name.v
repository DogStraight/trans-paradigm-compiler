// edge reject（fuzz 回归 2026-08-22）: ANSI 函数端口缺名字（input [7:0] 无标识符）
// 曾触发 parser assert 崩溃（_production.py old_node assert）；修复后软失败。
module func_wrapper ();
    function automatic parity (input [7:0]);
        reg p;
        begin
            p = 1'b0;
            parity = p;
        end
    endfunction
endmodule

// edge reject（fuzz 回归 2026-08-22）: 自引用宏 `` `define debug ( `debug ... ) ``
// 曾导致宏体预展开指数膨胀 → MemoryError 崩溃；修复后软失败（不崩溃）。
`define debug ( debug_command `debug debug_command )
module m(input clk);
    `debug
endmodule

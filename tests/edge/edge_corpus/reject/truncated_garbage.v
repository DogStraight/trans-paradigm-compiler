// edge reject（fuzz 回归 2026-08-22）: 变异垃圾过 lint 门禁 → parser 截断
// 曾静默 success=True 并丢内容（sub u1 例化被吞）；修复后必须失败。
module top ;
 ( ;
 sub u1 (
 . a wire b )
 ) ;
 endmodule

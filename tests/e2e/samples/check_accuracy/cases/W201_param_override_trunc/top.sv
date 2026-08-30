// 正样例：模块内固定位宽 ← 参数位宽赋值，外层覆盖参数后截断。
// 默认 W=4 下 x 4 位 == y 4 位不截断；外层 A #(.W(16)) 覆盖后 16→4 截断。
// B4 实例化覆盖 → 目标模块内部赋值重算（2026-08-31）。
module A;
  parameter W = 4;
  reg [3:0] y;
  wire [W-1:0] x;
  assign y = x;
endmodule

module top;
  A #(.W(16)) u_a();  // 覆盖点：模块内 assign y = x 截断
endmodule

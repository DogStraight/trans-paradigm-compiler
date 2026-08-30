// 负样例：外层覆盖参数但覆盖后仍不截断 → 不报 W201。
module A;
  parameter W = 4;
  reg [3:0] y;
  wire [W-1:0] x;
  assign y = x;  // 覆盖 W=4：4 位 == 4 位，无截断
endmodule

module top;
  A #(.W(4)) u_a();  // 覆盖值 == 默认值，无截断
endmodule

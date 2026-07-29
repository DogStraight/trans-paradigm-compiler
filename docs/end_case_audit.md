# end_case 严格度审计

> 创建: 2026-07-30
> 状态: 待验证

## 背景

`end_case` 在解析时于生产式匹配完成后检查。若下一个 token 不在 `end_case` 列表中，整条规则匹配失败并回滚。这可能导致合法 Verilog 被拒绝。

## 问题分类

### A 类: `end_case = ["newline"]` 过于严格

生产式末尾已有 `symbol.base.semicolon` 自然终止，`end_case` 额外要求换行。

| 文件 | 规则 | 生产式末尾 | 被阻止的写法 |
|------|------|-----------|-------------|
| `30_assign.toml` | `NonBlockingAssign` | `";"` | `a <= b; c <= d;` |
| `30_assign.toml` | `BlockingAssign` | `";"` | `a = b; c = d;` |
| `30_assign.toml` | `AssignStmt` | `";"` | `assign a = b; assign c = d;` |
| `30_wire_reg.toml` | `WireDecl` | `";"` | `wire a, b; wire c, d;` |
| `30_wire_reg.toml` | `RegDecl` | `";"` | `reg a, b; reg c, d;` |
| `30_wire_reg.toml` | `IntegerDecl` | `";"` | `integer i; integer j;` |
| `40_params.toml` | `LocalParamDecl` | `";"` | `localparam A=1; localparam B=2;` |
| `40_params.toml` | `GenvarDecl` | `";"` | `genvar i; genvar j;` |
| `20_for.toml` | `ForLoop` | `@ForBodyStmt` | `for(;;) stmt1; stmt2;` |
| `20_for.toml` | `ForLoopBlock` | `@BeginEnd` | 同上（块体版） |
| `25_event_wait.toml` | `EventWaitStmt` | `@Statement\|";"` | `@(posedge clk); stmt;` |
| `70_misc.toml` | `SubroutineCall` | `";"` | `func1(); func2();` |
| `70_misc.toml` | `NullStmt` | `";"` | `; ;` |
| `60_module_inst.toml` | `ModuleInst` | `@PortConnection` | `mod u1(...); mod u2(...);` |
| `60_module_inst.toml` | `PortConnection` | `";"` | 同上 |
| `20_body_ports.toml` | `BodyInputDecl` 等 6 个 | `";"` | `input a; input b;` |
| `20_body_ports.toml` | `TaskInputDecl` 等 3 个 | `";"` | `input a; input b;` |

### B 类: 块规则 end_case 含被嵌套规则的关键字

| 文件 | 规则 | end_case | 潜在问题 |
|------|------|----------|---------|
| `03_always.toml` | `AlwaysStmt` | `["newline", "keyword.end"]` | 嵌套 begin…end 的 `end` 可能触发提前终止 |
| `04_statements/10_if.toml` | `IfBlock` | `["newline", "keyword.end", "keyword.else"]` | 嵌套 if 的内层 `end` 可能被外层 if 消费 |
| `04_statements/10_if.toml` | `IfStmt` | `["newline", "keyword.end", "keyword.else"]` | 同上 |
| `04_statements/40_case.toml` | `CaseStmt` | `["keyword.endcase", "keyword.end", "newline"]` | 嵌套 case 的内层 `endcase` |

### C 类: `Expression.end_case` 不完整

当前: `["comma", "semicolon", ")", "]", "}", ":"]`

可能缺少的 token:
- `keyword.end` — if/for/case 体内的表达式后可能跟 `end`
- `keyword.else` — if 条件后的表达式后可能跟 `else`
- `symbol.base.equal` — for 循环初始化中的 `=` 前是表达式

## 验证方法

对每个问题，准备最小测试用例，通过现有测试框架运行:

1. A 类: 同一行多条语句
2. B 类: 嵌套 begin…end / case 的块
3. C 类: 表达式的各种边界情况

# Case 目录（语义单例文档化）

> 把引擎的关键语义行为整理为**可读清单**：每行为一个 case——输入片段 →
> 显式期望。正确性已由自动化（差分/fuzz/e2e）覆盖，本清单的增量价值是
> **语义契约可读**：改引擎时对照期望，加语言特性时先看同类 case 形态。
>
> 每个 case 标注样本引用（`tests/e2e/samples/` 下同名 ref 可独立复跑：
> `python tests/e2e/run_all_tests.py <group> <name>`）。
> 更新：2026-08-26（P2.5 case 即文档轻量版）

## Lexer（词法）

| case | 输入片段 | 期望 | 样本 |
|------|---------|------|------|
| 基数字面量（配置驱动） | `8'd255` / `3'b101` / `16'hff00` | 按 `[number.based]` size/base_prefix 识别，值捕获正确 | ref_alu |
| 无尺寸数字 | `3'd0`（case 项） | 定界符捕获模式（delim capture） | ref_fsm |
| 位宽表达式 | `[W-1:0]` / `[2:0]` | 表达式内 `-` 不拆数字，整体作为范围 | ref_alu, ref_param_range |
| 注释清理（语言包配置） | `// 行注释` / `/* 块 */` / `"字符串"` | pre_scan clean 三段按 `[[pre_scan.clean]]` 剥离（line/block/string） | ref_comments |
| 数组下标 | `[0:7]` / `[7:0][3:0]` | 多维索引 token 化不歧义 | ref_array, ref_array2d |

## Parser（语法）

| case | 输入片段 | 期望 | 样本 |
|------|---------|------|------|
| ANSI 端口列表 | `input wire [W-1:0] a, output reg zero` | 方向/类型/位宽/名字正确归位 | ref_alu |
| 参数化模块 | `module alu #(parameter W = 8)(...)` | 参数列表 + 端口列表双列表 | ref_alu, ref_param_range |
| 连续赋值 | `assign sum = a + b;` | 赋值语句发现（模块级） | ref_alu |
| 过程赋值 + 时序控制 | `always @(*)` / `@(posedge clk)` | 敏感列表解析（SensitivityList） | ref_fsm, ref_always_events |
| case 语句 | `case (op) 3'd0: ... default: ...` | 分支项 + default，endcase 配对 | ref_fsm |
| for 循环 | `for (i=0; i<N; i=i+1)` | 三段式（init/cond/step） | ref_for_loop, ref_loops_gen |
| 函数/任务声明 | `function ...; endfunction` / `task ...; endtask` | ANSI 风格端口 + 块配对 | ref_func_ansi, ref_task, ref_taskfunc |
| generate 块 | `genvar` + `generate/endgenerate` | 结构生成 | ref_generate |
| 属性标注 | `(* keep = "true" *)` | AttrSpecList 挂载 | ref_attribute |
| 参数化实例化 | `#(.W(8)) inst (.a(a));` | ParamOverrideList + NamedPortList | ref_top |
| 拼接表达式 | `{W{1'b0}}` / `{a, b}` | ConcatExpr 嵌套 | ref_alu, ref_concat_nest |
| 三元条件 | `cond ? a : b` | 只断 `:` 后（wrap 断点） | ref_complex |
| 增强语法：类型/角色 | `spi.slave spi_io` | type/role 声明解析（transform 组源） | transform/ref_nested_type |

## Linter（前置 token 级检查）

| case | 输入片段 | 期望 | 样本 |
|------|---------|------|------|
| 缺 endmodule | `module m; assign a=b;`（无尾） | 报缺模块闭合（e01） | ref_e01_missing_endmodule |
| 多 endmodule | 两个 `endmodule` | 报多余闭合（e02） | ref_e02_extra_endmodule |
| 未闭合 begin | `always @(*) begin ...`（无 end） | 报块未闭合（e03） | ref_e03_unclosed_begin |
| 语句缺分号 | `assign a = b` | 报缺失分号（e05） | ref_e05_missing_semicolon |
| 表达式双操作符 | `a + + b` | 报相邻操作符（e21） | ref_e21_expr_double_op |
| 合法语句无误报 | `wire a; assign a = b;` 等 | ref_v01-v05 全部通过（0 误报） | ref_v01_wire_assign … |

## Analyzer（语义）

| case | 输入片段 | 期望 | 样本 |
|------|---------|------|------|
| 作用域/符号 | module 内 wire/reg/port | 模块作用域 + 符号表（kind 区分） | ref_alu |
| role 类型解析 | `spi.slave` 端口声明 | role 引用解析 + 端口展开（flatten_ports） | transform/ref_spi_inf |
| primitive 顺序 | resolve_refs → flatten_ports → attach_invert_map | 按 `[analyzer] primitive_order` 执行 | transform/ref_nested_type |
| error 级诊断停管线 | 语义错误样本 | analyze pass 报 error → 停调度停管线 | errors 组 |
| warning 级不阻断 | `spi` 引用无类型 | warning 继续管线（WARN 设计状态） | warning/ref_spi_no_type |

## Transform（语义映射 + 配置驱动变换）

| case | 输入片段 | 期望 | 样本 |
|------|---------|------|------|
| typed_ports 展开 | `spi.slave spi_io` 端口 | 展开为具体端口（spi_io_clk 等），映射表驱动 | transform/ref_spi_inf |
| impl 绑定 | `impl spi.master (...) => top;` | 生成 ModuleInst 实例（替换绑定） | transform/ref_impl_test |
| 嵌套类型引用 | role 引用另一 role | 嵌套展开（inner_* 方向反转） | transform/ref_nested_type |
| 实例名 hash 稳定性 | 生成实例命名 | `u_<type>_<hash>` 双路径（P/X）一致 | transform/ref_spi_inf |
| extra AST | impl 包装模块 | 渲染为独立输出文件（gen_*.v） | transform/ref_impl_test |

## Renderer（Doc IR → 文本）

| case | 输入片段 | 期望 | 样本 |
|------|---------|------|------|
| Pad 三件套（对齐进 Doc） | 对齐声明/端口列 | Pad/IfBreakPad/IfFlatPad 参与 fits/break 决策 | ref_alu（端口对齐） |
| fits 带外层 continuation | 嵌套 group 组合行 | 预算 = 行宽 − 前面已占 − 后续将占 | ref_complex |
| intent 声明（compact） | 列表布局 | join+first_soft+nest 别名，输出逐字节等价 | ref_alu（端口列表） |
| 注释 attachment | `input clk, // 注释` | 行尾注释挂项节点 → line_suffix 锚定 | ref_comments |
| 保真度分级 | `--fidelity keep_blank` | 空行按源结构位置回插 | ref_led_blinker |
| 幂等 | 任意 normal 样本 | 生成文本再走管线稳定（idempotent） | normal 组全量 |

## Formatter（世界 B：文本行 pass）

| case | 输入片段 | 期望 | 样本 |
|------|---------|------|------|
| 品类对齐 | 连续 `reg [..] x;` 声明 | 声明列对齐（port_dir/declaration/parameter） | ref_alu |
| wrap 惩罚折行 | 超宽行 | 断点惩罚最小化（逗号<逻辑<算术<三目） | ref_picorv32 |
| inst_port 对齐 | 实例端口连接 | `.name(sig)` 列对齐 | ref_top |
| 拆行 contexts 同步 | 端口尾行拆分 | 拆行后 lines/contexts 不错位 | ref_picorv32 |

## Preprocessor（宏/条件编译）

| case | 输入片段 | 期望 | 样本 |
|------|---------|------|------|
| 宏定义/展开 | `` `define W 8 `` → `W` | 宏表 + 展开（反向映射可还原） | ref_macro_def |
| 函数宏 | `` `define MAX(a,b) ... `` | 实参替换 + 语句级展开 | ref_pp_func_macro_* |
| ifdef 分支选择 | `` `ifdef/`else/`endif `` | 活跃分支展开、非活跃占位 | ref_pp_ifdef_* |
| 条件块往返 | 嵌套 ifdef 编辑 | 占位注释 → 原文还原（roundtrip） | ref_pp_ifdef_roundtrip |
| timescale 指令 | `` `timescale 1ns/1ps `` | 指令行保留还原 | ref_timescale |

## Pipeline（编排调度 ADR-0007）

| case | 输入片段 | 期望 | 样本/测试 |
|------|---------|------|-----------|
| 缺省 schedule | 无 `[[pipeline.schedule]]` 声明 | default = [analyze, transform]（旧行为零变化） | test_schedule.py |
| kind 三态 | analyze / transform / check | analyze 产 scope、transform 消费、check 执行 handler | test_schedule.py |
| 时点序列器 | order=N / after=X / 声明序 | 钉号/推导/填空；冲突/环/未知名 fail-fast | test_schedule.py |
| 能力协议 | `[capabilities]` 声明 | get_capability 查找（pipeline 不直连插件） | test_capabilities.py |
| stage 截断 | `stage="analyze"` | 执行完名为 analyze 的 pass 后截断 | test_schedule.py |

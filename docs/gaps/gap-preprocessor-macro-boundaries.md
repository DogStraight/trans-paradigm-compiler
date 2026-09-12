# Gap — preprocessor 宏覆盖缺口（type macros / 复合嵌套反向映射）

- 状态：**立项中**（TODO「缺口闭环队列」③，2026-09-12 排队）：只立项
  **类型位宏**；嵌套反向映射实测未复现失败（见下），待确认形态后再论
- 关联：原 `docs/known_limitations.md` Correctness boundaries（2026-09-04 按
  部件拆入本档）
- 参照：C 预处理器（对象/函数宏 + 条件编译）的成熟形态

## 缺口是什么

宏系统覆盖常用形式，非全种类：对象/函数式 `` `define ``、条件编译
（`ifdef/ifndef/else/elsif/endif`）、`` `include ``（递归、循环检测）、反斜杠
续行——均支持，且带反向映射回原文。两个剩余缺口：

1. **类型/网类型/位宽槽位的宏失败**（2026-09-13 实测重列；**原复现用例是非法
   Verilog，已作废**）：
   - ⚠ 原档复现 `input `PTYPE d`（PTYPE=`reg [7:0]`）展开即
     `input reg [7:0] d` —— 这是**非法 Verilog**（input 不可声明为 reg），
     语法包拒绝**正确**。该用例不能作为缺口依据（2026-09-12 的"失败"结论
     就建立在它上面）。
   - ✅ 手写合法形态**均被语法包支持**：`input [7:0] d` / `input wire d` /
     `input wire [7:0] d` / `output reg [7:0] q` / `output reg q` / `inout wire [7:0] d`。
   - ❌ 对应**宏写法全部失败**：`input `NT d`（NT=wire）、`output `PT q`
     （PT=`reg [7:0]`）、`input `T d`（T=`[7:0]`）→ 均 `parse truncated`。
   - ✅ 语句位/整声明位可用：`` `define REG_DECL reg [7:0] r0; `` + 体内
     `` `REG_DECL ``（保真 0.972）；`` `define WIRE_DECL wire d `` +
     `input `WIRE_DECL` 也可用（marker 恰好落在端口名位，即"碰巧合法"）。
   - **根因**：展开锚 `tpc_marker_N` 是一个**标识符**；`id` 不是合法的
     net_type / 类型 / 位宽。手写 `input wire d` 合法是因为 `wire` 是关键字，
     而 marker 是 id。故缺口 = "代理 token 在非表达式槽位不合法"。
   - ADR-0016 **阶段 4 已完成但未覆盖此案**（marker 代理仍是展开机制），
     故不能算已被吸收。
   - 触发面（实测枚举）：宏体为 net_type（`wire`/`tri`）、类型（`reg`）、
     或**完整位宽**（`[7:0]`）且落点在端口/声明的类型槽。宏体为表达式
     （`` `W `` + `[`W-1:0] d`）不受影响。
2. **嵌套调用反向映射**（2026-09-12 实测**未复现失败**）：
   - 对象宏嵌套 `` `define B (`A + 1) `` → 保真 0.983；
   - 函数宏嵌套 `` `define V(y) `W(y)*2 `` → 保真 0.986；
   - 两者均无 marker 残留、`` `B `` / `` `V(3) `` 原样还原。残余差异全部来自
     与本缺口无关的 `module m;` → `module m();` 渲染归一。
   原描述"折叠单 token 后无法干净还原"在对象/函数两种嵌套形态上不成立——
   需另找触发形态（如宏体跨多语句 + 条件编译交织）再认定，否则应从缺口移除。

## 为什么是缺口（影响面）

真实工程（如 PicoRV32 类核心）会混用"声明/类型宏 + 嵌套调用"，类型位失败
意味着**端口声明里用类型宏写不出合法输入**（用户只能绕开），是真实的形态
盲区。原档并列的"嵌套反向映射失败"经实测未复现，暂不再作为缺口论据。

## 成熟解法参照（见贤思齐）

- C 预处理器对宏展开做 token 级保留（预扫描标记），反向映射的成熟做法是展开
  期保留"宏调用区间"结构，而非折叠后猜词边界。
- `preprocessor/_bridge.py`（锚 + 残片回插）已是统一位置桥——type macro 可沿
  该桥扩展"声明形态宏"的锚记。

## 可实现性

- 类型位宏：**修法待选**（"代理 token 在类型槽不合法"有两种解法，取舍不同）：
  - **A. 体前缀判定 → inline 形态**：宏体以类型/net_type/位宽前缀开头时，
    不用 `tpc_marker_N`，改走既有的"行内注释锚 + 体原文"形态
    （`/*<tpc:macro:N>*/` + body，注释是 trivia、parser 跳过，`=` 后缀宏
    已在用这条通道）。前缀表由语言包声明（`[expand] inline_body_prefixes`，
    顺带把现硬编码在引擎里的 `=` 判定搬进 TOML——语言知识归位）。
    代价：这些宏**不再产 `MacroCall` 节点**（阶段 2 成果，P3.2/P3.3 前提）。
  - **B. 全量 inline**：所有非空体宏都走 inline → 一次修好所有位置，但
    `MacroCall` 节点全面消失，等于回退阶段 2。
  - **C. 判为已知边界**：无真实语料消费（ice40/picorv32/tv80/darkriscv 均通过），
    等真有工程要求再做。
  - 倾向 A（牺牲面最小、与既有 `=` 先例同构）；选路后先补失败门禁再改实现。
- 嵌套反向映射：**先确认形态是否真的失败**（当前实测通过），确认后再谈
  保留调用树/区间锚的方案——不确认就不动展开器。
- 验证：`tests/languages/verilog/test_macro*.py` + real 语料宏还原门禁
  （`tests/e2e/test_macro_reverse.py`）。
- 依赖前置：无（纯 preprocessor 层）。

## 关联条目

- 原 `docs/known_limitations.md`（Correctness：macro system covers common forms）
- `preprocessor/`（`_expand.py`/`_reverse.py`/`_bridge.py`）
- real 语料宏还原门禁：`tests/e2e/test_macro_reverse.py`

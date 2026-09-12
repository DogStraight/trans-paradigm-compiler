# Gap — preprocessor 宏覆盖缺口（type macros / 复合嵌套反向映射）

- 状态：条目 1（类型位宏）**已闭环**（2026-09-13，commit 待记）——按
  `docs/decisions/0017-macro-in-syntax-position.md`：锚复用 lexer 宏识别 +
  类型槽位声明 `@MacroCall`（parser 直产宏节点）+ linter 锚窗口拼接。
  剩余：**宏子槽**（条目 1b，见下）；条目 2 实测未复现失败（见下），待另寻形态
- 关联：原 `docs/known_limitations.md` Correctness boundaries（2026-09-04 按
  部件拆入本档）；`docs/decisions/0017-macro-in-syntax-position.md`
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
   - **根因**：展开锚曾是**标识符**；`id` 不是合法的 net_type / 类型 / 位宽。
     手写 `input wire d` 合法是因为 `wire` 是关键字，而 marker 是 id。
     故缺口 = "代理 token 在非表达式槽位不合法"。
   - **✅ 已闭环（2026-09-13）**：锚改为**宏调用文本形态**（`` `<锚名> ``，lexer
     归为 `macro.call`，不为锚新造词法形态）；`[TypeSpec]`/`[TypeSpecNoReg]`
     首元素加 `@MacroCall` 备选（宏是**整体替换类型片段**的文本 → 锚必然落在
     首元素位，故一处声明覆盖三例）；parser 直产 MacroCall（宏名 + 源区间），
     渲染按 `_macro_fragment` 直出原文。实测三例均：解析成功 + 树含宏节点 +
     输出保留 `` `NT d `` 原文 + 手写形态不变。
     `tests/languages/verilog/test_macro_type_slot.py`。
   - ADR-0016 阶段 4 的 marker 代理机制已被本修法替换（锚即宏调用形态）。
   - 触发面（实测枚举）：宏体为 net_type（`wire`/`tri`）、类型（`reg`）、
     或**完整位宽**（`[7:0]`）且落点在端口/声明的类型槽 → 已支持。宏体为表达式
     （`` `W `` + `[`W-1:0] d`）不受影响。
1b. **宏子槽未支持**（2026-09-13 登记）：`` input wire `T d ``（T=`[7:0]`）——
   子槽（Range/signed）的 layout 自带字面 `[` `]`，而宏残片可能含方括号 → 会多套
   一对（静默错渲染）。**宁可停不可静默错**，故有意不加备选（照旧解析失败）。
   若将来支持：要么让该槽位的 layout 能识别"ref 是宏节点则不出字面括号"，
   要么把方括号收进 Range 自己的 layout（现由调用方槽位加）。代价：宏体为
   `signed` 的子槽同属此类，同理未支持。
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

- 类型位宏：**已选路（2026-09-13，作者定）**——见
  `docs/decisions/0017-macro-in-syntax-position.md`：
  ① **句级语法检查前移到 linter 展开路径**（linter 本就有 skip/近似能力，
     带宏的语法检查归它）；
  ② **parser 直产宏节点**（宏名 + 源区间），不做硬解析、也不引入恢复机制；
  ③ 实现形态：展开期改为产**占位 token**（类型由语言包声明），语言包声明
     `[MacroNode.parser] production = ["<占位 token>"]` 并在"宏可出现"的槽位加
     `@MacroNode` 备选（"宏能出现在哪"是语言知识，归语言包）。
  被拒备选：**parser panic + skip 到后界**（与"跳过能力已在 linter"重复建设，
  且让 parser 承担语法近似）/ 体前缀判定改 inline（只治一类且牺牲 MacroCall）/
  全量 inline（回退阶段 2）/ 维持已知边界（代价不对称）。
- 嵌套反向映射：**先确认形态是否真的失败**（当前实测通过），确认后再谈
  保留调用树/区间锚的方案——不确认就不动展开器。
- 验证：`tests/languages/verilog/test_macro*.py` + real 语料宏还原门禁
  （`tests/e2e/test_macro_reverse.py`）。
- 依赖前置：无（纯 preprocessor 层）。

## 关联条目

- 原 `docs/known_limitations.md`（Correctness：macro system covers common forms）
- `preprocessor/`（`_expand.py`/`_reverse.py`/`_bridge.py`）
- real 语料宏还原门禁：`tests/e2e/test_macro_reverse.py`

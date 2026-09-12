# ADR-0017: 宏落在语法位——检查前移 linter 展开路径 + parser 直产宏节点

- Status: accepted（决策 3/4 已实现；语法位槽位声明按语言包逐槽位推进）
- Date: 2026-09-13
- 关联：ADR-0016（宏体入树：raw 源区间权威 + 对应层）；
  `docs/gaps/gap-preprocessor-macro-boundaries.md`（触发面实测）；
  `docs/gaps/gap-parser-linter-approximation.md`（"无恢复"定调**不变**，本决策只新增
  "宏位可解析为宏节点"这一条语法路径）

## 背景

**触发面**（2026-09-13 逐形态实测，见 gap 档案）：宏调用落在**语法级位置**时无法
解析。手写合法形态语法包都支持，对应宏写法全部失败：

| 手写（均 ✅） | 宏写法 |
|---|---|
| `input [7:0] d` / `input wire d` / `input wire [7:0] d` | `` input `T d ``（T=`[7:0]`）/ `` input `NT d ``（NT=wire） |
| `output reg [7:0] q` / `output reg q` | `` output `PT q ``（PT=`reg [7:0]`） |

**根因两层**：

1. **宏本身破坏语法结构**：展开代理 `tpc_marker_N` 是一个**标识符**，而 `id`
   不是合法的 net_type / 类型 / 位宽——手写 `input wire d` 合法是因为 `wire`
   是关键字，代理却是 id。故在该位置**硬解析不可能对**，换多少种代理形态都治标。
2. **parser 无任何容错**：任一产生式失败即整文件截断。实测（同一份模块，只有 ports
   列表里一项不同）：

   | 输入 | 结果 |
   |---|---|
   | 全好 | ✅ 15 类节点（ModuleDecl / PortList / AnsiInputDecl / Declarator…） |
   | 一个端口类型位为 marker | ❌ **节点种类 0** + `parse truncated` |
   | 一个端口纯语法错（`input [7:0]` 缺名） | ❌ 同样 0 节点 |
   | 块体内一个坏语句 | ❌ 同样 0 节点 |

   即失败粒度不是"丢一个节点"，而是**一个坏项废掉整份文件**（含与宏无关的部分）——
   代价与收益严重不对称。

原 `gap-parser-linter-approximation` 把"无恢复"记为**接受**（理由：收益低、与
linter 职责重叠）。该理由在"坏输入"场景成立，但**漏掉了本情形**：宏是**合法
源码**，parser 只是缺容忍机制，于是合法文件被整体拒绝。

**错在哪一层**（本决策的核心）：现状把"带宏的句级语法检查"压在 **parser** 上，
而 parser 面对宏位**必然失败**（代理 token 是 id，不是合法的 net_type/类型/位宽）。
反过来，**跳过/近似能力其实已经在 linter**：`linter/discovery.py` 已有对标 yacc
panic mode 的同步 token ∪ 行尾 newline 的 skip 推进，linter 本就是"在坏/不完整
输入上工作"的那一层。故正确的位置是把带宏的语法检查**前移**，而不是给 parser
补一套恢复。

## 决策

1. **句级语法检查前移到 linter 的展开路径**。带宏的语法检查由**前置 linter** 在
   **宏展开后的文本**上完成——linter 本就有 skip/近似能力，正是这类检查该待的
   层（"静态解析不对宏位负责，展开后再检查"）。
2. **语言包不为宏保留任何语法槽位**（2026-09-13 定稿，**推翻本 ADR 初稿的
   "槽位声明"路线**）。宏的位置本质上是**文本任意**的，逐槽位声明 `@MacroCall`：
   - **补不齐**：结构词（`module`/`begin`/`end`）、运算符、逗号/分号/括号位
     根本没有"槽位"可声明——它们就是 parser 用来决定怎么解析的 token。
     位置覆盖量化（不变量：把任一 token 换成等价宏
     `` `define M <原 token 原文> ``，格式化输出必须不变；
     `_drafts/probe_macro_anywhere.py`）：逐槽位声明 **54/135 = 40%** → 撤销
     语法声明后 **50/135 = 37%**——即整套槽位机制只买到 4 个位置，代价/收益
     不成立。
   - **会静默错渲染**：某些槽位的 layout 自带字面量（如 range 子槽的 `[` `]`），
     宏残片可能已含这些字符 → 多套一对；判据不显然（取决于该槽位 layout 形态），
     越补越像掩盖边界。
   故 `Identifier` 的 `macro.call` 备选、`MacroCall.parser`、
   `TypeSpec`/`TypeSpecNoReg` 的 `@MacroCall` 均**已撤销**。

3. **宏由外层（预处理器/管线）处理；MacroCall 是引擎级节点，语言包只声明它怎么
   渲染**。展开在解析之前发生（`expand_tokens(semantic=True)` 铺宏体文本）——
   **宏在任意位置都退化为"展开后的文本在该位置是否语法合法"**，由既有语法自己
   判定，不需要任何声明：`` input `NT d ``（NT=wire）展开就是 `input wire d`，
   现有产生式直接成立——所以"类型位槽位声明"是伪需求。宏边界节点（宏名 + raw
   源区间）由管线就树产生/改写（ADR-0016 阶段 2 的机制，`pipeline/__init__.py`），
   语言包对它的唯一认知是渲染方式（`[MacroCall.renderer.layout]` 输出
   `_macro_fragment`）。

4. **渲染侧：遇宏节点走 raw 分支拼接**——输出宏调用原文，不把展开内容重新
   格式化。带宏文本的对齐/格式化参照前人做法（Verible / clang-format：宏调用
   视为**不可拆的原子文本**，无法证明可安全重排时整段原样输出 verbatim）。
   **规则（2026-09-13 实测后定）**：取**最小的 `is_statement` 包含节点**，该节点
   整段按**源文本原样输出**（节点保留、只加引擎标记，不替换成 MacroCall——避免
   影响分析遍历）。
   - 为什么不是"精确对齐的节点级折叠"：实测 6 例中 4 例精确对齐到节点
     （`Range`/`Number`/`BlockingAssign`/`RegDecl`，`_drafts/probe_region_alignment.py`），
     但**精确对齐不等于可安全替换**——`` input `T d ``（T=`[7:0]`）精确对齐到
     `Range`，而 `Range.renderer` 只出 `msb : lsb`、方括号由**槽位 layout** 加，
     宏展开体却自带 `[` `]` → 节点级替换会渲染成 `` input [`T] d ``（多套一对）。
   - `is_statement` 是**语言包声明**（引擎只读、不硬编码）→ 规则与 layout 无关，
     可证明不臆造文本：类型位三例落到 `BodyInputDecl`/`BodyOutputDecl` 声明上
     → 原样输出 `` input `NT d; `` ✓；语句体/声明体宏落到各自语句/声明上 ✓。
   - 粒度代价：含宏的**声明内部**不重排（对齐/空白保持原样）——这是"宁可原样，
     不可静默重排"的直接结果。

5. **parser 不做通用错误恢复**。`gap-parser-linter-approximation` 的"无恢复"
   对**非宏输入仍然成立**（真语法错仍是"linter 前置 + truncation 双保险"）；
   本决策只改宏的**处理位置**（外层展开 + 渲染 raw 拼接），不改其它失败语义。

## 权衡

**付出**：
- 展开在解析前发生（铺宏体文本）→ 渲染侧必须有 **raw 拼接** 才能把宏调用原文还回去
  （宏区间 ↔ 输出文本的对应），这是本决策真正的成本所在；
- 宏区间与"可渲染单元"不重合的形态（宏残片含槽位字面量）需定下原样输出的边界
  规则（决策 4 末条）；
- 迁移期间锚（`__tpc_marker_*`）与展开并存，需分切片迁移并保行为不回退
  （锚仍在用：`restore_anchors` 是当前输出的还原通道）。

**被拒绝的备选**：
- **逐槽位声明 `@MacroCall`/`@MacroNode`**（本 ADR 第二稿方案，2026-09-13 实测后
  推翻）：宏位置文本任意 → 补不齐（37% → 40% 实测）+ 部分槽位静默错渲染；
- **parser panic + skip 到后界**（初稿方案）：把跳过能力搬进 parser，与
  "跳过能力已在 linter"重复建设，且让 parser 承担语法近似；
- **给 marker 找合法形态 / 体前缀判定改 inline**：治标（只治一类槽位），且牺牲
  ADR-0016 阶段 2 的 MacroCall 节点成果；
- **维持现状（判为已知边界）**：一个宏废掉整份文件的代价与触发概率不匹配。

**边界（本决策不做）**：
- 不做列级定位；不做通用 LR/GLR 式恢复；**宏位之外**的错误行为一律不变
  （宁可停，不可静默错——与"静默错乱是假绿温床"一致）。

## 验证

1. **语法位宏可解析**：`` input `NT d `` / `` output `PT q `` / `` input `T d ``
   → 解析成功，且树中出现**宏节点**（宏名 + 源区间）——当前 6 个用例以
   `xfail(strict=True)` 钉在 `tests/languages/verilog/test_macro_type_slot.py`，
   机制就位后翻正（strict 保证翻正必须被看到）；
2. **位置覆盖可量**：把"任一 token 换成等价宏"做成不变量（
   `_drafts/probe_macro_anywhere.py`，历史：逐槽位 40% / 当前 37%），
   机制就位后上升且不回退——这是"其他位置能不能同样处理"的**可验证答案**；
3. **非宏真错误行为不变**：块体内 `assign = 1;` 仍阻断（比对现状）；
4. **宏定位不改失败语义**：真语法错仍是 linter 前置 + truncation 双保险；
5. 全量回归 + e2e FAIL 0 + 真实语料保真不降 + 误报基线无增长。

> Impl: 切片 ① ✅ **宏区间表**（`preprocessor/_expand.py::expand_tokens` 第三返回值：
> 源区间 + 展开结果字符区间；测试 `tests/engine/preprocessor/test_macro_regions.py`）
> → 切片 ② 渲染侧 raw 拼接 → 切片 ③ 撤锚。
> 已落地部分：锚名协议（保留前缀/盐/序号/还原唯一性守卫，
> `core/token_protocol.py` + `preprocessor/_bridge.py`）——它是**当前**输出还原
> （`restore_anchors`）的载体，服务本决策的决策 4；语法侧已**撤销全部宏声明**
> （`Identifier` 备选 / `MacroCall.parser` / `TypeSpec` 的 `@MacroCall`）。
> Test: `tests/engine/preprocessor/test_anchor_protocol.py`（锚名/还原守卫）·
> `tests/languages/verilog/test_macro_type_slot.py`（6 个 xfail = 目标需求）·
> `tests/languages/verilog/test_macro_call_node.py`（宏边界节点）·
> `tests/languages/verilog/test_macro_body_comment.py`（宏调用后同行内容不被吞——
> 文本展开路线的守卫）

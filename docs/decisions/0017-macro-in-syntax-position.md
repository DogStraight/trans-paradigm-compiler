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
2. **parser 只产宏节点，不承担宏位解析，也不引入恢复**。宏落在语法位时，parser
   **不尝试硬解析**、也不需要 panic/skip 机制——**直接产出宏节点**（宏名 +
   源区间），使该构造的其余部分照常解析、整份文件不再被一个宏拖垮。
3. **实现形态：锚复用 lexer 的宏识别 + 槽位声明走 `Identifier` 备选**（已实现）。
   - **锚不是新词法形态**：lex 阶段本就把 `` `NAME `` 识别为宏 token，故展开期的
     锚直接写成**宏调用文本**（`` `<锚名> ``），lexer 自然归为 `macro.call`——
     不为锚新造词法面（此前 `tpc_marker_N` 与 `id` 同形，才需要另想办法区分）。
   - **锚名协议**（`core/token_protocol.py`）：保留前缀 `__tpc_` + `marker` + 盐 + 序号。
     盐 = 源文本 sha256 前 8 位（**不用内置 `hash()`**：PYTHONHASHSEED 随机化会
     破坏跨进程可复现）→ 文件间不撞、文件内序号互异、用户代码撞不出来。
     还原侧加**唯一性守卫**（命中次数 ≠ 1 不回插，保留占位可见，不静默错还原）。
   - **槽位声明**：`[Identifier.parser] production = ["id|macro.call"]`——宏出现在
     "标识符可出现"的槽位时被该备选接受；parser 仍产 Identifier 节点，宏边界由
     管线按锚表改写为 `MacroCall`（ADR-0016 阶段 2 成果不回退）。
     比原候选甲（逐槽位补 `@MacroNode`）少 83 处数据改动，比候选乙（parser 宽容）
     保持"失败即失败"的严格语义。代价：`macro.call` 于是能在**所有** `@Identifier`
     槽位通过——与"宏可出现在哪"这一语言知识相比偏宽，由 linter 展开路径兜底语义。
   - **类型位槽位声明已补**（`grammar/verilog/02_declarations/00_base.toml`）：
     `TypeSpec`/`TypeSpecNoReg` 首元素加 `@MacroCall` 备选——宏是**整体替换类型
     片段**的文本，锚必然落在首元素位，故一处声明覆盖三例（`` input `NT d `` /
     `` output `PT q `` / `` input `T d ``；实测三例均解析成功、树含宏节点、输出
     保留原文）。**宏子槽**（`` input wire `T d ``）有意不做：子槽 layout 自带
     字面 `[` `]`，宏残片可能含方括号 → 多套一对（静默错渲染）；宁可停不可静默错
     （登记 `docs/gaps/gap-preprocessor-macro-boundaries.md` 条目 1b）。

4. **linter 检查的是完全展开形态：锚不进检查、展开体进检查**（已实现）。
   展开路径的检查对象必须是**宏展开后的语法形态**——带锚则判的是锚名而非展开
   内容（类型位宏展开成 `wire` 才可判），且锚是引擎占位、会被 P0 当未定义宏。
   实现形态按"锚表 + token 级窗口拼接"（`linter/scanner.py::_splice_anchor_windows`）：
   锚 token 原位换成展开体 token 序列（位置映射到锚位置），**不改 linter 内部的
   检查器与既有测试面**。
   **为什么不是文本级展开**（`expand_tokens(semantic=True)` 铺宏体文本）：文本替换
   跨注释边界——宏体自带行尾注释时（实测 darkriscv `` `define LUI 7'b01101_11
   // lui rd,imm ``），宏调用**同行的后续 token**（`;`）被吞进注释，语句丢分号
   → 发现器级联失守（**实测 81 条 phase-unrecognized**；同一份文件 check 链
   `analyzer/structure.py::_expand_source` 走文本展开，今天就有这 81 条）。
   token 级拼接不跨 token 边界，无此问题（实测同一文件降到 0）。
   残余：darkriscv 上仍有 26 条与"体注释"同进同出（去注释即 0），但单条多行
   表达式/三元的 9 个最小变体均 0 条——**相关性已测、机制未定**，待钉死触发
   条件（登记 `docs/gaps/gap-parser-linter-approximation.md`）。
4. **parser 不做通用错误恢复**。`gap-parser-linter-approximation` 的"无恢复"
   对**非宏输入仍然成立**（真语法错仍是"linter 前置 + truncation 双保险"）；
   本决策只新增"宏位可解析为宏节点"这一条语法路径，不改其它失败语义。

## 权衡

**付出**：
- 语言包需在宏可出现的槽位补 `@MacroNode`（**数据**改动，逐槽位；这也是它该在
  的地方——"宏允许出现在哪些语法槽"是语言知识）；
- 展开期新增占位 token 形态，与现有 marker 机制（服务渲染还原 / 宏边界节点化 /
  ADR-0016 阶段 2、4）并存或替换，需分切片迁移并保行为不回退；
- linter 展开路径要划清与 raw 检查的分工（哪些诊断在 raw、哪些在展开文本上）。

**被拒绝的备选**：
- **parser panic + skip 到后界**（本 ADR 初稿方案）：把跳过能力搬进 parser，与
  "跳过能力已在 linter"重复建设，且让 parser 承担语法近似——偏离其"纯解析"定位；
- **给 marker 找合法形态 / 体前缀判定改 inline**：治标（只治一类槽位），且牺牲
  ADR-0016 阶段 2 的 MacroCall 节点成果；
- **维持现状（判为已知边界）**：无真实语料消费，但"一个宏废掉整份文件"的代价
  与触发概率不匹配。

**边界（本决策不做）**：
- 不做列级定位；不做通用 LR/GLR 式恢复；**宏位之外**的错误行为一律不变
  （宁可停，不可静默错——与"静默错乱是假绿温床"一致）。

## 验证

1. **语法位宏可解析**：`` input `NT d `` / `` output `PT q `` / `` input `T d ``
   → 解析成功，且树中出现**宏节点**（宏名 + 源区间）；
2. **无关部分照常产出**：同一文件里与宏无关的节点数不减少
   （对照基线：现状 0 类节点 → 目标 ≥ 全好样本的 15 类节点）；
3. **非宏真错误行为不变**：块体内 `assign = 1;` 仍阻断（比对现状）；
4. **linter 展开路径**：带宏的句级语法问题可被检出（相对"整文件截断"是能力提升）；
5. 全量回归 + e2e FAIL 0 + 真实语料保真不降 + 误报基线无增长。

> Impl: `core/token_protocol.py`（锚名协议：保留前缀/盐/序号）·
> `preprocessor/_expand.py`（锚写成宏调用文本 + 锚表带展开体）·
> `preprocessor/_bridge.py`（还原唯一性守卫）·
> `linter/scanner.py::_splice_anchor_windows`（token 级锚窗口拼接）·
> `pipeline/__init__.py::_attach_macro_meta`（两种进树形态挂锚表元数据）·
> `grammar/verilog/05_expressions/00_base.toml`（`Identifier` 接受 `macro.call` +
> `[MacroCall.parser]`）· `grammar/verilog/02_declarations/00_base.toml`
> （`TypeSpec`/`TypeSpecNoReg` 类型位 `@MacroCall`）
> Test: `tests/engine/preprocessor/test_anchor_protocol.py`（锚名/守卫）·
> `tests/engine/linter/test_anchor_splice.py`（拼接语义）·
> `tests/languages/verilog/test_macro_type_slot.py`（类型位三例 + 子槽边界）·
> `tests/languages/verilog/test_macro_call_node.py`（锚名形态/可复现）·
> `tests/languages/verilog/test_macro_body_comment.py`（体注释不吞后续 token）·
> 真实语料守卫 `tests/e2e/test_real_corpus.py::test_file_parses_clean[ref_darkriscv.v]`

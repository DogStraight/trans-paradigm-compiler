# 0018 解析侧宏占位协议：宏 token 满足任意语法元素

- Status: accepted
- Date: 2026-09-13
- 关联：0017（宏任意位置 = 外层展开 + 渲染侧 raw 拼接）、0016（宏体进 AST）
- Doc: `parser/_production.py`（匹配器）· `core/token_protocol.py`（`macro.call` token）

## 背景

目标态（与作者逐条对齐）：

1. linter 检查**真展开态**——反向解析器要验"宏体铺进去后语法是否成立"
   （已落：`ctx.lint_source`，见 `pipeline/__init__.py::_stage_expand`）。
2. 预处理生成宏表（已有：`scan_directives` → `macro_defs` / `func_macros`）。
3. parser 对宏**不展开**，把宏调用拉成节点；下游消费节点（渲染还原原文、
   语义层按需展开宏体）。
4. 锚点机制收缩：只剩"空体宏占位"一个语义。
5. 多行语句误报（已修：pratt 中缀循环的行首运算符续行判据）。

问题：现状 parser 吃的是**锚形态**（宏调用被替换成 `__tpc_marker_*` 普通 id），
而锚的能力边界 = "该位置允许任意 id"（2026-09-13 实测）：

- 表达式位可用；**结构位（类型/关键字位）无产生式可匹配** →
  `` input `NT d; `` 在锚形态下解析失败（`tests/languages/verilog/test_macro_type_slot.py`
  的 6 个 xfail 即此）；
- 空体宏 / 整行宏只能整体消失（替换成注释占位），语法结构与真展开态不一致。

改动前基线（`_drafts/probe_raw_parse.py`，"扫指令后不展开"= 目标态解析输入）：
真实语料 9 个文件中 **4 个解析失败**（darkriscv / ice40_cells_sim / picorv32 /
tv80_core）——占位协议要消化的就是这 4 个面。

## 决策

1. **解析输入 = 扫指令后的原文本**（宏调用保持 `` `NAME ``，lexer 归
   `macro.call`），不再替换成锚。
2. **引擎级通配**：匹配器（`parser/_production.py` 的 token / call 匹配点）遇到
   `macro.call` token 时，视作"满足当前位置所需的**任意一个**语法元素"——消费 1
   token，产出 `MacroCall` 节点（源区间 + 调用原文）。语言包零宏知识：不需要任何
   槽位声明，"当前位置要什么元素"由匹配器当时的期待集决定（这正是 0017 撤销
   逐槽位声明后缺的那一环）。
3. **分工**：通配必然放宽 parser 的接受面（语义荒谬的宏位置也照收）——合法性由
   linter 的**真展开检查**兜底（背景 1）。两个机制互补，缺一不可。
4. **锚的处置**（迁移顺序即依赖顺序）：
   - 渲染还原 → 宏节点（原文）+ 区间表（宏体）接管，不再依赖锚名 / 盐 / 序号；
   - 锚的"替身"职责 → 由通配协议接管；
   - 锚保留的唯一语义 = **空体宏占位**（展开态不占 token / raw 态占一个 token
     的对账点，渲染与诊断行映射用）；
   - 先把 line / sync 两类锚的还原迁进区间表，再按"先证后删"收锚。

## 权衡

通配放宽了 parser 的接受面（语义荒谬的宏位置也照收）——这是**有意的取舍**：
把"宏体是否破坏语法"的检查责任集中到 linter 的真展开检查（一处、可测、
有真实语料门禁），parser 只负责结构。

被拒的备选：
- 逐槽位声明（0017 已撤销）：补不齐，部分槽位静默错渲染；
- 解析输入改真展开：把宏体语法责任压给 parser，实测真实语料 `parse truncated`。

## 验证

- `test_macro_type_slot.py` 6 个 xfail 翻正（结构位宏）；
- 真实语料 raw 解析的 4 个失败文件 → 0（同 `_drafts/probe_raw_parse.py` 口径）；
- lint 吃真展开（已落）不退化：全量门禁 / e2e FAIL 0 / 误报基线无增长；
- 格式化对拍：宏调用原文回填、无锚残留、输出幂等。

> Impl: `parser/_production.py`（`macro.call` 通配点，待实现）
> Test: `tests/languages/verilog/test_macro_type_slot.py`

## 已废弃（被本决策推翻或替代）

- 早期"语言包逐槽位声明 `@MacroCall`"（0017 决策 2 已撤销）：补不齐且部分槽位
  会静默错渲染。
- "解析输入改真展开"（2026-09-13 实验）：把宏体语法责任压给 parser 是错的分工，
  且实测真实语料 `parse truncated`。

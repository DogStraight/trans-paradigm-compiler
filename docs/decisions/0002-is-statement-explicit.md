# ADR-0002: is_statement 显式声明（而非推导）

- Status: accepted
- Date: 2026-08-02（本 ADR 于 2026-08-09 沉淀）

## 背景

`is_statement` 曾有推导：`derive_rule_roles`（块规则推导 + statement_entry 沿纯 @ 分派选择器展开）+ `lookahead._context_leaves`（从 ModuleItem/Stmt 根选择器再展开一遍）。同一件事做两遍，"为了发现而发现"。且推导对模型/改造者是隐性知识，追踪成本高、易误改。

## 决策

37 条语句规则在 TOML 直接标 `is_statement = true`；删除 `derive_rule_roles`/`_expand_statement_entry`/`_is_selector_rule`/`_STATEMENT_REF_RE`。入口选择器（Stmt/TaskStmt/ModuleItem）不标 is_statement。块规则（ModuleDecl/FuncDecl/TaskDecl/BeginEnd/GenerateBlock）同样显式标 is_statement。

（2026-08-18 更新：`statement_entry` 角色值/`body_context`/`[linter]` 集中配置全部删除——语句发现从 is_statement 规则 + block_start 结构自推导，B 类 ident 候选是单一全局集合，不按上下文分组。c4 语言包无任何额外字段即可跑 linter。）

## 权衡

- 代价：配置里多写一行字段（声明式）。
- 换取：删除 4 个推导函数；消除隐性语言知识；改造者（人/模型）一眼可见，零歧义。
- 原则：**声明优于推导**——用规则名做逻辑分支是跨语言漂移点；用配置/字段安全。
- 推广：本 ADR 确立的原则适用于全部推导链（`_is_atom_selector`/first-token/block_start 还原等），后续逐一收敛。

## 验证

231 + run_all 35（FAIL 0）+ normal 28/28 + errors 3/3 全绿。

> Impl: grammar/verilog/**/*.toml（is_statement = true）
> Impl: core/define.py（规则字段解析）
> Test: tests/engine/linter/test_linter_lookahead.py

# ADR-0001: 前置 token 级 linter（而非错误恢复 parser）

- Status: accepted
- Date: 2026-08-09

## 背景

传统语言工具的 linter 依附 AST：parse 成功后才遍历 AST 检查，语法有错时 AST 构建失败，检查失效或需容错解析器。带错误恢复的 LL 解析器（错误产生式/同步集合/级联抑制/恢复状态一致性）是编译器工程公认最难的复杂度。

## 决策

linter 前置于 parser（`config/tpc_config.json` stages: `lex → lint → parse → ...`），直接消费 token 流产出错误诊断，不构建 AST；parser 只解析合法输入。语法配置与 parser 同源（同一份 `grammar/*.toml`），复用部分解析器基础设施（pratt + 共享 RuleMatcher）。

## 权衡

- 代价：真实为 lex×2（linter 内部再 tokenize）+ 一次 O(n) token 扫描 + parse×1，均为线性低常数。
- 换取：省掉"错误恢复解析器"的复杂度爆炸维度；parser 纯净无状态污染；诊断独立可测；lint/parse 语法知识零漂移。
- 备选：单遍带错误恢复的 LL 解析器（拒绝：复杂度不可控，且破坏配置同源）。

## 验证

31/31 recall、0 false positive、0 known_miss；normal 28 零误报；残缺/无末尾换行代码均可检出。

> Impl: linter/scanner.py::LinterScanner.scan
> Impl: linter/discovery.py::Discovery.discover
> Impl: linter/checkers/matcher.py::RuleMatcher
> Test: tests/engine/linter/test_linter_discovery.py
> Test: tests/engine/linter/test_linter_matcher.py
> Test: tests/e2e/eval_lint_accuracy.py

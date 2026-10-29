# linter — 前置 token 级 lint（反解析器，复用同一 TOML 语法）

> parser 之前对 token 流做轻量错误扫描。语言规则复用 `grammar/` TOML（反解析器
> ——同一语法文件既驱动 parser 也驱动 lint 语句发现），不含硬编码语言知识。

| 文件 | 一句话 |
|------|--------|
| `scanner.py` | 两阶段 Linter 编排器（发现 + 扁平检查） |
| `checkers/` | 扁平检查器族（`matcher.py` 规则匹配 / `expression.py` pratt 复用 / `macro_hygiene.py` 宏指令卫生 / `style.py` 排版卫生 ST 族） |
| `checker.py` | 扁平检查器协议与注册表 + 发现节点（`DiscoveredNode`/`UnrecognizedSite`） |
| `discovery.py` | 发现阶段（语言无关推导组件）：token 流 → 轻量结构树 + 未识别位点 |
| `lookahead.py` | 动态两级前瞻消歧表 |
| `grammar_slicer.py` | 从语法规则推导切分层级映射 |
| `first_set.py` | FIRST 集单一实现（保守/可空两种语义） |
| `discovery_shape.py` | 语句发现形态声明（语言包 `[discovery]`，ADR-0025） |
| `diagnose.py` | 条件编译多路径诊断（枚举所有路径逐条 lint 汇总） |
| `macro_syntax.py` | 宏定义的**形式化语法**检查（AST 前；语言包声明 `[macro_syntax]` 才启用；`tpc lint` 与 `tpc check` 的语法阶段**共用同一实现**——后者按原文补查，见 `analyzer/structure.py::raw_source_macro_diags`） |

> **结构推导是本包内部组件**（切片树 / FIRST / 前瞻消歧 / 发现树，不设独立顶层包）：
> 本包负责检查器与诊断；`islands/`（片段模式）直接消费本包的推导 API。
> 架构总述见 `linter/linter_architecture.md`；精度评测见
> `tests/e2e/eval_lint_accuracy.py`（recall/误报门禁）。
> CLI 诊断入口是 `main.py` 的 `tpc lint`（`cli.py` 重复实现已删）。

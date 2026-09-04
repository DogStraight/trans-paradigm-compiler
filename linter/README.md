# linter — 前置 token 级 lint（反解析器，复用同一 TOML 语法）

> parser 之前对 token 流做轻量错误扫描。语言规则复用 `grammar/` TOML（反解析器
> ——同一语法文件既驱动 parser 也驱动 lint 语句发现），不含硬编码语言知识。

| 文件 | 一句话 |
|------|--------|
| `scanner.py` | 两阶段 Linter 编排器（发现 + 扁平检查） |
| `discovery.py` | 发现阶段：token 流 → 自动注册的扁平检查器列表 |
| `checkers/` | 扁平检查器族（`matcher.py` 规则匹配 / `expression.py` pratt 复用） |
| `checker.py` | 扁平检查器协议、注册表与轻量 AST 节点 |
| `lookahead.py` | 动态两级前瞻消歧表 |
| `grammar_slicer.py` | 从语法规则推导切分层级映射 |
| `diagnose.py` | 条件编译多路径诊断（枚举所有路径逐条 lint 汇总） |
| `cli.py` | linter 诊断输出（CLI 入口） |

> 架构总述见 `docs/linter_architecture.md`；精度评测见
> `tests/e2e/eval_lint_accuracy.py`（recall/误报门禁）。

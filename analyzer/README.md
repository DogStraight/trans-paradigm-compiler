# analyzer — 语义分析（作用域、符号、类型 + 检查插槽）

> AST → 作用域/符号/诊断。类型与检查规则由 `grammar/` 声明（语义检查原语 +
> 插件 [analyzer] 段 / `[[checks]]` 表），引擎骨架语言无关。

| 文件 | 一句话 |
|------|--------|
| `scope.py` | Scope（作用域链）+ Symbol（符号声明）类型 |
| `context.py` | AnalysisContext（分析上下文/诊断上报） |
| `traversal.py` | AnalysisTraversal（遍历 + post-pass 钩子调度） |
| `diagnostic.py` | 结构化诊断 + related 链 |
| `checker.py` | ProjectChecker（跨文件语义检查引擎） |
| `checks.py` | L1 声明式检查规则执行器（规则 = 数据） |
| `suppress.py` | 诊断豁免注释（Verilator lint_off 借鉴） |
| `primitives/` | 语义检查原语（symbol 声明/引用核对等） |

> 语义检查插槽总述见 `analyzer/semantic_checks.md`；加检查规则见
> `.agents/skills/checker-rule-authoring/SKILL.md`（L1 声明式 / L2 handler-postpass）。

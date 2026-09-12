# analyzer — 语义分析（作用域、符号、类型 + 检查插槽）

> AST → 作用域/符号/诊断。类型与检查规则由 `grammar/` 声明（语义检查原语 +
> 插件 [analyzer] 段 / `[[checks]]` 表），引擎骨架语言无关。

| 文件 | 一句话 |
|------|--------|
| `scope.py` | Scope（作用域链）+ Symbol（符号声明）类型 |
| `context.py` | AnalysisContext（分析上下文/诊断上报） |
| `traversal.py` | AnalysisTraversal（遍历 + post-pass 钩子调度） |
| `diagnostic.py` | 结构化诊断 + related 链 |
| `checker.py` | ProjectChecker（工程检查门面：结构提取底座 + 检查编排 + 诊断汇总）。结构提取底座（elaboration 三层，协议见语言包 `[structure] protocol`）是**通用设施**——消费方不止检查，各 postpass/插件都读它注入的 `module_index`/信号图 |
| `report_html.py` | check 报告 → HTML（诊断的呈现视图，CLI `--html`） |
| `checks.py` | L1 声明式检查规则执行器（规则 = 数据） |
| `suppress.py` | 诊断豁免注释（Verilator lint_off 借鉴） |
| `primitives/` | 语义检查原语（symbol 声明/引用核对等） |

> 语义检查插槽总述见 `analyzer/semantic_checks.md`；加检查规则见
> `.agents/skills/checker-rule-authoring/SKILL.md`（L1 声明式 / L2 handler-postpass）。

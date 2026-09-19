# analyzer — 语义分析（作用域、符号、类型 + 检查插槽）

> AST → 作用域/符号/诊断。类型与检查规则由 `grammar/` 声明（语义检查原语 +
> 插件 [analyzer] 段 / `[[checks]]` 表），引擎骨架语言无关。

| 文件 | 一句话 |
|------|--------|
| `scope.py` | Scope（作用域链）+ Symbol（符号声明）类型 |
| `context.py` | AnalysisContext（分析上下文/诊断上报） |
| `traversal.py` | AnalysisTraversal（遍历 + post-pass 钩子调度） |
| `diagnostic.py` | 结构化诊断 + related 链 |
| `checker.py` | ProjectChecker（工程检查**门面 + 组合根**：装配六个结构提取协作者 + 分阶段诊断汇总）。结构提取细节全在 `structure.py`，共享组件装载在 `shared_components.py` |
| `shared_components.py` | 检查侧共享组件装载（按 `rules_dir` 缓存的 rules/rule_selector/lexer/linter/renderer；与 pipeline 侧 `_PIPELINE_SHARED` 刻意分离） |
| `diag_serialize.py` | 诊断 → LSP 形状序列化（两阶段 stage/range/macro/related；纯函数 + 行号回源，与检查逻辑正交） |
| `structure.py` | 结构提取（elaboration 三层）——**组合式**：`StructureCtx`（会话上下文：环境开关 + 索引 + 语言包 `[structure] protocol` 协议读取）+ 六个阶段协作者（`ModuleIndexer` 发现 / `FilePipeline` 单文件装配 / `ModuleExtractor` 单元提取 / `ConnectionElaborator` 连接展开层 2 / `SignalGraphBuilder` 信号图层 3 / `GenerateEvaluator` 条件求值）。**通用设施**，非检查专用：消费方含各 postpass/插件（读它注入的 `module_index`/`inst_sites`/信号图） |
| `report_html.py` | check 报告 → HTML（诊断的呈现视图，CLI `--html`） |
| `checks.py` | L1 声明式检查规则执行器（规则 = 数据） |
| `suppress.py` | 诊断豁免注释（Verilator lint_off 借鉴） |
| `primitives/` | 语义检查原语（symbol 声明/引用核对等） |

> 语义检查插槽总述见 `analyzer/semantic_checks.md`；加检查规则的双路径实操见
> `grammar/verilog/plugins/checks/README.md`（L1 声明式 / L2 handler-postpass）。

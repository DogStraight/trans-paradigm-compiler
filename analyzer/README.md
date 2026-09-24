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
| `structure.py` | 结构提取的**文件层**（引擎唯一可视单位 = **文件**）：`StructureCtx`（会话上下文：环境开关 + 索引 + `[structure]` 协议读取）+ `ModuleIndexer`（依赖发现）/ `FilePipeline`（单文件装配）/ `ModuleExtractor`（单元注册表——**只剩**名字 / 文件 / 声明节点）。⚠ 原层 2/3（连接展开 / 信号图）与 generate 求值已按 ADR-0019 迁入语言包插件 |
| `elaboration/` | **精化协议**（ADR-0019）：契约与声明校验（`contract.py`）/ 驱动器（`driver.py`）/ 原子供源（`atoms.py`）/ 语言无关服务句柄（`service.py`）/ 能力读取点（`loader.py`）。**只提供机制**——项列表与全部语义求解在语言包插件（`grammar/<lang>/plugins/elaboration/`） |
| `report_html.py` | check 报告 → HTML（诊断的呈现视图，CLI `--html`） |
| `checks.py` | L1 声明式检查规则执行器（规则 = 数据） |
| `suppress.py` | 诊断豁免注释（Verilator lint_off 借鉴） |
| `primitives/` | 语义检查原语（symbol 声明/引用核对等） |

> 语义检查插槽总述见 `analyzer/semantic_checks.md`；加检查规则的双路径实操见
> `grammar/verilog/plugins/checks/README.md`（L1 声明式 / L2 handler-postpass）。

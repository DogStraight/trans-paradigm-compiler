# ADR-0005: 跨文件语义检查 + tpc check 分阶段出口

- Status: accepted
- Date: 2026-08-25

## 背景

ADR-0004 定了 analyzer 阶段语义检查插槽（双层规则 + post-pass 链式检查），
但两个落地缺口未覆盖：

1. **跨文件联动**：用户场景是"文件 A 实例化模块 B（定义在另一个文件），
   B 的端口/参数/位宽变了，A 没跟上"——错误范式在**文件联动**处，单文件
   分析无法发现（模块名拼错、端口名不存在、参数覆盖不存在、字面量宽度
   与参数化端口错配）。
2. **分阶段错误出口**：最终交付形态是 lint 可执行文件，用户要"分阶段拿
   到错误"——linter 部件产语法错误，analyzer 插件产语义错误，两个阶段
   可区分、可过滤、可分别消费。

## 决策

### 1. 职责边界（不改造 linter）

- **linter 部件不动**：只产出 token 级语法错误（ADR-0001 现状保持）。
- **语义检查全部在 analyzer 插件层**：语法错误（`tpc lint`）与语义错误
  （`tpc check`）是**两个命令、两个阶段**。`tpc lint` 保持语法-only
  （向后兼容）；新增 `tpc check` 跑语义（parse 成功后）。

### 2. 跨文件引擎（`analyzer/checker.py::ProjectChecker`）

- **单文件入口 + 自动递归**：从入口文件的模块实例化点出发，找被实例化
  模块的定义文件（同目录、`--include` 目录；同名 `<name>.v/.sv` 优先，
  再扫描文本匹配 `module <name>`），递归分析；**memo** 文件级去重 +
  **环防护**（互指定义不死循环）。
- **模块定义表**（`ModuleInfo`）从 AST 提取声明形态（端口名/方向/宽度
  表达式、参数名/默认值），不依赖符号表——联动检查只需要"声明形态 vs
  实例化点"的比对。
- **语言无关边界**：引擎只提供跨文件上下文，经
  `AnalysisTraversal._external_extra` 注入每个文件的
  `context.extra`：`module_index`（全工程模块表）与 `inst_sites`（本
  文件实例化点）。**"端口存在性/参数存在性/宽度联动"等 Verilog 语义
  规则是插件（`grammar/verilog/plugins/inst_check/`）的 postpass**，
  引擎零语言知识。

### 3. 语法有错 → 语义跳过

与 ADR-0001 一致（parser 只解析合法输入）：文件有语法错误时语义阶段
跳过该文件（不基于残缺 AST 报语义误报），语法错误本身照常报出。

### 4. 位置溯源（语义诊断定位）

AST 节点原本无源位置——parser 节点创建点（`_production.py` 块/普通规则
两处）统一挂 `_pos_line`/`_pos_col`（通用引擎能力，语言无关）；
`Node.dump()` 过滤下划线前缀元数据，不污染 AST 序列化。语义诊断 +
`Diagnostic.related` 链据此定位；related 节点可跨文件（`_file` 属性）。

### 5. 实例插件（`inst_check`）

首个跨文件联动插件，规则码：
- W101 实例化未找到定义的模块（定义缺失/拼写错误）
- W102 连接了不存在的端口
- W103 覆盖了不存在的参数
- WC001 字面量连接参数化宽度端口（ADR-0004 配置敏感死值场景，
  related 链：实例化点 ← 模块定义处 ← 端口声明处）

## 权衡

- 代价：递归发现 + 每文件 parse×1 + analyze×1（memo 后线性）；模块表
  从 AST 提取是"声明形态"而非完整 elaboration——宽度联动只做"参数化 vs
  字面量"的启发式，不做数值求值（求值属 Verilator elaboration 领域）。
- 换取：文件联动错误范式（HDL 工具空白）；分阶段错误出口贴合 lint 可
  执行文件的交付形态；插件边界让一线参与者贡献规则不碰引擎。
- 被拒绝备选：① 改造 linter 承载语义——违背"linter 只产语法错误"的
  定位，token 级无符号表；② 完整 elaboration/宽度求值——超出范围，与
  Verilator 重叠；③ 工程级目录扫描入口——用户拍板先做单文件递归。

## 验证

- pytest：`tests/engine/analyzer/test_checker.py`（递归发现/环防护/
  W101-W103/WC001/语法跳过/干净文件）、`test_diagnostic_related.py`
  （related 序列化）。
- e2e：`eval_lint_accuracy.py` 31/31 recall、0 fp 不回归（linter 未动，
  parser 位置挂载改动全量验证）。
- CLI：`tpc check` 文本/JSON 输出（stage 字段），exit code 按 error 级。

> Impl: analyzer/checker.py::ProjectChecker（递归+memo+模块表）
> Impl: analyzer/traversal.py::AnalysisTraversal._run_postpasses（postpass 执行）
> Impl: analyzer/diagnostic.py::Diagnostic.related（链字段）
> Impl: core/plugin_loader.py::_load_postpasses/get_analyzer_postpasses
> Impl: parser/_production.py（节点位置挂载）
> Impl: grammar/verilog/plugins/inst_check/（联动规则 postpass）
> Impl: main.py::_cmd_check（tpc check CLI）
> Test: tests/engine/analyzer/test_checker.py / test_diagnostic_related.py

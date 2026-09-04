# ADR-0004: analyzer 阶段语义检查插槽（双层规则 + post-pass 链式检查）

- Status: accepted
- Date: 2026-08-22

## 背景

用户场景：Verilog 接口端口位宽是**配置化**的（如 `[DATA_W-1:0]`），人写代码时按模块内部宽度写了一个**可能是死的值**（字面量 `16'hFFFF`）来测试；单独测模块没问题，外部修改端口位宽后产生非预期行为。长赋值链下人和 LLM 都因上下文注意力涣散而不敏感。

前置调研（`references.md`「静态检查器功能调研」节）结论：

- Verilator 等已覆盖宽度/截断检查，但发生在 **elaboration 后按具体参数值**检查——`DATA_W=16` 时 `16'hFFFF` 合法，改 8 才报；**"配置可能变"它结构上无法知道**。
- HDL 领域**无任何工具做跨语句链级溯源**。
- 五规则引擎（Semgrep/CodeQL/ESLint/clang-tidy/Ruff）共识：规则元数据=数据、匹配逻辑=数据或代码、统一抑制、统一报告、按层测试。

现状盘点：tpc 已有 analyzer 原语机制（`@register` + `[RuleName.analyzer]` 配置键触发，`check_name_call` 为现成范式）与 LSP 兼容 `Diagnostic` 报告通道，但无规则元数据、无用户级规则选择、无 post-pass（跨节点/链式）能力、无抑制机制。

## 决策

在 analyzer 阶段建立**语义检查插槽**，采用**双层规则模型 + post-pass 机制**：

### 1. 双层规则

- **L1 声明层（规则=数据）**：TOML `[[checks]]` 声明规则——`id`/`category`/`severity`/`scope`/`message`（模板插值）/可选 `handler` 引用。覆盖 80% 结构形态检查。
- **L2 脚本层（复杂检查=代码）**：复用现有 `@register` 原语 / handler 模块机制，规则声明引用实现。两层**共享同一报告管道**（消息模板/severity/位置/链）。

### 2. post-pass 钩子（机制核心）

现有原语是节点锚定的（访问某节点时触发），链式检查需要"遍历时收集 → 结束后走查"。新增 `[analyzer] postpasses = ["_chain_walk.py:run"]`——遍历完成后调用，访问已收集的符号/端口/赋值链。这是现有 `_resolve_pending`（遍历后统一核对）模式的通用化，机制已验证过。

### 3. 差异化边界（不重造轮子）

- **不做**：宽度截断/未连接/未使用/锁存器等 Verilator 已覆盖的检查。
- **只做**：① 配置敏感类检查（唯一性——tpc 的配置体系在自己身上，能查"字面量 vs 符号宽度"）；② 链级溯源（稀缺性——报告带赋值链）；③ 声明式规则机制（通用性）。

### 4. 统一层（一次做对）

- **抑制**：`// tpc-disable[rule-id]`、`// tpc-disable-next-line`、文件级、配置 ignore——声明层脚本层共用。
- **报告**：`Diagnostic` 增加 `related`/`notes` 字段（LSP `relatedInformation`），承载链溯源。
- **用户配置**：项目级 `tpc.toml` `[checks]`——`enabled`/`overrides`（severity 提升）/`per_file`（Ruff per-file-ignores 式，测试台豁免）。

### 5. 分阶段落地

| 阶段 | 内容 |
|---|---|
| P1 | 机制层：post-pass 钩子 + `Diagnostic.related` 链 + 统一抑制语法 |
| P2 | `width_check` 实例插件（窄版：参数化端口 + 字面量 + 单链） |
| P3 | L1 声明式规则 schema + 注释驱动测试（ruleid:/ok:） |
| P4 | 用户配置层 `[checks]`（enabled/overrides/per_file） |

## 权衡

- 代价：post-pass 增加一次遍历后的额外走查（成本与链长度相关，需限制）；声明式 schema 是初期投入，收益在规则可配置/可测试/可分发。
- 换取：配置脆弱性检查（Verilator 结构性不可能）、链级溯源（HDL 空白）、规则"配置优先、脚本兜底"的用户自定义层。
- 被拒绝备选：① 自研完整数据流引擎——超出范围，链式走查按需收集即可覆盖目标场景；② 纯脚本规则（无声明层）——丢配置性，用户无法不开代码地选规则调 severity；③ 依赖外部 linter（Verilator）做宽度检查——无配置敏感性，无法链溯源，且引入外部工具依赖。
- 边界纪律：P1 机制层验证通过前不写 P2 的宽度语义；不重造 Verilator 已有检查（见决策 3）。

## 验证

- P1：post-pass 钩子单测；`Diagnostic.related` 链序列化单测；抑制语法单测。
- P2：用户复现场景（改端口位宽 → 抓到链上死值）作为验收用例。
- P3：把 WC001 从脚本层迁到声明层，注释驱动测试全绿。
- P4：e2e 验证 `[checks]` 配置生效与 per_file 豁免。

## 落地演进（2026-08-29 追加，自 references.md「命名规则配置面设计」迁入）

P1-P4 全部落地后，声明式规则机制的策略演进（数据决策，非固定策略）：

### NC 命名规则默认关（e93ab9f）

- 背景：试水实测 NC 族默认全开 + 小写下划线 pattern 对真实代码（混合
  风格）~1300 条误报海啸。用户定调：命名风格主轴 = 蛇形 + 大小驼峰；
  比风格更有价值的是**前后缀语义约定**（防错）。
- `[[checks]] default = false`：NC 族默认关闭（规则=数据，语言包声明）。
- 启用语义（analyzer/checks.py）：显式 enabled = "不选即关"（P4 不变）；
  缺省 = default=true 的规则 ∪ overrides/per_file **引用即启用**（per_file
  豁免对默认关闭的规则才有意义）；ProjectChecker.enabled_rules 注入。
- NC001/NC002 pattern 放宽为 PascalCase 或 snake_case（行业惯例；真实
  语料 picorv32/serv 均 Pascal）。
- 默认关后真实语料 NC 诊断归零（默认体验不刷屏；启用才按团队约定查）。

### 前后缀语义约定（NC014-016，防错）

- 声明式表 + handler（name_check/rules/_prefix_suffix_check.py）：
  - **NC014 端口方向后缀**：`direction_suffix` 表（input→_i / output→_o /
    inout→_io）——名字以某方向后缀结尾但声明方向不同 → 方向可能接反
    （防错核心，强约束）；`require = true` 时未按本方向后缀命名也报。
  - **NC015/NC016 类型后缀**：`kind_suffix` 表（wire→_w / reg→_r）。
  - 豁免：`_` 前缀（占位/故意不用约定，与 unused_check 同语义）。
  - 默认关，启用走 P4 用户配置 enabled。
- **评估不做**：低有效 `_n`、时钟/复位前缀 `clk_`/`rst_`——Verilog-2005
  无 clock/reset 符号 kind，用途判定需事件控制/复位条件分析（主流 svlint
  亦无此类规则）；用户可按团队约定自写 pattern 规则（配置面扩展点）。
- 默认策略（0.1.1）：风格弱约束（只报混用）/前后缀强约束（声明了才查）。

> Impl: analyzer/checks.py::check_rules_pass（kind 分发执行器）
> Impl: core/check_registry.py（规则表加载/用户配置校验）
> Impl: analyzer/checker.py::ProjectChecker（跨文件检查引擎）
> Impl: grammar/verilog/plugins/checks/name_check/（NC 族 + rules/ + cases/）
> Test: tests/engine/analyzer/test_check_test.py + tests/languages/verilog/
>       test_name_convention.py
> 机制设计见 analyzer/semantic_checks.md（架构"怎么拼"）

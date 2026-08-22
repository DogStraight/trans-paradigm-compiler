# ADR-0004: analyzer 阶段语义检查插槽（双层规则 + post-pass 链式检查）

- Status: accepted
- Date: 2026-08-22

## 背景

用户场景：Verilog 接口端口位宽是**配置化**的（如 `[DATA_W-1:0]`），人写代码时按模块内部宽度写了一个**可能是死的值**（字面量 `16'hFFFF`）来测试；单独测模块没问题，外部修改端口位宽后产生非预期行为。长赋值链下人和 LLM 都因上下文注意力涣散而不敏感。

前置调研（`docs/references/static_checkers_survey.md`）结论：

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

> Impl: 待实现（P1 起，见 docs/semantic_checks.md 机制设计）
> Test: 待实现（tests/ 下随各阶段新增）

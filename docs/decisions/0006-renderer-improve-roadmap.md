# ADR-0006: 渲染器改进路线（边界分析 + 资产盘点 + 迁移策略）

- Status: accepted
- Date: 2026-08-25

## 背景

renderer 审查（2026-08-25）暴露理论边界（body_cfg["indent"] 死配置、
幽灵 indent 参数、render_node/render_inline 重复），修复（a1b29ed）
后定性：**改进非重写**——Doc IR 内核（Wadler）正确、布局 TOML 是
语言知识存量、验证门禁原样承接。框架调研（topiary/dprint/prettier/
verible/cmake-format）落 docs/references.md。TODO P5 固化六项改进
方向，要求"动手前先写 ADR-0006"。本文档即 P5 的输入：边界分析
（为什么改）+ 资产盘点（继承什么）+ 迁移策略（怎么改不破坏）。

## 边界分析（现状能力边界）

### B1 缩进无统一模型

四个缩进来源并存：`style.indent_str` / `body_cfg["indent"]` /
expr `{indent: N}` / Nest 原语；`render_node(node, layout, indent,
renderer)` 的 indent 参数只传递不消费（`primitives/indent.py` 的
`eval_indent` 也只是传递）——"幽灵参数"。组合规则与优先级未定义，
语言包作者只能凭经验手拼 Break/Nest。

### B2 group 二元全局 → 表达不了对齐

Union(flat/broken) 二选一，无中间态；fits 只测第一行、贪心。
跨行对齐是"组内列宽统一"的全局约束（列宽取决于整组），二选一
模型不可表达——column_align 被迫在世界 B 做文本后处理即是证据。

### B3 注释非一等公民

世界 A：`inline_comment.py` 锚点回插（渲染后字符串级后处理，±3 行
窗口启发式，锚点漂移即丢）；世界 B：`LineContext.has_trailing_comment`
只有布尔标记，无注释文本/锚点。折行/重排后注释无法随行锚定。

### B4 规范化 vs 保真方向矛盾

normalizer 消除 optional/repeat/seq（语法层结构保留），渲染 =
完全重排；源格式信息（空行/折行/对齐）在 AST 阶段已丢。verible
token 级保真（空行保留可配）在现有单通道下不可达。

### B5 世界 B 行上下文与 AST 分离

LineContext 是 行号+文本+scope 栈，与 AST 无关联；pass 靠行号
耦合——wrap 拆行后 contexts 失效（行号漂移，二次 format 漂移）。
命令式重复：column_align/inst_port/wrap 各自实现行扫描
（grouping.py 被提取为公共工具，即重复的实证）。

## 资产盘点（改进可继承的六类）

1. **Doc IR 内核**：Wadler-Lindig `layout/_best/_fits` 正确性已被
   yaml/c4 世界 A 验证——内核保留，只加原语。
2. **布局 TOML 存量**：46 个顶层 `[x.renderer]` 表 + 137 个
   layout/body/tail 子段（verilog 46 表 + 115 子段、c4 13 子段、
   yaml 9 子段）——语言知识资产，迁移必须零改写。
3. **primitive DSL 注册机制**：`registry.py` @register 动态注册，
   新增原语（align/fill/lineSuffix）是"加原语"不是"改内核"。
4. **世界 B pass 资产**：column_align 列推断 / inst_port 对齐 /
   wrap 断点 / grouping 分组逻辑——格式知识，升格为引擎内建遍。
5. **boundary 结构识别**：token 流 → scope 栈/ifdef 分支/块头块尾
   （从语法规则自动推导，零硬编码）——结构知识，升格为"带结构行"
   的骨架。
6. **验证门禁**：real 保真度守卫（ref_picorv32/tv80_core/darkriscv）
   / vs Verible 差分 124 例 / 幂等 / e2e——改进全程原样承接。

## 决策：迁移策略（分阶段，每阶段独立可验证）

### 阶段 0 — 本文档（输入定型）

边界/资产/迁移路线定稿，P5 六项对应到阶段。

### 阶段 1 — 统一缩进模型（清幽灵 indent 参数）

- 原语协议签名收窄（indent 不再穿透传递）；缩进来源归一为单一
  缩进上下文，明确组合规则与优先级（style → body_cfg → expr 覆盖）。
- 验收：协议签名中幽灵参数消失；806 pytest 全绿；real 保真度零下降。

### 阶段 2 — Doc IR 原语升级

- 新增 align（对齐进 Doc 模型）/ fill（流式折行）/ lineSuffix
  （尾注释锚定）+ 注释 attachment 机制（Prettier 生产验证过的
  原语集）；layout() 继承扩展（Wadler 内核算法不动，只加分支）。
- 验收：新原语单测 + 世界 A 存量输出不变。

### 阶段 3 — 世界 B 升级（text pass → 引擎内建遍）

- column_align/inst_port/wrap 从手写文本 pass 升格为引擎内建遍
  （量化布局拒绝准则，cmake-format 借鉴）；"行 + 所属 AST 节点"
  的带结构行，根治 wrap 拆行后行号漂移。
- 验收：世界 B 输出与现 pass 逐行一致（先双跑对比，再切内建）。

### 阶段 4 — 布局意图声明化（多遍引擎）

- 语言包声明"结构 → 布局意图"（对齐/紧凑/折行/锚定），引擎推导
  具体 Doc，消灭手拼 Break/Nest；多遍引擎：对齐遍/折行遍/注释遍
  （topiary 封闭式理念的落地形态——节点级注解 + 引擎内建遍）。
- 验收：新语言包可纯声明布局意图；布局 TOML 存量仍零改写可用。

### 阶段 5 — 保真度分级

- 规范化程度显式可配：完全重排 / 保留空行 / 仅缩进（verible
  token 级保真为参照）；normalizer 侧保留源格式信息。
- 验收：三级 fidelity 各有测试，real 保真度守卫分级可配。

### 兼容约束（全程）

- 布局 TOML 存量语义兼容（老语言包零改写）。
- 验证门禁原样承接（real 保真度 / vs Verible 差分 124 / 幂等 / e2e）。

## 权衡

- 被拒绝备选：
  - 全重写为 topiary 式纯声明 formatter：节点级注解到不了跨行
    对齐（references 实证），且布局 TOML 存量需重写——丢弃资产。
  - 换 dprint 平台：配置是选项非布局规则，语言插件仍需手写
    printer——未解决"声明化"痛点。
  - 直接上 verible 形态（token 流 + 布局决策）：放弃已验证的
    Doc IR 内核，且与双世界并存成本高——作为参照而非替代。
- 代价：阶段推进期间双世界并存（世界 A/B 各自演进，阶段 3/4 合并
  是风险集中点）；原语升级是纯增量，风险低。

## 验证

- 每阶段独立验证（原语单测 + 门禁全量）；阶段 1 先清幽灵参数、
  阶段 3 先双跑对比再切内建。
- 最终验收：布局 TOML 存量零改写 + 门禁原样承接 + 新原语/保真度
  分级各有测试。

> Impl: renderer/doc.py::layout（内核扩展点；阶段 2 已加 Align/Fill/LineSuffix）
> Impl: renderer/primitives/registry.py（原语注册；阶段 2 已加 align/fill/line_suffix，
>       阶段 4a 已加 intent）
> Impl: renderer/primitives/intent.py（布局意图声明：compact/wrap/align/anchor）
> Impl: renderer/node_renderer.py::render_node（缩进上下文归一；阶段 1 已完成）
> Impl: grammar/verilog/plugins/formatter/（世界 B 升级目标）
> Test: tests/engine/renderer/（原语/缩进单测）+ tests/e2e/ + tests/differential/

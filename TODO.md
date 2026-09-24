# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## 架构：精化（elaboration）部件化 + 插件化（未开工）

> 作者定调（2026-09-19）：精化器逻辑应由**插件**实现，引擎侧只留"加载精化器的位"。
> 本仓已有同款机制可复用，不造第二套：`core/component_protocol.md` §1 的
> `[capabilities]` 能力位 + `get_capability_in(name, rules_dir)`（按语言包作用域，
> 切语言不串用）；先例 `macro_policy`（引擎薄适配器 `preprocessor/macro_policy.py`
> + 插件 `plugins/macro_policy/`）与 `formatter`。

- **现状错配（实测，`analyzer/structure.py`）**：
  - 文本模式求值/判断（应 AST-first）：`_is_signal_expr` 正则、`render_subtree` 渲染
    后再字符串比较（`== port`）、`_eval_gen_cond` 的 `text.isdigit()` /
    `text.startswith(not_op)` / `IDENT_RE.fullmatch`、`_tokenize_const` +
    `_CONST_TOK_RE` + `_eval_const_expr` 文本递归下降、`_param_truth` 值文本判数字。
  - 语言知识硬编码（应进插件）：`_fill_body_ports` 的 `_FUNC_OR_TASK` 元组、
    `_fill_body_params` 的 `"ParamDeclStmt"` / `"Declarator"` / `"init"`、
    `elaborate_connections` 的 `field("connects") or "ports"`、
    `_fill_body_ports` 的 `or "direction"`，以及"名字在 `Node.content`"这一未声明形态假设。
  - AST 证据（`_drafts/probe_ast_shape.py`）：取反在 AST 里是
    `UnaryOp(op='!', operand=HierExpr([Identifier('W')]))`——**不是文本前缀**；
    `Number.value` 今天有 str / Node 两种形态（形态知识进插件后由插件自认，无需对齐语法绑定）。
- **契约划分**：引擎基座 = ①加载位（能力名 + 未声明降级为单文件 lint+analyze）
  ②产物模型与 `context.extra` 键名（**形状属引擎协议**——消费方是下游 postpass，
  不能由插件定义）③语言无关服务句柄（读源 / 宏展开 / AST 解析 / 行映射 `line_map`、
  宏区间 `macro_regions`）。插件 = 全部语言语义（实例化点→目标模块名、按名找定义文件、
  单文件精化、**AST-first 求值规则**、驱动源三类形态、层次穿透、端口方向语义）。
- **分期**：E1 立零件（`analyzer/elaboration/`：契约 + 能力名 + 加载位 + 产物模型 +
  句柄，只新增不接线）→ E2 verilog 精化器整体搬进
  `grammar/verilog/plugins/elaboration/`，门面改经契约调用并**同批删引擎侧旧实现与
  `[structure]` 声明**（不留双路径）→ E3 插件内 AST-first 重写（删文本解析链）→
  E4 文档收口（`core/component_protocol.md` 加"精化器能力位"节 + 插件 README +
  `MODEL_INDEX`/`analyzer/README`）。
- 按建议定的两条：编排骨架（发现循环 / 汇总 / `extra` 注入）**留引擎**（无语言语义）；
  产物**运行期核验**（照 transform 插件 `produces` + `_verify_produced` 同款，
  少填产物键 → fail，不让下游静默空转）。
- 外部对照（为什么这不是过度泛化）：elaboration 是 HDL/EDA 的必备阶段（Verilator
  `V3Param` 删未选中 AST 子树、slang `Elaborator`、VHDL/Ada LRM 专章），通用语言侧
  同构概念（Racket phase、Scala macro elaboration、Zig comptime、C++ 模板实例化）；
  成熟实现一律在 AST/IR 上精化，文本只作输出与诊断呈现。注意中文"精化"与
  refinement（B/Event-B 规格精化）撞词，部件/配置名用 `elaboration`。


## 语言知识渗透复审与精化基座重设计（2026-09-20 立，长期）

> 作者定调：**近期主线 = Bifrost 审计修复**——**已收口**（2026-09-20 主体 +
> 2026-09-22 收尾：B-C 快照按 A–G 归位、`python-absent-member` 下边界判决、
> 能力族 ④ 变更差分接入流程、草稿区结论分流落正式位）。判据与门限见
> `policy/structural_budget.md`（口径/停止规则/基线）与 `policy/bifrost_audit.md`
> （判据集 + 已知边界 + 重构期用法）；当前基线 **S = 0**（每个命中都有结论；
> 原始量仍在，删 `structural_kept.json` 对应条目即可回滚），登记表完整性由
> `tests/policy/test_structural_kept.py` 守。
> **下一项 = 精化基座重构**（本文件首节的 E1–E4 执行面 + 下方 L2 的能力边界
> 设计原则，同一件事的两面）；L1 语言知识渗透复审仍是长期方向、不在近期排期。

### L1 语言知识渗透复审（长期）

- **范围（作者 2026-09-20 指定）**：**重点 analyzer / preprocessor / linter**；
  parser 与 lexer 基本形式化、renderer 主要吃原语、transform 是插槽形式（可能性小）
  ——但**实测校正**：parser 仍有一处分量级渗透（位宽字面量，见下）。
- **判据三条（强弱递减；详见 `docs/gaps/gap-language-penetration.md`）**：
  ① **最小语言包探针**（主判据，行为面）——只加载最小骨架包跑全量测试，仍绿的引擎
     测试 = 普适面；② **声明面缺失探针**（辅助，行为面）——临时删一段语言包声明跑测试，
     仍绿处 = 引擎替声明做事；③ **弱信号面** = `tools/lang_penetration.py`
     （引擎里出现语言包规则/节点名（硬信号）/ 语言对象词作标识符（弱信号，须人工判））。
  ⚠ 三条都只覆盖**被测路径** → 结论只能是"已知渗透面收敛"。
- **首轮实测（2026-09-20，词法/结构面；全表见 gap 档）**
  - **analyzer = 重灾区**（与作者判断一致）：`structure.py` 硬编码 5 个**规则名**
    （`"FuncDecl"/"FuncDeclOld"/"TaskDecl"`、`"ParamDeclStmt"`、`"Declarator"`）
    + 语义名词标识符 **183 处**（端口/实例/信号驱动）；`checker.py` 的 `_signal_graph`/
    `inst_sites`。**均归 L2（精化基座）**——不动，等 L1 其余面做完。
  - **parser**：11 处结构名命中全是**引擎表达式树/节点协议名**；原先当渗透的
    `_parse_bit_width_literal` 经**调用计数探针**实测在三语言包下**不可达**（lexer 按
    `[[number.based]]` 捕成单 token，规则的 `Number` 先手接住）→ 实为**冗余第二路径**，
    **已删**（钩子 + 槽位 + 登记条目）。
  - **pipeline**：`__init__.py` 曾按名调语言包的排版步骤（`split_port_close_lines` /
    `split_inst_tail_lines`）→ **已修**：能力面改声明 `pre_scan_passes`（前置文本遍列表）。
  - **linter / preprocessor / lexer / renderer / core / transform**：词法/结构面未发现活渗透
    （linter 的 21 处、renderer 的 18 处、lexer 的 7 处名词命中全是误报；
    `core/_protocol.py` 的 `ATTR_RESOLVED_PORTS` 等是**产物契约键名**，按既定决策留引擎 → 归 L2 重审）。
  - **同名陷阱**：`Root`/`Comment`/`UnaryOp`/`BinaryOp`/`TernaryOp`/`Number`/`Identifier`/
    `MacroCall` 是**引擎表达式树/节点协议**（语言包按此名声明 renderer），不是渗透。
  - ⚠⚠ **新判据（当场踩坑得出）**：弱信号命中要过四道——① 词法命中 → ② 看调用链定性
    → ③ **数调用次数（可达性）** → ④ 才分“渗透 / 死代码 / 契约”。
    只做到 ② 会把**不可达的冗余路径**当渗透，白花一道外置工序（本次实测）。
- **现有的两条门禁只覆盖词法面**（关键字字面量 / 配置键声明），为何抓不到语义渗透：
  用配置键或通用算法表达的 Verilog 语义里**一个 Verilog 词都没有** → 形式完全合规；
  配置点位法反而**奖励**这类渗透。两条门禁答的是"有没有**语言的关键字**"，
  而精化基座的问题是"有没有实现**语言的语义**"——前者是字符串问题，后者是判据问题。
- **下一步**：① 行为面基线（最小语言包探针）——判语义面的唯一办法，单独一期；
  ② 之后就进 L2（精化基座重设计；analyzer 的 5 个规则名 + 183 处语义面 + 产物契约键名都在那一批）。
- **另："多加语言包"作为暴露法的代价（已知事实）**：c4/yaml 覆盖浅，暴露力有限；
  且多语言同进程已有真实串味史（`_PIPELINE_SHARED` 按 rules_dir 缓存、
  `global_state` 语言注册面只增不还原、`test_language_switch` 曾偶发失败）→ 该法
  只在隔离跑（每语言一进程）下可用，不作日常手段。
- **状态**：方向已定（作者 2026-09-20），方法待选；未见排期。

### L2 精化基座重设计（引擎 vs 插件的能力边界）

- **作者定调（2026-09-20）**：重设计一次基座，**引擎只留"普适的文件操作 + 树化行为"**；
  把**抽取能力**（从树上取语言结构）与**动态求解**（常量/宽度/端口方向等语义求值）
  移到插件侧。现状是基座把**很多 Verilog 独有的操作在引擎内侧实现了**——作者判定为
  "明显的语义渗透"。
- **设计原则细化（作者 2026-09-20，防止走成"普适化 → 配置面膨胀"）**：
  **自带配置的增量设计**——引擎侧留**占位 + 简单实现**（能跑通最普适形态），
  语言特有的完整实现**集中到语言适配层**；这样配置复杂度与语言知识都落在插件侧，
  插件又靠引擎的原语组合而不必重复造骨架。
  - **三选一别走错**：引擎硬编码（禁） / **引擎配置字段（慎）** / **插件实现（首选）**。
    "为让引擎普适而设计一套 schema"会把复杂度从代码搬到配置，并为新形态预留表达力
    缺口——这是本仓已经踩过的形态（见下面的数字实证）。
  - **两条判据**：① *普适性*：去掉所有语言包声明后，引擎的简单实现能否对任意输入
    给出**可解释**结果？能 → 引擎；不能 → 插件。② *配置 vs 代码*：**能被表单穷举、
    且不涉及算法/状态机/语义求值**的少量变体 → 留配置；需要算法/状态机/求解的 →
    移插件代码。③ *增量*：插件只写"与默认的差"（override / 扩展点），不复制骨架。
  - **取舍的定位（作者 2026-09-20）**：声明式表达一切 ⇒ 配置面无限；不可能。所以做法是
    **把"会变动的结构"做成配置，把"特异的部分"做成语言包代码**——不是消灭取舍，
    而是把取舍**局部化**（每个决定只影响一个组件、可回滚、可被测试锁住）。
  - **把"会变动 vs 特异"变成可判的第三判据（看它在语言间的分布）**：
    | 语言间分布 | 归宿 |
    |---|---|
    | 多语言共有、且形态稳定（只有值不同） | **配置**（值走声明） |
    | 多语言共有、且结构一致（形态相同） | **引擎骨架**（上提，避免各语言复制声明） |
    | 单语言特有，或各语言形态各异 | **插件代码**（下沉） |
  - **两个可机械测的失效信号（用来发现"放错了"）**：① *该上提却还在配置*：同一 schema 下
    多个语言包的声明高度相似（复制粘贴式）→ 说明这是共性结构，应上提为骨架/默认；
    ② *该上提却还重复*：同一段逻辑出现在 ≥2 个语言包，或插件与引擎默认逐字同体
    （Bifrost 重复工具 + 现有 A–C 类判据可测）→ 应上提。两条都是**往返通道**：
    只能单向移动（一味下沉或一味上提）会累积另一种债。
- **普适原语必须共享**（否则各插件重写"跳空白"之类会漂移）：既有 `core/token_protocol`、
    `lexer/lexer_utils`、`core.define.iter_nodes` 已是这类原语，重设计时明确清单。
- **命中点与实证（本仓事实）**：
  - `analyzer/structure.py`：引擎侧实现了 generate 条件求值（`_eval_const_expr`/
    `_ConstExprParser`）、端口/参数抽取（`_PortFields`/`ModuleExtractor`）、
    信号图（`SignalGraphBuilder`）→ 属"抽取 + 动态求解"，是 L2 的首要搬迁面。
  - **数字形态（配置面膨胀的实证）**：旧 `NumberFSM` 硬编码单例**已不存在**
    （P2.1 配置化时移除，`lexer/main_lexer.py` 有记录）。现状是另一种形态——
    为让引擎普适，`grammar/verilog/base/_number.toml` 用 **7 个字段 × 4 个形态块**
    （`size.digits`/`base_prefix`/`signed`/`bases`/`value_digits`/`value_allow`/
    `value_allow_space`）声明形态，引擎侧 `number_gen._PatternBuilder`（通用 DFA
    构造）+ `number_runner` 把它编译成状态表。**加形态可能撞 schema 表达力边界**，
    这正是"普适化推高配置面"的样本。按新原则应改为：引擎留"十进制/浮点最简扫描"
    占位 + 数字扫描原语（字符类判定 / 最长匹配 / radix 取值），verilog 插件侧
    集中实现位宽·进制·x-z 形态。
  - 正面样板：`typed_ports`（抽取走插件 + TOML 声明，引擎零硬编码）。
- **诚实代价（写进 ADR 权衡）**：声明式 → 命令式后，**加语言不再是零代码**
  （c4/yaml 需写一小段插件或继承默认）；换来的是引擎 schema 与代码不随语言数增长。
- **已有约束须一并遵守**：语言知识零进代码（AGENTS 硬约束）、不留兼容垫片、
  删除先证后删（`policy/doc-alignment.md`）；配置加载 fail-fast。
- **预期待定**：属架构决策，动手前先立 ADR（`docs/decisions/`）；现仅记方向与命中点。
- **成熟解法参照（避免自造）**：
  - **GCC 的路线**：语言差异由**手写前端**接住（每个语言一个 front end），共享点在下游
    （GENERIC/GIMPLE IR + 后端 + 目标描述 `.md`）。它的"占位"不在前端骨架，而在
    `LANG_HOOKS`/`TARGET_HOOKS` 回调与机器描述文件——**取舍位置与我们相反**（它把共享点
    下移，我们把共享点上移到前端骨架）。另外 GCC 的机器描述是"配置面膨胀"的成熟解法样本：
    它给配置面配了**领域语言 + 代码生成器/校验器**（`.md` → `genrecog`/`genoutput`/
    `genattrtab`）——可见**配置面本身需要工具链管理**，否则就是纯负担。参照它设计我们的
    TOML→生成器/校验器（`number_gen` 这类"schema + 编译器"在**有生成器**时不算错）。
  - **LLVM**：IR 作为普适中间层的样本（前端/优化/后端三段解耦）。
  - **语言工作台（Xtext/Rascal/MPS）**：元语言 + 生成，与"配置表达式 + 插件补特异"同路线。
  - ⚠ 记录纪律：本仓文档不写"超过 X / 比 X 强"这类**不可验证的比较断言**（AGENTS
    「不拉踩开源作者」+ 对外话术纪律）；可比的是**取舍位置与可审计性**，且要同时写明
    自己的短板（无优化深度、语言规模墙、语义分析浅、单语言选择模型）。

## 测试基础设施

- **并行度默认值**：`pyproject.toml` 的 `addopts = "-n auto"` **保持现状**（作者
  2026-09-19 定调“先这样”）。本机跑全量时自行显式传 `-n 4` 规避顶满核（做法与分档
  见 `tests/README.md`「改动节奏分档」）；不改仓库默认。

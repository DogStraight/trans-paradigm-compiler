# ADR-0019: 精化基座边界——引擎只做文件操作，精化项列表走语言插件能力

- Status: accepted
- Date: 2026-09-24
- 关联：`docs/decisions/0018-preprocessor-plugin-policy.md`（**同构先例**：引擎只做文本
  操作，处置策略走能力位）、`TODO.md`「精化（elaboration）部件化 + 插件化」、
  `docs/gaps/gap-language-penetration.md`（渗透面实测）、
  `docs/gaps/gap-semantic-elaboration-boundaries.md`（精化能力边界）
- 参照：Verilator `V3Param`（AST/IR 上精化，文本只作输出与诊断呈现）、
  slang `Elaborator`、`references.md` 语言工作台条目

## 背景

精化基座（`analyzer/structure.py`，**1782 行**）里混着两类东西，与 ADR-0018 的
预处理器**同构**：

1. **文件操作 / 通用机制**（语言无关）：读源、宏展开、解析、AST 缓存（`memo`）、
   行映射与宏区间、依赖文件发现的编排。
2. **语言知识**（写在引擎里）——且关键发现是：引擎里住的**不只是逻辑，更是
   Verilog 的类型词汇表**：

   | 位置 | 内容 |
   |---|---|
   | `_ModulePort`（L68-76） | `direction` / `width_expr` / `net_type` —— "端口有方向和宽度"是 Verilog 世界观 |
   | `ModuleParam`（L79-84） | `value_expr`（值被抽成**文本**） |
   | `ModuleInfo` / `PortConnection`（L87-109） | 单元 = 模块、实例化点、端口连接形态 |
   | `_tokenize_const` + `_ConstExprParser` + `_eval_const_expr`（L145-289） | Verilog 常量表达式（四则/比较）求值 |
   | `_SIGNAL_RE` / `_is_signal_expr`（L60-65） | 标识符形态 = 信号 |
   | `_GenFace`（L333-353） | generate 条件求值面 |
   | 语义名词标识符 **183 处** | 端口方向 / 实例连接 / 信号驱动等硬件语义（实测见 gap 档） |

**为什么"把逻辑搬进插件"不足以解决（本次勘察结论）**：`width_check` 插件
（`grammar/verilog/plugins/checks/width_check/_width_check.py`，**1311 行**）逻辑
已经全部在插件侧——但它靠 `port.width_expr` / `ModuleParam.value_expr` 喂饭
（`_module_params()` L144-151 直接读 `info.params`）。**引擎替插件决定了"世界由
哪些事实构成"**（端口有宽度、参数有值文本、信号有驱动/负载）。只要类型词汇表
留在引擎，插件再怎么写都只是在填引擎的表格。

两个点名病灶由此得到精确解释：

- **位宽比较**：逻辑在插件，但"宽度表达式"这个**事实**由引擎抽取并定义
  （`_ModulePort.width_expr`）→ 观感上像在基座里。
- **跨文件参数值变更**：参数值在引擎侧被抽成**文本**、在插件侧被解释成数
  （`eval_expr_params` 链式求值 + 环护栏）；`_override_params`（L482）/
  `_check_inst_internal_widths`（L514）/ `_recheck_module_assigns`（L613）沿
  引擎的 `ModuleInfo.insts` / `PortConnection` 骨架传播 → **值语义被劈成两半**，
  任一侧单独看都不完整。

## 决策

**1. 边界：引擎的最小可视单位 = 文件。**
引擎只保留：读源 / 宏展开 / 解析 / AST 缓存 / 行映射与宏区间 / **依赖文件发现的
编排**（按语言包给出的"想要的单元名"去找文件、读文件）。引擎不认识"端口 / 参数 /
方向 / 宽度 / 驱动 / 负载 / 层次"。单元规则名与名字字段一律**按声明读取**（现状
`[structure]` 的 `module_decl_rule` / `[structure.fields].module_name`），引擎不认
"模块"这个概念——**声明键本身是否改为中性名（`unit_decl_rule` / `unit_name_field`）
归 `[structure]` 声明面处置**（该面本就属 P3 的删/替换对象），落地时定，不在本 ADR
预先断言。

**2. 精化协议 = 语言包能力位返回的、可扩展的项列表。**
语言包 tpc.toml 声明
`[capabilities] elaborator = "_elaborator.py:build_elaborator"`——与 `formatter` /
`macro_policy` 同款能力机制（ADR-0018 决策 3 先例），**不造第二套**；引擎用
`get_capability_in("elaborator", rules_dir)` 按语言包作用域查找（`core/plugin_loader.py:574`），
切语言不串用。

能力入口返回 `ElaboratorSpec`：`items: list[ElaborationItem]` + `solvers: dict[str, Callable]`。

> 命名纪律（承 TODO 原记）：中文"精化"与 refinement（B/Event-B 规格精化）撞词，
> 故**部件名 / 配置名 / 类名一律用 `elaboration`**（`ElaboratorSpec` /
> `ElaborationItem` / 能力名 `elaborator` / 目录 `analyzer/elaboration/`）；
> 中文行文仍可称"精化"。README.md 对外话术用 "elaboration"。

**3. 每个精化项（`ElaborationItem`）的字段**——前 3 项为设计输入给定，其余为本次新增
（⚠ **P2 实测更正 2 处**，见本决策末）：

| 字段 | 必/选 | 含义 |
|---|---|---|
| `name` | 必需 | **项目名**。产物键，语言包作用域内唯一；引擎只当日志标签与容器键，**不解释语义** |
| `locator` | 可选 | **如何从 AST 找到此类值**：声明式定位 `Locator(rule=...)`——引擎在 scope 原子子树内按规则名匹配 |
| `locator_fn` | 可选 | 同上，但定位本身需要算法（函数名，与 `solvers` 同表解析）；与 `locator` 二选一 |
| `solver` | 必需 | **求解的精化逻辑的函数名称**（字符串）。加载期从 `solvers` 解析，缺失 → fail-fast |
| `scope` | 必需 | 执行原子：`file` / `unit` / `project`（**引擎定义枚举**，机制面，可审计；同 ADR-0018 决策 2） |
| `provides` | 必需 | 产出键声明，**运行期核验**（照 transform 插件 `produces` + `_verify_produced` 同款：少填产物键 → fail，不让下游静默空转） |
| `depends_on` | 可选 | 项间依赖；引擎按**拓扑序**执行（后声明项经 `ctx.products` 读先声明项产物） |
| `role` | 可选 | **引擎角色位**（**引擎定义封闭枚举**，契约见下）。条目名由插件定 ⇒ 引擎无法按名寻址**自己也要用**的产物；声明角色位的项，其唯一 `provides` 键即该角色的容器键 |

设计取向：**定位声明式为主、求解为插件代码**——把"变化的结构"做成数据、把"特异
的求解"做成代码（L2 已定的三分法）。`locator_fn` 与省略定位保证表达力不锁死。

> **P2 实测更正（两处，均为落地时才发现）**：
> ① **`locator` / `locator_fn` 都可省略**（省略 ⇒ 求解器收到 `hits = [原子根]`）。
>    原设计要求"恰好声明一个"，但 `param_default` 的值分散在**两种节点形态**
>    （头部 `#(..)` 字段 + 体内 `ParamDeclStmt`），**单条规则名表达不了**；而"怎么找"
>    本身就是语言知识 → 归插件代码正是本协议的目的。原设计会逼出一个字段投影小语言
>    （＝已拒的"配置面膨胀"）。
> ② **新增 `role`**：`GenerateEvaluator`（生成条件求值）在 P3 才迁入协议，过渡期它仍需
>    "单元常量绑定"这张表。容器条目名由插件定 ⇒ 引擎不能写死 `"param_default"`（那是把
>    插件起的名字塞进引擎）。`role` 是引擎能认的封闭枚举，机制上等价于 `scope`。
>    ⚠ **它是过渡面**：gen 族搬迁完成后应删除该角色（`contract.py::ROLES`）。

> **角色位契约**（每个角色**同时**定义寻址键与产物形状——因为引擎要消费它，这与
> 普通条目"形状归插件"不同）：
>
> | 角色 | 寻址键 | 产物形状 | 引擎消费方（**随对应族退场**） |
> |---|---|---|---|
> | `gen_activity` | 文件路径 | `{id(节点): bool}`（节点是否落在**选中**的 generate 分支内） | `SignalGraphBuilder` → 层 3 迁入后 |
> | `unit_ports` | 单元名 | `{端口名: {name, direction, width_expr, net_type, decl_node}}` | `ConnectionElaborator`（层 2）+ `SignalGraphBuilder`（层 3）→ 两者迁入后 |
> | `unit_connections` | 文件路径 | `[{inst_name, module_name, inst_node, file, connects, ordered}]` | `SignalGraphBuilder`（层 3）+ `ProjectChecker` 注入 postpass → 层 2/3 迁入后 |
> | `unit_signal_graph` | `""`（project 单原子） | `{(单元名, 信号名): {drivers: [...], loads: [...]}}` | `ProjectChecker` 注入 postpass（W105）→ 层 3 迁入后 |
>
> `unit_constants`（寻址键 = 单元名，形状 = `{名字: 值文本}`）曾在 P2–P3-① 间服役
> （过渡期 `GenerateEvaluator` 要参数表）；**P3-① 已退场**——gen 求值迁入插件后，单元
> 常量改由插件经 `ctx.products["param_default"]` 自取，引擎不再中转。
>
> ✅ **"收口时 `ROLES` 为空"这个终态判据已核实可达**（P3-② 开工时查过）：引擎的**文件
> 发现**阶段（`ModuleIndexer`）只用**声明**（单元规则名 / 实例规则名 / 名字字段 /
> 扩展名 / 关键字）+ 通用 AST 操作（"取声明种类的节点"），**不需要任何插件产物**；故
> "引擎按语言包给出的单元名去找文件"（决策 1）不引入新角色。
>
> ⚠ **角色位一律是过渡面**：终态（决策 1）下引擎不消费任何插件产物，故 **P3 收口时
> `ROLES` 应为空**——这是"重构完成"的一个可机械检查的判据。角色位的 `scope` **不限**
> （`unit` / `file` 都已有实例），唯一硬约束是"恰好一个 `provides` 键"；原设计曾要求
> role ⇒ `scope == unit`，P3-1 落地时放宽（那是把 `unit` 的实现细节错当成了通用约束）。

**4. 细粒度：每一项 = 一个可导出事实。**
不按现有 4 个类切，按"事实"切。首清单（本次勘察得出，**非穷举**，随落地调整）：

`param_default` / `param_override` / `port_direction` / `port_width` / `port_net_type` /
`port_names` / `inst_sites` / `port_connects` / `unit_of_node` / `gen_condition` /
`gen_activity` / `assign_drivers` / `proc_drivers` / `proc_blocks` / `signal_graph` /
`hier_paths`

每项独立声明定位与求解、独立验证、独立删除引擎侧旧实现。

> **P2 实测更正（`param_override` 的归期）**：原分期把 `param_override` 与
> `param_default` **同批**落地。落地时读码发现：**实例化点参数覆盖的三层合并逻辑
> （`#(.P(v))`）今天已经全在插件侧**（`width_check._override_params`、
> `hier_check._merged_params`，各自直接读 AST）——**它不是引擎侧渗透**。把它上提为
> 协议项是**去重与共享**（多个检查复用同一张合并表），不是"把语言知识搬出引擎"。
> 故归期改为**随 `inst_sites` / `connections` 族在 P3 落地**：它是那两族产物的直接
> 消费者，同批做才不产生中间态。P2 只落 `param_default`——**真正消掉引擎侧
> `ModuleParam` / `ModuleInfo.params` 的那一项**（实测它同时服务 5 个消费方：
> `width_check` / `hier_check` / `latch_check` / `inst_check` + 引擎 `GenerateEvaluator`）。

**5. 产物契约：引擎定容器，插件定条目。**
引擎产出 `context.extra[ELABORATION] = {item_name: {atom_key: product}}`——引擎只保证
**容器与生命周期**（一次运行内建好、失败即 fail-fast）；**条目名与产物形状由语言包
定义**。理由：条目可扩展 ⇒ 引擎无法预知条目名；同语言包的下游消费方（`width_check`
等插件）与产出方同源，可自行对齐。

⚠ 这**改变**了 TODO 原记的"产物模型与 `context.extra` 键名（形状属引擎协议——消费方
是下游 postpass，不能由插件定义）"——那条结论的前提是"条目固定"；条目可扩展后前提
不成立（风险与缓解见权衡）。

**6. 未声明能力 → 降级为单文件 lint + analyze**（不提取、不递归、不注入容器）——
与现存 `[structure]` 未声明行为一致，保留逃生门。

**7. 不留双路径**：每搬一项，**同批删除**引擎侧旧实现（含 `[structure]` 声明面、
`_ModulePort` / `ModuleParam` / `PortConnection` 等 Verilog 形状 dataclass、
`_ConstExprParser` / `_is_signal_expr` / `_GenFace`），不保留兼容垫片
（AGENTS 硬约束 + `policy/doc-alignment.md` 删除判据）。

**范围外（本 ADR 不动，避免混批）**：analyze → transform 的映射通道
（`transform/_semantic_mapping.py` + `core/_protocol.py` 的 `TABLE_*` /
`ATTR_RESOLVED_PORTS`，即 `typed_ports` 那条线）是**另一条数据流**；是否同构迁移
另行立项。`gap-language-penetration.md` 里"`_protocol.py` 契约键名 → 归 L2 重审"
一项因此**仍开放**，未被本 ADR 结掉。

## 权衡

- **声明式 → 命令式的代价**（L2 已记）：加语言不再零代码（c4/yaml 需写一小段插件）；
  换来引擎 schema 与代码**不随语言数增长**。
- **拒绝了"纯 TOML 项列表"**：与 ADR-0018 拒绝"纯 TOML 策略表"**同因**——判定条件
  本身是语言知识，表会演化成小型 DSL；且 TODO 已记"为让引擎普适而设计一套 schema
  会把复杂度从代码搬到配置"（`_number.toml` 7 字段 × 4 形态块是实证）。能力位是既有
  机制，复用优于新造。
- **细粒度的代价**：项数多（首清单 16 项），引擎编排要管依赖序与运行期核验；
  换来每项可独立验证、独立删除、独立被下游消费——这正是"不断拓展的 list"的兑现方式。
- **条目名下沉给插件的风险**：跨语言包的同名条目可能含义不同，而引擎不解释语义、
  **无法拦**。缓解：容器按语言包作用域隔离 + 条目名带语言包前缀的约定；**不做引擎级
  语义校验**（引擎不认识语义，校验必然退化成 schema 膨胀，即上一条已拒的坑）。
- **拒绝的备选**：
  ① **只搬逻辑不搬类型**——实测无效（`width_check` 1311 行已证明：逻辑在插件，
     词汇表仍在引擎）；
  ② **一次全搬**——协议本身未经验证就大规模搬迁，缺陷与搬迁缺陷混在一起无法归因；
  ③ **引擎内置"普适精化"**（如通用符号表/通用常量求值）——新形态必撞 schema
     表达力边界，`_number.toml` 是前车。
- **未决（不预先决定）**：`check()` 公开返回的 `"modules": {name: file}`
  （`analyzer/checker.py:139`）属引擎级 API，而单元名是"插件给出的事实"——此键保留
  还是变形，留到 P2 落地时按实测定。

## 验证

- **P1 先固化行为基线**（回归护栏）：`tools/min_pack_probe.py` + `tools/min_pack_baseline.json`。
  ⚠ 口径 = **串行**（见分期一节）；比对只认**仍绿集合**。
- **每项搬迁的统一口径**：`tests/policy/test_diag_baseline.py` 卡住的真实语料诊断
  基线持平（门禁"只许减"）+ `tests/engine/analyzer` 部件测试全绿 + smoke + 全量测试 +
  真实语料对拍（格式化字节对拍 / lint 准确率）。
- **协议机制测试**（`tests/engine/analyzer/test_elaborator_protocol.py`）：未声明能力 →
  降级；协议**形状** fail-fast（未知键 / 项重名 / 容器键跨项重复 / 角色位重复与非法 /
  `depends_on` 自引用与成环 / `locator` 与 `locator_fn` 同给 / 求解名未解析）；拓扑序；
  强方向核验（求解器返回未声明的键 → fail）。
  ⚠ **刻意不做**"声明了但某原子无产物 → fail"的双向核验（理由见 `contract.py` 模块头：
  按原子出产物时空是常态），这是与 `_verify_produced` 的已知差异，不是遗漏。
- **搬迁项的等价性对拍**（P2 的做法，后续各族照办）：新实现落地后、删旧实现前，先断言
  **产物与旧实现逐项相同**（P2 的 `test_elaboration_param_default.py` 即此法的产物——
  对拍通过后才删引擎侧，golden 值随之为冻结契约）。
- 落档时基线：HEAD `28bf9eb`，`pytest -m smoke` **433 passed**。

## 分期

- **P1 立骨架**（只新增不接线）：`analyzer/elaboration/`（`ElaborationItem` /
  `Locator` / `ElaboratorSpec` / 驱动器 / 加载位 / 产物容器 / 运行期核验）+ 行为基线。
  **已完成**（行为基线 = `tools/min_pack_probe.py`；⚠ 必须**串行**跑，探针故意混跑双语，
  并行结果随 worker 分配漂移——实测同一份代码 1126/1122/1120，在基线提交上复跑也复现
  不出基线）。
- **P2 纵向打穿 `param_default`**（`param_default` 一项 + verilog 插件 + 引擎接线 +
  5 个消费方迁移 + **同批删**引擎侧抽取与 `ModuleParam`/`ModuleInfo.params`/两个死声明键）。
  **已完成**。效果：消掉病灶②（跨文件参数值变更）在引擎边界的一半——引擎不再定义
  "参数有值文本"这个事实。`param_override` 改归 P3（理由见决策 4 的更正节）。
- **P3 搬迁（⚠ 顺序按 P3 开工实测更正）**：原计划按**事实**分族（ports → connections →
  gen → signal graph）。开工时清点引擎内部消费关系（`grep` `in_active_generate` /
  `module_index` / `\.ports` / `inst_sites`）发现**该切法不成立**：

  | 事实 | 引擎内部消费者 |
  |---|---|
  | gen 活性 | **只在 `SignalGraphBuilder` 内**（`in_active_generate` 5 处调用点） |
  | `ports` / `inst_sites` / `connections` | **同一个簇**：`ConnectionElaborator`（层 2）+ `SignalGraphBuilder`（层 3） |
  | `module_index` | 发现（`ModuleIndexer`）+ 层 3 + `checker` 返回值 |

  即：除 gen 外，**每个事实的消费者都是那个本身要一起消失的层 2/3 簇**。按事实切会在
  每一步都撞上"引擎的层 2/3 还在读它"→ 被迫为**注定要消失的消费者**造临时 role
  （role 会堆到 3 个，全是过渡脚手架）。**改为按消费簇切**：

  1. **gen 族 —— 已完成**（P3-①a 移植 + 逐节点对拍，P3-①b 切引擎 + 删）：
     `GenerateEvaluator`（184 行）+ `_GenFace` + 文本常量求值链
     （`_tokenize_const` / `_ConstExprParser` / `_eval_const_expr` / `_param_truth`）
     整体迁入插件项 `gen_activity`（`scope = file`，`role = gen_activity`，
     `depends_on = ["param_default"]`），引擎侧与 `[structure]` gen 声明面**同批删除**。
     **引擎侧的文本求值链自此清零**——但注意：**搬迁未改技法**，它仍是文本模式求值
     （先渲染条件子树再解析文本），只是搬进了插件。故 TODO「文本模式求值/判断（应
     AST-first）」的**渗透维度**结项（引擎里不再有这套 Verilog 求值），而**AST-first
     改写作为独立改进项保留**（动机从"消除渗透"变为"插件代码质量"，需自己一套验证）。
     `ROLE_UNIT_CONSTANTS` **已退场**；`depends_on` 通道至此才真正被用上（P2 是纵向
     打穿，未用依赖）。
  2. **层 2 + 层 3 + ports 一次性搬迁 —— 进行中**：`ConnectionElaborator`（176）+
     `SignalGraphBuilder`（400）+ `_ModulePort` / `ModuleInfo.ports` / `ModuleInfo.insts`
     / `PortConnection`（形状归插件）+ `param_override` 上提。它们的消费者是**彼此**，
     切开只会造桥。落地后**所有临时 role 归零**，引擎只剩文件层（这即决策 1 的终态验收）。
     - **P3-②a 已完成（只新增）**：`port_decls` 项移植 + 与引擎 `ModuleInfo.ports` 的
       **逐端口对拍**（两个夹具：ANSI 头部 / 裸名头部 + 体内旧式声明）。`unit_ports`
       角色位已登记但引擎**尚未切换**——本阶段产物无人消费，存在意义即对拍。
       ⚠ 已记一个键口径差异待 P3-②b 处理：产物按**原子键（单元名）**归位，同名单元在
       多文件重复定义时"最后一个原子赢"，而 `module_index` 是"**首个**定义者优先"。
     - **P3-②b-prep 已完成（只新增）**：`connections` 项（层 2）移植 + 与
       `FileResult.connections` **逐文件对拍**（覆盖命名 / 位置 / 命名但值为空 `.a()`）。
       ✅ 顺带排除一个**时序风险**（结论：不存在）——层 2 在引擎里是**发现过程中逐文件**
       算的，精化 pass 却在**发现之后**统一跑；若它依赖 `module_index`（彼时只填了一部分）
       结果就会不同。实测读码：`elaborate_connections` **完全不读端口表**，只读声明字段并
       渲染连接表达式 → 无时序问题。
     - **层 3 已移植并对拍通过**（P3-②b）：`SignalGraphBuilder` 整体进新文件
       `grammar/verilog/plugins/elaboration/_graph.py`（**逐字搬迁，算法不动**），成为项
       `signal_graph`（`project` 作用域，`depends_on = ["connections", "port_decls",
       "gen_activity"]`——三个**自身产物**，经 `ctx.products` 互读）。对拍 7 个夹具逐条目
       一致（6 个专为信号图设计的 `W105_*`/`W104_*` 样例 + 真实语料），并断言不空转
       （多驱动与 output 穿透真的发生、负载非空）。
       **至此插件侧五项齐备且各自对拍通过**；引擎侧层 2/3 仍在原位（只新增阶段）。
     - **P3-②c 待做**（最后一步，做完即达终态）。⚠ **关键洞察（先删消费方，role 才退场）**：
       role 是"引擎消费插件产物"的寻址机制；**引擎一旦不再消费，role 就该退场**。故顺序
       是"先迁消费方 → 再删引擎实现 → role 自然归零"，而非逐项删引擎代码：
       1. **c-1**：`inst_check` 是 `connections` 的**唯一**消费方（实测：`width_check` 只用
          `inst_sites`，不碰 `connections`）→ 把它与 `signal_graph` 的读取一并改为读
          **产物容器**；此后层 2/3 **无任何消费者** → 删 `ConnectionElaborator` /
          `SignalGraphBuilder` / `_SignalGraphCtx` / `_graph_entry` / `_append_ref` /
          `_is_signal_expr` / `_SIGNAL_RE` / `PortConnection` / `FileResult.connections`，
          `ROLE_UNIT_CONNECTIONS` 与 `ROLE_UNIT_SIGNAL_GRAPH` **同时退场**。
          ⚠ 同批处理 `tests/engine/analyzer/test_checker.py::TestElaborationConnections`
          （直连 `fr.connections` 的层 2 测试——主体随实现消失）。
       2. **c-2**：4 个端口消费方改读 `port_decls` 产物 → 引擎侧再无 `unit_ports` 消费者
          → 删 `_ModulePort` / `ModuleInfo.ports` / `_PortFields` / `ModuleExtractor._fill_ports`
          族 + `[structure]` 端口字段声明 → **`ROLES` 归零**（终态判据达成）。
          **消费方清单（已实测，c-2 直接照此改）**：
          | 插件 | 读什么 |
          |---|---|
          | `width_check` | `info.ports.values()`（**顺序** → 位置连接匹配）、`info.ports.get(pn)`、`port.width_expr`（含 `_module_width_table` 的 `info.ports.items()`） |
          | `inst_check` | `info.ports.get(pn)` / `.keys()` / `.items()`、`port.width_expr`、`port.decl_node`（related 链）、`port.direction`（另有 `output_dirs` / `input_dirs` 来自 extra） |
          | `hier_check` | `port.width_expr`（`_port_width` / `_module_width_table`） |
          | `latch_check` | **不碰 ports**（只读 `param_default` 与本文件 AST） |
          ⚠ 别误改：`sym.decl_node` / `s.decl_node`（`unused_check` / `width_check`）是**符号**
          的声明节点，与端口无关。
       3. **c-3**：`param_override` 上提（ADR 决策 4 的更正经 P3 落地；与 `inst_sites` /
          `connections` 族同批）。
       ✅ 已备 c-1 的前置：引擎注入**当前分析文件**（`core/_protocol.py::CTX_ANALYZED_FILE`，
       语言无关的文件层事实）——`connections` 是**文件作用域**产物而 postpass 逐文件跑，插件
       需要它才能取对切片（否则只能反查 AST 猜自己在分析哪个文件）。
       ✅ 顺带删掉一个**死字段**：`ModuleInfo.insts`（模块内实例化点）**只有写入、从无读取**
       ——连同唯一写入点（`FilePipeline.parse_file` 的"挂回"循环）一起删（已完成）。
- **P4 文档收口**：`core/component_protocol.md` 加"精化器能力位"节 + 插件 README +
  `MODEL_INDEX` / `analyzer/README` 同步。

> Impl: `analyzer/elaboration/`（契约 / 驱动器 / 原子供源 / 服务句柄 / 加载位）、
> `grammar/verilog/plugins/elaboration/`（verilog 精化项与求解器）
> Test: `tests/engine/analyzer/test_elaborator_protocol.py`（机制面）、
> `tests/engine/analyzer/test_elaboration_param_default.py`（P2 搬迁项 + 角色位 + 降级）

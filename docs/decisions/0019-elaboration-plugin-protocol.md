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

**3. 每个精化项（`ElaborationItem`）的字段**——前 3 项为设计输入给定，其余为本次新增：

| 字段 | 必/选 | 含义 |
|---|---|---|
| `name` | 必需 | **项目名**。产物键，语言包作用域内唯一；引擎只当日志标签与容器键，**不解释语义** |
| `locator` | 必需 | **如何从 AST 找到此类值**：声明式定位 `Locator(rule=..., fields={...})`——引擎在 scope 原子子树内按规则名匹配、按字段名取值 |
| `solver` | 必需 | **求解的精化逻辑的函数名称**（字符串）。加载期从 `solvers` 解析，缺失 → fail-fast |
| `scope` | 必需 | 执行原子：`file` / `unit` / `project`（**引擎定义枚举**，机制面，可审计；同 ADR-0018 决策 2） |
| `provides` | 必需 | 产出键声明，**运行期核验**（照 transform 插件 `produces` + `_verify_produced` 同款：少填产物键 → fail，不让下游静默空转） |
| `depends_on` | 可选 | 项间依赖；引擎按**拓扑序**执行（如 `param_override` 依赖 `param_default`） |
| `locator_fn` | 可选 | **逃生门**：定位本身需要算法（非"规则名 + 字段名"可表达）时改用函数名，同 `solver` 解析。声明式够用时不用 |

设计取向：**定位声明式为主、求解为插件代码**——把"变化的结构"做成数据、把"特异
的求解"做成代码（L2 已定的三分法）。`locator_fn` 保证表达力不锁死。

**4. 细粒度：每一项 = 一个可导出事实。**
不按现有 4 个类切，按"事实"切。首清单（本次勘察得出，**非穷举**，随落地调整）：

`param_default` / `param_override` / `port_direction` / `port_width` / `port_net_type` /
`port_names` / `inst_sites` / `port_connects` / `unit_of_node` / `gen_condition` /
`gen_activity` / `assign_drivers` / `proc_drivers` / `proc_blocks` / `signal_graph` /
`hier_paths`

每项独立声明定位与求解、独立验证、独立删除引擎侧旧实现。

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

- **P1 先固化行为基线**（回归护栏；gap 档判据 1「最小语言包探针」同为"待做"项，
  同批补）——没有基线则"改了有没有用"无法判。
- **每项搬迁的统一口径**：`tests/policy/test_diag_baseline.py` 卡住的真实语料诊断
  基线持平（门禁"只许减"）+ `tests/engine/analyzer` 部件测试全绿 + 全量测试 +
  真实语料对拍（格式化字节对拍 / lint 准确率）。
- **新增 `tests/engine/analyzer/test_elaborator_protocol.py`**：未声明能力 → 降级为
  单文件；`solver` 名未解析 / `scope` 取值非法 / `provides` 未产出 → **fail-fast**；
  `depends_on` 拓扑序生效；**语言作用域**（c4 拿不到 verilog 的项）；容器形状。
- 当前基线（本 ADR 落档时实测）：HEAD `28bf9eb`，`pytest -m smoke` **433 passed**。

## 分期

- **P1 立骨架（只新增不接线）**：`analyzer/elaboration/`（`ElaborationItem` /
  `Locator` / `ElaboratorSpec` / 驱动器 / 加载位 / 产物容器 / 运行期核验）+ 行为基线。
- **P2 纵向打穿两项**：`param_default` + `param_override`（后者依赖前者），
  `width_check` 改读新容器，并**同批删**引擎侧对应实现——直接消掉病灶②（跨文件
  参数值变更），且以最小面积验证协议本身（定位 / 求解 / 跨文件 / 下游消费 / 核验
  五段全通）。
- **P3 逐族搬迁**（每项：落地 → 验证 → 删旧实现，不留双路径）：ports 族 →
  connections 族 → gen 族 → signal graph 族。
- **P4 文档收口**：`core/component_protocol.md` 加"精化器能力位"节 + 插件 README +
  `MODEL_INDEX` / `analyzer/README` 同步。

> Impl: `analyzer/elaboration/`（契约/驱动器/加载位）、
> `grammar/verilog/plugins/elaboration/`（verilog 精化项与求解器）
> Test: `tests/engine/analyzer/test_elaborator_protocol.py`

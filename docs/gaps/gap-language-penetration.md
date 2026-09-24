# Gap — 语言知识渗透（引擎里实现了语言语义）

- 状态：未闭环（词法/结构面首轮已清；**判据 1 行为面基线已立**，语义面仍待按判据逐条排查）
- 关联：`TODO.md`「L1 语言知识渗透复审」「L2 精化基座重设计」；`docs/gaps/gap-semantic-elaboration-boundaries.md`（精化能力边界）
- 参照：`references.md` 语言工作台条目（Spoofax / Xtext / MPS / rascal）

## 边界是什么

硬约束是"**语言知识不进代码**"（`AGENTS.md`）。现有两条门禁只覆盖**词法面**：

- `policy/check_hardcode.py` R1–R5：语言**关键字字面量** / `grammar/` 路径 / Doc 头 /
  引擎 import `grammar.<lang>` / 测试 `chdir`；
- `tools/config_sites.py check`：引擎读的**配置键**是否都在语言包声明。

两条都答不了"引擎里有没有实现**语言的语义**"。原因：用配置键（`fields["module_name"]`）
或通用算法（`_eval_const_expr` 只认数字/四则/比较，却以"能求值 generate 条件"为前提）
表达的 Verilog 语义里**一个 Verilog 词都没有**；配置点位法反而**奖励**这类渗透。
实证：`_eval_gen_cond` 的 `eval` 求值由外部审计发现，而"它其实是 Verilog 形态进了引擎"
是靠**人读代码**发现的。

### 判据（三条，强弱递减；都只覆盖**被测路径**）

| # | 判据 | 性质 | 状态 |
|---|---|---|---|
| 1 | **最小语言包探针**：只加载最小骨架包跑全量测试，仍绿的引擎测试 = 普适面 | 行为面（强） | **已做**（`tools/min_pack_probe.py`，2026-09-24；基线 `tools/min_pack_baseline.json`） |
| 2 | **声明面缺失探针**：临时删一段语言包声明跑测试，仍绿处 = 引擎替声明做事 | 行为面（强） | 待做 |
| 3 | **弱信号面**：`tools/lang_penetration.py`——① 引擎字符串里出现语言包规则/节点名（硬信号）② 语言对象词作标识符（弱信号） | 词法面（仅线索） | 已跑（2026-09-20） |

⚠ 判据 3 **不能当判据**：普适协议也可能叫这些名。实测误报两类——linter 的 `width`
是 LSP 诊断列宽、`reset_atom_memo` 的 `reset` 是动词。必须逐条看调用链才能定性。

⚠⚠ **第二条教训（2026-09-20 当场踩到）：弱信号命中还须先判"可达性"**。
首轮把 `parser_core._parse_bit_width_literal`（引擎实现的 Verilog `[size]'[base]digits`）
当成活渗透 → 先做成能力外置（新增 `number_literal` 能力 + 语言包组件）；随后用
**调用计数探针**（monkeypatch `pratt_parser.parse_number_literal` 计数）实测：
**三个语言包下调用次数全为 0**——lexer 按 `[[number.based]]` 把 `8'hFF` 捕成
**单 token**，语言包的 `Number` 规则（`value = "$1"`）先手接住，pratt 的
字面量前缀路径根本不执行。即那条引擎实现是**不可达的冗余第二路径**（同一个概念
有两条扩展机制），不是渗透。
处置：**撤掉外置物、删掉冗余钩子**（`install_*` + 槽位 + 登记表条目），
保留通用整数/浮点解析；带宽度基数的语言事实留在**语法规则面**（lexer 声明 + 规则），
那里本来就有它。
**可复用判据**：弱信号 → ② 看调用链定性 → ③ **数调用次数（可达性）** →
④ 才分"渗透 / 死代码 / 契约"。只做到 ② 会把死路径当渗透，多花一道外置工序。

### 行为面基线（判据 1 首轮，2026-09-24）

机制 = `tools/min_pack_probe.py`：用 `$TPC_CONFIG`（官方支持的覆盖点，
`core/_user_config.py` 优先级 1）把**默认语言包**指向迷你包，**子进程**跑引擎测试。
必须进程级隔离——各模块 `from core.define import DEFAULT_RULES_DIR` 在 import 期
已复制值，同进程 monkeypatch 无效。

⚠⚠ **必须串行跑（工具已默认补 `-n 0`）——这条是实测踩出来的，不是性能选择**：
探针**故意让一个进程里混跑两种语言**（默认包 = 探针包，而大量引擎测试显式加载
verilog），而本仓已记载"多语言同进程有真实串味史"（`tests/README.md`）→ xdist 的
worker 分配一变，结果就变。实测（`tests/engine`，**同一份代码**）并行三次 =
**1126 / 1122 / 1120** 仍绿；**在基线提交 `141cf25` 上复跑也复现不出基线**
（1120 + 6 项假回归）。改串行后同一子集两次逐项相同（351）。故**基线以串行建立与
比对**；并行结果只能当"大致规模"，**不可作回归判据**。

探针包 = `grammar/yaml`（仓库既有"迷你语言包"：无插件、4 个 token 文件，且**固定**
——基线与该包绑定，换包须重记）。⚠ 它仍是一门真语言（声明了缩进与标量形态），故结论
只在"相对该包"的意义上成立，这是本判据的已知折扣。

首轮实测（串行，`tests/engine`）：基线见 `tools/min_pack_baseline.json`（含逐项仍绿
清单与计数）。

⚠ 只有**仍绿集合**可作判据；`变红/报错` 的边界会漂（同一用例随分配落"失败"或"报错"，
总数不变），计数仅供人看。

判读方式：改动前后各跑一次（都串行），**仍绿集合缩小 = 回归**（曾有测试走引擎通用面，
现在开始依赖语言包声明）。这是 P2–P3 逐族搬迁的回归护栏。

## 首轮实测（2026-09-20，词法/结构面，作者指定重点：analyzer / preprocessor / linter）

| 子系统 | ① 结构名字面量 | ② 语言对象词（定性） | 结论 |
|---|---|---|---|
| **analyzer** | **5**（全在 `structure.py`） | 183（`structure.py` 独占，真渗透） | **重灾区**（与作者判断一致） |
| parser | 11（全是 pratt/节点协议名） | 10（位宽字面量族 → **不可达**，见下） | **无活渗透** |
| linter | 0 | 21（**全部误报**：文本宽度 / 动词 reset） | 词法面已清 |
| preprocessor | 0 | 0 | 词法面已清（形态外置后） |
| core / pipeline / renderer / transform / lexer | 0 | 45（**全部误报或契约**，见下表） | 已清（一处已修） |

**非精化基座面的逐条定性（2026-09-20）**

| 位置 | 命中 | 定性 |
|---|---|---|
| `pipeline/__init__.py:184-189` | `split_port_close_lines` / `split_inst_tail_lines` | **曾是真渗透**（引擎按名调用语言的排版步骤）→ **已修**：能力面改声明 `pre_scan_passes`（前置文本遍列表，引擎不知道每遍的语义） |
| `renderer/doc.py` 18 处 | `width` / `max_width` / `_row_width` | 排版列宽（Prettier 式 Doc 模型）→ 误报 |
| `lexer/main_lexer.py` 7 处 | `width` | `[indent]` 缩进宽度 → 误报 |
| `core/define.py` / `global_state.py` | `_default_instance`、`reset` | Python 单例实例 / 动词 → 误报 |
| `pipeline/schedule.py` | `instance` | `instance = cls(**params)` 对象实例 → 误报 |
| `core/_protocol.py`、`transform/_semantic_mapping.py` | `ATTR_RESOLVED_PORTS` / `TABLE_TYPE_PORTS_FLAT` / `_uses_resolved_ports` | **契约面**（elaboration 产物键名按既定决策留引擎，消费方是下游 postpass）→ 归 L2 重审 |

**语言名与协议名的同名陷阱**：`Root` / `Comment` / `UnaryOp` / `BinaryOp` / `TernaryOp` /
`Number` / `Identifier` / `MacroCall` 是**引擎表达式树协议**（pratt 建节点 + 语言包按此名
声明 renderer），属"引擎定义的最小协议"；同一份名单里的 `BitWidthLiteral` 曾按"渗透"
记账，实测是**不可达的死规则**（不是渗透，删除判据 B 类），2026-09-20 已删。
判"是协议还是渗透"的问法：**这个名字是引擎要求的契约，还是引擎对某种语言
语法形态的假设**？

### 已确认的渗透点

**analyzer（重灾区）**
- `analyzer/structure.py:1038-1040`：`"FuncDecl"` / `"FuncDeclOld"` / `"TaskDecl"` 集合
  ——按**规则名**认"函数/任务体"。
- ~~`analyzer/structure.py:1115,1118`：`"ParamDeclStmt"` / `"Declarator"` ——按规则名取
  参数与声明符。~~ **P2 已迁出**（ADR-0019）：随 `param_default` 精化项进入
  `grammar/verilog/plugins/elaboration/`，引擎侧 `_fill_params` 族与
  `ModuleParam`/`ModuleInfo.params` **同批删除**——本项清零。
- `analyzer/structure.py` 语义名词标识符 **183 处**（`_register_port` / `_inst_name_of` /
  `_is_signal_expr` / `_SIGNAL_RE` / `_backfill_port` …）：端口方向、实例连接、信号驱动
  等**硬件语义在引擎里实现**（L2 的"抽取能力 + 动态求解该在插件侧"）。
  ⚠ P2 后复测仍 **183**（未动：P2 搬的是参数，属"求解"面；端口/实例/信号仍在原位，
  P3 逐族处理）。
- `analyzer/checker.py:74,130,208,212`：`_signal_graph` / `inst_sites` ——全工程信号
  驱动/负载图（ADR-0008 elaboration 层 3）。
  ⚠ P2 后复测：`checker.py` 仍 4 处（P3 目标，未动）。

**P2 后渗透面复测（2026-09-24，`tools/lang_penetration.py`）**：① 硬信号
`analyzer/structure.py` **5 → 3**（`ParamDeclStmt`/`Declarator` 两项清零）；② Tier A
语言对象词 analyzer **187 = `structure.py` 183 + `checker.py` 4**——**新增的
`analyzer/elaboration/` 命中 0**（探针自己认它语言中性）。故本批**未引入新渗透面**。

**parser（无活渗透；一处冗余路径已删）**
- 11 处 ① 命中全是**引擎表达式树/节点协议名**（`Root` / `Comment` / `UnaryOp` / `BinaryOp` /
  `TernaryOp` / `Number` / `Identifier` / `MacroCall`）：语言包按这些名声明 renderer，
  属契约。
- 已删：`pratt_parser` 的"数字字面量扩展钩子"（框位 + `install_*` + 引擎实现）——
  实测三语言包下**不可达**（见上"可达性"教训），带宽度基数的语言事实由 lexer 声明 +
  语法规则承担。
- **已删（2026-09-20 结案）**：语言包的 `BitWidthLiteral` 规则（production =
  `[literal.number, symbol.base.single_quote, @Identifier]`）在当前 `[[number.based]]`
  声明下**不可达**（实测 `8'hFF` / `8 'hFF` / `8'h FF` / `'hFF` / `8'shFF` / `4'b10_10`
  六种形态均不产生该节点；`8 'hFF` 甚至直接解析失败）→ 连带
  `[[BitWidthLiteral.renderer.layout]]`、`attributes`/`udp`/`PrimaryExpr` 里的候选、
  `inst_check`（合成节点文本拼回分支）与 `width_check`（宽度分派表项）同属死面。
  **作者确认它是死规则（完整数字字面量在 lexer 阶段就拿到了）**，全部已删。
- **删除受阻的真因（本次实测，非"规则定义本身被需要"）**：删定义后两条测试变红
  （`tests/languages/verilog/test_macro_body_comment.py`、
  `tests/e2e/test_real_corpus.py::test_svparser_interop[ref_darkriscv.v]`）。逐项
  bisect（规则定义 / 候选列表两维）得到"只要规则定义还在就绿"，
  但**机制不是"规则被用到"**：
  - 关键取证：`_attach_line_end` 的 `(text, line)` **全局去重**。HEAD 下同一行尾注释
    先被 `BitWidthLiteral` 的**失败尝试**（`current_node` 残留该节点）吃掉并挂到
    随后被丢弃的节点上 → 注释只留在锚点通道；删规则后注释**第一次**就挂到真节点
    `Number` 上（V2 实测 `current_node=Number`）。
  - 后果：`LineSuffix` 当时"按层就地落地"（内层原子节点 doc 无尾换行点）→ 语句
    `;` 被印在注释之后 → **分号消失**（输出非法）→ 宏原文回填的自描述比较
    （`_renders_as_itself`，注释剥离后比对）不再成立 → 回填静默跳过。
  - **同一坑在 HEAD 上已可达**（与删规则无关）：`assign a = v[0] // note` + 换行 + `;`
    → `assign a = v[0] // note;`（分号被吃）；`(v[0])` 形态同样。
  - 已修：`LineSuffix` 跨嵌套层级上提 + `line_ending` 判类（行终止型推迟、块注释
    就地），见 `renderer/renderer_architecture.md`「行尾锚定的推迟范围与两类注释」。
    修完删规则直接通过：全量 **2114 passed / 7 skipped**、diag 5548 持平、
    lint 33/33 误报 0、格式化字节对拍 73 文件 0 diff。
- **教训（保留）**：规则的"可达性"与"影响力"不等价——不可达的 is_atom 规则仍可能
  通过 `current_node` 残留 / 注释去重这类**间接通道**改变行为；删任何规则前都要跑
  行为面（本次还额外证明：注释挂载对"原子规则集合与顺序"存在隐式依赖，属已修的
  潜在脆弱点）。

**linter / preprocessor**：本轮**未发现**词法/结构面渗透。linter 由 grammar 切片驱动
（语句/块边界从规则推导），preprocessor 已全形态外置（`[macro_recognition]` +
`[directive_handlers]`，含 include 的拼写与路径形态）。⚠ 这只说明"没按名认结构、没写死
语言词"；**语义面**（如 linter 的错误恢复近似、预处理器求值）要靠判据 1/2 才算查过。

## 成熟解法参照（见贤思齐，未闭环项适用）

语言工作台（`references.md`：Spoofax / Xtext / MPS / rascal）都强制"语法定义 → AST 类型"
与"语言语义实现"分离，引擎只提供通用骨架。本仓的差距不在机制（插件/能力位/槽位都有，
`typed_ports` 就是正面样板），而在**默认实现的语言特定化**：引擎里留下的不是"最普适形态"，
而是完整的 Verilog 实现。

## 可实现性（未闭环项适用）

按 L2 三分法处置（值不同 → 配置；结构一致 → 引擎骨架；形态各异 → 插件代码），
一步一验：

1. **行为面基线**：**已做**（2026-09-24）——`tools/min_pack_probe.py` +
   `tools/min_pack_baseline.json`（`tests/engine` 仍绿 1126 例；机制与判读见上节）。
2. **parser 位宽字面量**：槽位保留，Verilog 实现移入语言包（能力位/声明式 hook），
   引擎默认退化为"纯数字"。验证 = smoke + 真实语料字节对拍 + `tests/engine/parser`。
3. **analyzer 结构名（5 处）**：规则名进语言包声明（`[structure]` 已有同类字段先例）。
   验证 = analyzer 部件测试 + 诊断基线 5548 持平。
4. **analyzer 语义面（183 处那一坨）**：属 L2 基座重设计（抽取/求解移插件），
   先立 ADR 再动。验证 = 诊断基线 + 真实语料对拍 + `typed_ports` 先例对照。

## 关联条目

- `TODO.md`「L1 语言知识渗透复审」/「L2 精化基座重设计」
- `docs/gaps/gap-semantic-elaboration-boundaries.md`（精化/单例/inject 边界）
- 门禁：`policy/check_hardcode.py`（词法面）、`tools/config_sites.py check`（配置面）
- 探针：`tools/lang_penetration.py`（弱信号面，按需跑）

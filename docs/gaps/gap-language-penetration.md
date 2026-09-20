# Gap — 语言知识渗透（引擎里实现了语言语义）

- 状态：未闭环（词法/结构面首轮已清，**语义面待行为探针**）
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
| 1 | **最小语言包探针**：只加载最小骨架包跑全量测试，仍绿的引擎测试 = 普适面 | 行为面（强） | 待做 |
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
声明 renderer），属"引擎定义的最小协议"；同一份名单里只有 `BitWidthLiteral` 是渗透
（见下）。判"是协议还是渗透"的问法：**这个名字是引擎要求的契约，还是引擎对某种语言
语法形态的假设**？

### 已确认的渗透点

**analyzer（重灾区）**
- `analyzer/structure.py:1038-1040`：`"FuncDecl"` / `"FuncDeclOld"` / `"TaskDecl"` 集合
  ——按**规则名**认"函数/任务体"。
- `analyzer/structure.py:1115,1118`：`"ParamDeclStmt"` / `"Declarator"` ——按规则名取
  参数与声明符。
- `analyzer/structure.py` 语义名词标识符 **183 处**（`_register_port` / `_inst_name_of` /
  `_is_signal_expr` / `_SIGNAL_RE` / `_backfill_port` …）：端口方向、实例连接、信号驱动
  等**硬件语义在引擎里实现**（L2 的"抽取能力 + 动态求解该在插件侧"）。
- `analyzer/checker.py:74,130,208,212`：`_signal_graph` / `inst_sites` ——全工程信号
  驱动/负载图（ADR-0008 elaboration 层 3）。

**parser（无活渗透；一处冗余路径已删）**
- 11 处 ① 命中全是**引擎表达式树/节点协议名**（`Root` / `Comment` / `UnaryOp` / `BinaryOp` /
  `TernaryOp` / `Number` / `Identifier` / `MacroCall`）：语言包按这些名声明 renderer，
  属契约。
- 已删：`pratt_parser` 的"数字字面量扩展钩子"（框位 + `install_*` + 引擎实现）——
  实测三语言包下**不可达**（见上"可达性"教训），带宽度基数的语言事实由 lexer 声明 +
  语法规则承担。
- **待定（需要作者拍板）**：语言包的 `BitWidthLiteral` 规则（production =
  `[literal.number, symbol.base.single_quote, @Identifier]`）在当前 `[[number.based]]`
  声明下**也不可达**（实测 `8'hFF` / `8 'hFF` / `8'h FF` / `'hFF` / `8'shFF` / `4'b10_10`
  六种形态均不产生该节点）→ 连带 `[[BitWidthLiteral.renderer.layout]]` 与
  `inst_check` / `width_check` 里按该节点名分支的代码同属死面。删它要动多处 production
  候选列表与文档，属"删除先证后删"里证据较齐但影响面较大的一项。

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

1. **行为面基线（先做）**：最小语言包探针脚本 + 记录"哪些引擎测试在最小包下仍绿"。
   没有这条基线，"改了有没有用"无法判。
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

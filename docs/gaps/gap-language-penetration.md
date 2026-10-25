# Gap — 语言知识渗透（引擎里实现了语言语义）

- 状态：未闭环（词法/结构面已清；语义面已随精化基座重构迁出，**残余两项**在 `TODO.md`）
- 关联：`TODO.md`（插件侧 AST-first 改写 / 引擎侧未声明的取值形态假设）；
  `core/component_protocol.md`（精化器能力位与设计原则）
- 参照：`docs/references.md` 语言工作台条目（Spoofax / Xtext / MPS / rascal）

## 边界是什么

硬约束是"**语言知识不进代码**"（`AGENTS.md`）。现有两条门禁只覆盖**词法面**：

- `policy/check_hardcode.py` R1–R5：语言**关键字字面量** / `grammar/` 路径 / Doc 头 /
  引擎 import `grammar.<lang>` / 测试 `chdir`；
- `tools/config_sites.py check`：引擎读的**配置键**是否都在语言包声明。

两条都答不了"引擎里有没有实现**语言的语义**"：用配置键（`fields["module_name"]`）或
通用算法（`_eval_const_cond` 式求值）表达的 Verilog 语义里**一个 Verilog 词都没有**；
配置点位法反而**奖励**这类渗透。实证：`_eval_gen_cond` 的求值曾由外部审计发现，而
"它其实是 Verilog 形态进了引擎"是靠**人读代码**发现的——该实现现已迁入语言包
（`grammar/verilog/plugins/elaboration/_elaborator.py::solve_gen_activity`）。

## 判据（三条）

> 强弱递减；三条都只覆盖**被测路径**，故结论只能是"已知渗透面收敛"。

| # | 判据 | 性质 | 状态 |
|---|---|---|---|
| 1 | **最小语言包探针**：只加载最小骨架包跑全量测试，仍绿的引擎测试 = 普适面 | 行为面（强） | **已做**（`tools/min_pack_probe.py`；基线 `tools/baselines/min_pack_baseline.json`） |
| 2 | **声明面缺失探针**：临时删一段语言包声明跑测试，仍绿处 = 引擎替声明做事 | 行为面（强） | 待做 |
| 3 | **弱信号面**：`tools/lang_penetration.py`——① 引擎字符串里出现语言包规则/节点名（硬信号）② 语言对象词作标识符（弱信号） | 词法面（仅线索） | 已跑（按需复跑） |

### 弱信号的四道判据（可达性教训）

⚠ 判据 3 **不能当判据**（普适协议也可能叫这些名）。命中必须走完四道：
① 词法命中 → ② 看调用链定性 → ③ **数调用次数（可达性）** → ④ 才分"渗透 / 死代码 / 契约"。
反面教材：`_parse_bit_width_literal` 曾被当活渗透外置成能力位，调用计数探针实测三语言包下
调用次数**全为 0**（lexer 已按 `[[number.based]]` 把 `8'hFF` 捕成单 token）——那是**不可达的
冗余第二路径**，处置 = 撤外置物 + 删冗余钩子。只做到 ② 会把死路径当渗透，白花一道工序。

### 行为面基线（判据 1）

机制 = `tools/min_pack_probe.py`：用 `$TPC_CONFIG`（官方支持的覆盖点，`core/_user_config.py`
优先级 1）把**默认语言包**指向迷你包，**子进程**跑引擎测试——必须进程级隔离（各模块
`from core.define import DEFAULT_RULES_DIR` 在 import 期已复制值，同进程 monkeypatch 无效）。

⚠ **必须串行跑（工具已默认补 `-n 0`）——这是实测踩出来的，不是性能选择**：探针故意让一个
进程里混跑两种语言（默认包 = 探针包，而大量引擎测试显式加载 verilog），而本仓已记载
"多语言同进程有真实串味史"⇒ xdist worker 分配一变结果就变；**并行结果只能当"大致规模"，
不可作回归判据**。探针包 = `grammar/yaml`（仓库既有迷你语言包，**固定**——基线与该包绑定，
换包须重记）；它仍是一门真语言，故结论只在"相对该包"的意义上成立，这是本判据的已知折扣。

基线（`tools/baselines/min_pack_baseline.json`）：**`passed = 1186`**。复现：
`python -c "import json;print(json.load(open('tools/baselines/min_pack_baseline.json',encoding='utf-8'))['passed'])"`。
⚠ 只有**仍绿集合**可作判据；`变红/报错` 的边界会漂（同一用例随分配落"失败"或"报错"，
总数不变），计数仅供人看。判读方式：改动前后各跑一次（都串行），**仍绿集合缩小 = 回归**
（曾有测试走引擎通用面，现在开始依赖语言包声明）——这是逐族搬迁的回归护栏。

## 当前实测快照

`python tools/lang_penetration.py`（本档最近一次复跑）：

- ① **结构名字面量（硬信号）11 处，全在 parser**，且全是**引擎表达式树/节点协议名**：
  `parser/_constants.py:35,36`（`Root`/`Comment`）、`parser_core.py:231`（`MacroCall`）、
  `pratt_parser.py:149,155,158,407,457,525,605,642`（`Number`/`Identifier`/`UnaryOp`/
  `BinaryOp`/`TernaryOp`）。语言包按这些名声明 renderer，属契约。**analyzer 0 处**。
- ② **Tier A 语言对象词命中 68 处**：linter 21 / renderer 18 / core 11 / lexer 7 /
  **analyzer 6** / transform 3 / pipeline 2。analyzer 的 6 处**全是产物契约键名**
  （`analyzer/structure.py` 的 `inst_sites`/`inst_module_name`、`analyzer/checker.py:226`
  `inst_sites`）——语言语义实现已随精化基座重构移入语言包
  （`grammar/verilog/plugins/elaboration/_graph.py::_is_signal_expr`、
  `_elaborator.py::_register_port`/`_inst_name_of`）。
- **同名陷阱**：`Root`/`Comment`/`UnaryOp`/`BinaryOp`/`TernaryOp`/`Number`/`Identifier`/
  `MacroCall` 是**引擎表达式树协议**（pratt 建节点 + 语言包按此名声明 renderer），不属渗透。
  判"是协议还是渗透"的问法：**这个名字是引擎要求的契约，还是引擎对某种语言语法形态的假设**？
- 其余命中（`width`/`reset`/`instance`/`_uses_resolved_ports` 等）在历史复盘中已逐条定性为
  误报或契约键名；结论只能是"**已知渗透面收敛**"——三条判据都只覆盖**被测路径**。

## 关联条目

- `TODO.md` 残余两项：**插件侧 AST-first 改写**（`_graph.py` 正则判"简单信号名"、
  `render_subtree` 渲染后字符串比较）、**引擎侧未声明的取值形态假设**（`[structure.fields]`
  只声明字段名，引擎仍假设取值在 `Node.content`）
- `core/component_protocol.md` §1b（精化器能力位）+ `analyzer/elaboration/README.md`（引擎侧职责）
- 门禁/探针：`policy/check_hardcode.py`、`tools/config_sites.py check`、
  `tools/lang_penetration.py`、`tools/min_pack_probe.py`（基线 `tools/baselines/min_pack_baseline.json`）

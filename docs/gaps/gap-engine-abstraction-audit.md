# Gap — 引擎能力面抽象审查（主线 1 刻度完成后执行）

- 状态：**T3 完成（#59–#66，六部件全审）**；触发 = 刻度 7→9 完成 + 作者 2026-10-23 拍板三任务路线图
- 关联：`ROADMAP.md`「刻度完成后的全项审查」；`policy/collaboration.md`（证据/循环纪律）
- 参照：—
## 缺口是什么

C 包的价值之一是**抽象压力测试**：每出现一次"这台语言要单独处理"，就暴露一个未审查的抽象；
**多一门语言就多一次不同的处理**，说明分叉处没有抽象。当前缺的不是功能，而是**"哪些是引擎
能力面、哪些是语言包方言"的全局视图**，以及把方言收回引擎的可证伪判据。

本档是审查台账：**方法 + 矩阵 + 每行证据**。日常循环碰到新的语言特化处理就在此补一行
（调查轮性质，不单独汇报）；刻度完成后按矩阵一次性出结论与立项清单。
## 审查方法（唯一判据：能力 × 语言矩阵 + 第二语言复用实验）

矩阵每格四态（按"为表达它，引擎改了什么"分类）：
| 态 | 含义 | 结论 |
|---|---|---|
| **原样** | 只用既有声明/机制表达 | 抽象成立 |
| **新声明键** | 只加同族配置键（面变宽、语义不变） | 抽象成立 |
| **新引擎代码** | 为一门语言改了引擎 | **leak 候选** |
| **逃生门** | 软路径 / 特判 / 双语分支 | **必须消灭或降级** |

矩阵另记一类**方言复制**：同一能力在语言包内复制了 N 份声明（如拼写别名），未改引擎但知识
重复、容易漂移——审查目标是「收敛为一条声明（引擎加声明面）或显式接受」。
**第二语言复用实验**（leak 候选的证伪形式，不做实验不算数）：

1. 取候选能力，在**第二门语言**上用配置表达一次（临时包即可，不提交）；
2. 只改配置即成立 ⇒ 抽象成立，候选撤销；
3. 引擎必须再改一次 ⇒ 记 leak，写内置化方向与判据（落 `TODO.md` 或 `ROADMAP.md` 立项）；
4. 复现命令/临时包位置写回本行——**没有复现的记录按观察计**。
## 执行路线（T3，作者 2026-10-23 拍板）

C 与 Verilog 两个主语言包**按部件逐轮**对照审查；每轮一个部件、独立判据/独立提交。
两包对照的作用 = 同一抽象在两门语言里若处理不同，差异处即 leak 候选（或用第二语言
复用实验证伪）。
| 序 | 部件 | 重点对照面 | 已有探针/证据 |
|---|---|---|---|
| 1 | lexer / preprocessor | 词法声明面、宏/条件/include 处理、注释边界 | 判据①最小包、`gap-preprocessor-*`、`gap-language-penetration` 矩阵 |
| 2 | parser | 规则字段/消歧/raw/符号面（#49 新面）、错误路径 | 判据②删声明段、A/B、`gap-parser-linter-approximation` |
| 3 | linter | L1/L2/发现面、宏检查、raw 资格（T2 后重审） | 判据②、lint accuracy、`linter/linter_architecture.md` |
| 4 | analyzer / elaboration | scope/symbol/精化基座、语言语义插件边界 | `gap-c-semantic-base`、精化能力位、`component_protocol.md` |
| 5 | transform / renderer | 归一化、注释/宏 splice、渲染布局声明面 | 渲染保真/幂等门禁、`gap-formatter-line-behavior` |
| 6 | pipeline / config / plugin 契约 | `[engine] uses`、声明键→消费点、空转检测、双路径 | `tools/config_sites.py`、`tools/feature_sites.py`、`structural_score.py` |

每部件**输出**（一轮内可交付）：
1. 矩阵行审查：四态归类（原样/新声明键/新引擎代码/逃生门）+ 方言复制项；
2. leak 清单：每项 = 证据命令 + C/Verilog 对照 + 第二语言复用实验结论（成立 ⇒ 撤销；
   需再改引擎 ⇒ 记 leak + 内置化方向/判据，落 TODO 或本档）；
3. 判据②（声明面缺失探针）：临时删一段语言包声明跑受影响测试，仍绿处 = 引擎替声明做事；
4. 收口：修复进实现轮 / 接受登记本档「不做」表；`structural_score --compare` 与
   `feature_sites compare` 不新增未登记散点。
**止损**：每部件最多 1 调查 + 1 实现轮；第二语言复用实验需要临时语言包（不提交，
位置写回本档行）；不能证伪的候选按"观察，未对照"记，不进实现清单。
## 当前矩阵（按证据状态；调查轮顺带维护）
| # | 能力面 | 语言现状 | 四态 | 证据 / 复现 | 内置化方向 | 状态 |
|---|---|---|---|---|---|---|
| 1 | **档位门控**（`enabled`） | `enabled` 曾只门控**声明面**；插件规则文件无条件加载 ⇒ "档位 = 接受域"对不依赖新关键字的增量不成立。**已收口**：可选件（包内 `enabled` 清单里的组件）的 `[grammar] files` 随档位加载，常驻件与 Python 组件恒加载（ADR-0023） | **新引擎代码 → 已内置化** | 合法 C23 `_Static_assert(1);` 与 `enum e : int` 曾被此卡住（ADR-0023 后解锁）；反向证据 = 数字分隔符（#38）**能**收敛到声明层，说明"绕不开"发生在词法面之外；判据 = `tests/engine/core/test_tier_gated_grammar.py` + `tests/languages/c/test_c_standard_tiers.py` | 已按"可选件 vs 常驻件"成立（今后新增档位/可选语法增量按同一判据） | 已过（循环 #40；ADR-0023） |
| 2 | **同构造异拼写** | C11/C23 6 组双拼写各写一条同形规则，节点名分叉（`AlignasConstSpec`/`AlignasC23Spec` …） | **方言复制**（未改引擎） | `grammar/c/plugins/c23/16_alignas_alias.toml` 头注（token 类型由拼写决定 ⇒ 现无别名面）；`grep -l "alias" grammar/c/plugins/c23/*.toml` | 引擎"拼写别名"声明面（token 别名表 + 单规则多拼写策略），或显式接受 | 待审查 |
| 3 | **精化基座**（pre_scan / raw 承载与理解 / sites） | **已收口（T2 #53–#57）**：机制整体删除，C 只留 parser 符号表 + analyze 符号产物；Verilog 走 `peek` + typed_ports，yaml/c4 不用** | 待复用实验 | 机制：`linter/lookahead.py`（`pre_scan` 提示面）、`grammar/c/plugins/semantics/_raw_*.py`、`tools/feature_sites.py`；语言音用法差异见各包 README | 若第二语言复用成立 ⇒ 抽象成立；若必须改引擎 ⇒ 内置化为引擎能力面（raw/understand 的通用钩子） | 待取证（复用实验未做） |
| 4 | **文件链接 / 入口点** | C 的 `#include` 全链路（`path_forms`、内容进流、行映射、渲染剪枝）；Verilog 的 `module_index` 项目符号可见性；CLI 单文件 vs `ProjectChecker.check(paths)` 多入口 | **新引擎代码**（缺统一 unit graph） | `preprocessor/primitives/include.py`、`pipeline/__init__.py`（include 剪枝）、`analyzer` 的 `module_index`、`ROADMAP.md`「用户侧 CLI 形态」；两门语言各一套索引 | 引擎级 **unit graph / 入口协议**（根文件集 + 解析器声明 + 单位索引 + 链接策略），两门语言的索引收敛为配置 | 待审查（阶段 5 真实 C 语料接入会先逼一遍） |
| 5 | **容器成员位增量**（轮 #35） | `StructBody = { (@StructMember\|@StructMemberExtra)* }` + 空槽位注入 | **原样**（零引擎改动） | `tests/languages/c/test_c_standard_conformance.py::TestStaticAssertMemberPosition`；门禁变异 101 | —（抽象成立） | 已过 |
| 7 | **字面量前缀 / 数字形态声明面**（轮 #37/#38） | C 用 `[string] prefixes` + `[[number.based]]`（`suffix` / `base_prefix` / `digit_separator`）按名合并表达 L/u/U/u8、`0b…`、`1'000`；其余语言包不声明即无影响 | **原样**（引擎声明面） | `tests/languages/c/test_c_lexer.py::TestLiteralPrefixes/TestLiteralPrefixTiers/TestDigitSeparator{,Tiers}`；`tests/engine/lexer/test_number_digit_separator.py`；门禁变异 103/104/105/106 | —（抽象成立） | 已过 |
| 13 | **pipeline/config/plugin 契约（T3-⑥）** | C uses 7 项 / 默认管线；Verilog uses 14 项 + 4 pipeline units；`[engine] uses` 由能力门禁校验；config_sites 全在引擎词汇表 | **原样 + L1 漂移**（C 遗留 transform.slots） | `lang_penetration --dirs pipeline core`；判据② 1/20 红证；config_sites PASS | L1 删 C 遗留 uses（#66 已做） | 已审（L1 ✅ / L2 接受） |
| 12 | **transform/renderer（T3-⑤）** | C 无 transform 段、渲染 117 layout；Verilog typed_ports transform + 111 layout；renderer 全声明式 | **原样 + L1 硬编码**（transform `resolved_ports` 特判） | 判据② 22/8/rc2 红证；`_uses_resolved_ports` 变异 8 failed；render_coverage 100% | L1：mapping entry 声明 `resolved_attr`（#65 已做） | 已审（L1 ✅） |
| 11 | **analyzer/elaboration（T3-④）** | C：`c_symbol_collect`+`c_symbols` postpass+check 插件；Verilog：typed_ports symbol/scope/postpass + elaboration 插件；引擎 analyzer/elaboration 无语言分支 | **原样**（L1 `inst_sites` 命名为协议面，接受） | `lang_penetration --dirs analyzer`（0 结构名）；判据② 7/1/4 红证 | —（无行为 leak） | 已审 ✅ |
| 10 | **linter 声明面（T3-③）** | C：`[macro_syntax]` + 插件 check 规则；Verilog：`[linter] macro_hygiene`/`style_check`；宏检查/样式消费点均为引擎通用、无语言分支 | **原样** | `lang_penetration --dirs linter`（0 结构名）；判据② 5/6/6 红证；lint accuracy 33/fp0；A/B 0/144 | —（无 leak） | 已审 ✅ |
| 9 | **parser 声明面（T3-②）** | C 的 `register`/`requires_symbol`/`symbol_namespaces` 与 Verilog 的规则字段（`is_atom`/块边界）全走同一引擎字段；协议节点名（Root/Comment/MacroCall/pratt 产物）为引擎契约 | **原样（+协议面接受）** | `tools/lang_penetration.py --dirs parser`；判据② 见上「T3 部件②审查记录」；A/B 0/144 | —（无 leak） | 已审 ✅ |
| 8 | **词法/预处理声明面（T3-①）** | C/Verilog 注释/数字/宏/字符串形态全在包内声明；判据②删声明均红；弱信号 0 结构名；c4 复用同一面 | **原样 + 1 方言复制（Verilog 注释双声明）** | `tools/lang_penetration.py --dirs lexer preprocessor`；删声明探针见上「T3 部件①审查记录」 | 删 Verilog `token.toml` 重复 `[comment]`（#60 已做） | 已审（L1/L2 ✅） |
| 6 | **注释归属**（行中/行尾/前置/容器项间） | 引擎统一槽位模型，各语言布局只消费槽位 | **原样** | `renderer/renderer_architecture.md`（注释处理节）；`tests/engine/renderer/test_comment_slots.py` + C/verilog 渲染门禁 | —（抽象成立） | 已过（本轮 #32/#33 的修复未引入语言分支） |
## T3 部件①–⑤审查记录（#59–#65，细节见 CHANGELOG 与上方矩阵行）
- ① lexer/preprocessor：弱信号结构名 0；判据② C 注释/数字/宏 2/4/7 红、V 宏 50 红；
  L1 Verilog 注释双声明 → #60 修。抽象成立。
- ② parser：弱信号 11 处为引擎协议节点名（Root/Comment/MacroCall/pratt 产物），接受；
  判据② symbol_namespaces/register/requires_symbol 6/16/6 红；无 leak。
- ③ linter：弱信号 0；判据② V macro_hygiene/style_check 5/6 红、C macro_syntax 6 红；
  诊断 33/fp0；无 leak。
- ④ analyzer/elaboration：结构名 0；Tier A `inst_sites` 命名称谓接受；判据② 7/1/4 红；
  无行为 leak。
- ⑤ transform/renderer：结构名 0；判据② 22/8/rc2 红；L1 `resolved_ports` 硬编码 → #65 修。

## T3 部件⑥审查记录（pipeline / config / plugin 契约，#66）
- 弱信号：`lang_penetration --dirs pipeline core` → 结构名 2 处 `"L"`（诊断 `L{line}:C{col}`
  格式化，误报）；Tier A `core/_protocol.py` 的 `ATTR_RESOLVED_PORTS`/`TABLE_TYPE_PORTS_FLAT`
  = 协议 magic-string 常量（**L2 接受**：ADR-0015 单一来源；表名本身由语言包声明），
  其余 reset/instance 为动词误报。
- 声明面：C `[engine].uses` 7 项；Verilog 14 项（+elaborator/formatter/macro_policy/
  pipeline.units/structure/linter/transform）；`[[pipeline.units]]` 仅 Verilog（C 用默认管线）
  = 语言策略，非方言。
- **L1 修复**：C `uses` 曾声明 `transform.slots.v1`（P4 遗留），T2c 后 C 无任何 transform
  声明 ⇒ 已删除（`grep grammar/c transform` = 0；policy + C 套件 1238 passed 绿）。
- 判据②：删 C `analyzer.primitives.v1` → `test_engine_capabilities` **1 failed**（声明门禁）；
  删 Verilog pipeline unit `slots` → pipeline/e2e **20 failed**（声明承重）。
- 工具：`config_sites check` PASS；`feature_sites`/`structural_score` Δ0；A/B **0/144**。
- leak 清单：L1 已修；L2 常量命名接受；无行为 leak。

## T3 收口（#59–#66）
| 部件 | 结论 | 处置 |
|---|---|---|
| ① lexer/preprocessor | 抽象成立 | Verilog 注释双声明 → #60 修 |
| ② parser | 协议节点名接受 | 无 leak |
| ③ linter | 用户诊断同构 | 无 leak |
| ④ analyzer/elaboration | `inst_sites` 命名接受 | 无行为 leak |
| ⑤ transform/renderer | `resolved_ports` 硬编码 | L1 → #65 修 |
| ⑥ pipeline/config | `uses` 漂移 + 常量命名 | L1 → #66 修；L2 接受 |
- 验证：全量 4377/14、A/B 0/144、render 124/124、`c_acceptance` 49/0、S Δ0、feature 0、
  `config_sites check` PASS。
- 未修/接受（触发条件 = 第二门语言使用 structure/typed_ports 面时复议）：④
  `inst_sites`/`inst_module_name` 命名；⑥ `core/_protocol` 端口常量名。

## 可实现性（leak 候选的内置化骨架；审查轮细化）

- **入口/链接（#4）**：包声明 → 根文件集 + `include`/`import` 解析器 + 单位种类；引擎维护
  unit graph（包含边 + 单位定义边），分析器/linter/报告统一消费；判据 = 同一
  `ProjectChecker.check(paths)` 服务两门语言 + 多文件真实语料跑通（阶段 5 判据 5 复用）。
- **精化基座（#3）**：已由 T2 收口——结论 = 该机制**不属可复用抽象**（C 特有死重），已删；
  语言知识落点改为 parser 符号门（#49）与 analyze 符号产物（C 包 `semantics`）。
- **档位（#1，已落地）**：按 ADR-0023 只门控**可选件**（包内 `enabled` 清单里的组件名）的
  `[grammar] files`；常驻件与 Python 组件恒加载——C 的两条标准缺口随之解锁。**第二门带版本档
  的语言包**（如 SV 的 `--std`）仍未接入 ⇒ 多档语言的复用实验待 SV backlog 出现时补做；
  当前判据 = 两包（C / verilog）现状与该判据吻合（verilog 9 个 grammar 组件全在清单里）。
- **拼写别名（#2）**：先统计包内复制量（规则数/节点名数），再评估"别名表"声明面是否值得；
  移植成本 > 收益则显式接受（登记在 `gap-language-pack-scope`「接受域现状」）。
## 关联条目

- `ROADMAP.md`「刻度完成后的全项审查」；`PROGRESS.md`（刻度 7→9 = 触发条件）
- `docs/gaps/gap-language-pack-scope.md`（档位/拼写别名现状）；`docs/gaps/gap-language-penetration.md`
  （语言知识渗透复审，与本审查同族但关注"引擎里写了语言语义"）
- 复现工具：`tools/c_acceptance.py`、`tools/feature_sites.py`、`tests/e2e/eval_*`（证据口径）

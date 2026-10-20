# Gap — 引擎能力面抽象审查（主线 1 刻度完成后执行）

- 状态：未立项（触发 = `PROGRESS.md` 刻度 7→9 完成；先审查、后 P3/性能类改动）
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

## 当前矩阵（按证据状态；调查轮顺带维护）

| # | 能力面 | 语言现状 | 四态 | 证据 / 复现 | 内置化方向 | 状态 |
|---|---|---|---|---|---|---|
| 1 | **档位门控**（`enabled`） | `enabled` 曾只门控**声明面**；插件规则文件无条件加载 ⇒ "档位 = 接受域"对不依赖新关键字的增量不成立。**已收口**：可选件（包内 `enabled` 清单里的组件）的 `[grammar] files` 随档位加载，常驻件与 Python 组件恒加载（ADR-0023） | **新引擎代码 → 已内置化** | 合法 C23 `_Static_assert(1);` 与 `enum e : int` 曾被此卡住（ADR-0023 后解锁）；反向证据 = 数字分隔符（#38）**能**收敛到声明层，说明"绕不开"发生在词法面之外；判据 = `tests/engine/core/test_tier_gated_grammar.py` + `tests/languages/c/test_c_standard_tiers.py` | 已按"可选件 vs 常驻件"成立（今后新增档位/可选语法增量按同一判据） | 已过（循环 #40；ADR-0023） |
| 2 | **同构造异拼写** | C11/C23 6 组双拼写各写一条同形规则，节点名分叉（`AlignasConstSpec`/`AlignasC23Spec` …） | **方言复制**（未改引擎） | `grammar/c/plugins/c23/16_alignas_alias.toml` 头注（token 类型由拼写决定 ⇒ 现无别名面）；`grep -l "alias" grammar/c/plugins/c23/*.toml` | 引擎"拼写别名"声明面（token 别名表 + 单规则多拼写策略），或显式接受 | 待审查 |
| 3 | **精化基座**（`pre_scan` / raw 承载与理解 / sites） | 引擎有通用机制与声明键；**C 用全链路，Verilog 走 `peek` + typed_ports，yaml/c4 不用** | 待复用实验 | 机制：`linter/lookahead.py`（`pre_scan` 提示面）、`grammar/c/plugins/semantics/_raw_*.py`、`tools/feature_sites.py`；语言音用法差异见各包 README | 若第二语言复用成立 ⇒ 抽象成立；若必须改引擎 ⇒ 内置化为引擎能力面（raw/understand 的通用钩子） | 待取证（复用实验未做） |
| 4 | **文件链接 / 入口点** | C 的 `#include` 全链路（`path_forms`、内容进流、行映射、渲染剪枝）；Verilog 的 `module_index` 项目符号可见性；CLI 单文件 vs `ProjectChecker.check(paths)` 多入口 | **新引擎代码**（缺统一 unit graph） | `preprocessor/primitives/include.py`、`pipeline/__init__.py`（include 剪枝）、`analyzer` 的 `module_index`、`ROADMAP.md`「用户侧 CLI 形态」；两门语言各一套索引 | 引擎级 **unit graph / 入口协议**（根文件集 + 解析器声明 + 单位索引 + 链接策略），两门语言的索引收敛为配置 | 待审查（阶段 5 真实 C 语料接入会先逼一遍） |
| 5 | **容器成员位增量**（轮 #35） | `StructBody = { (@StructMember\|@StructMemberExtra)* }` + 空槽位注入 | **原样**（零引擎改动） | `tests/languages/c/test_c_standard_conformance.py::TestStaticAssertMemberPosition`；门禁变异 101 | —（抽象成立） | 已过 |
| 7 | **字面量前缀 / 数字形态声明面**（轮 #37/#38） | C 用 `[string] prefixes` + `[[number.based]]`（`suffix` / `base_prefix` / `digit_separator`）按名合并表达 L/u/U/u8、`0b…`、`1'000`；其余语言包不声明即无影响 | **原样**（引擎声明面） | `tests/languages/c/test_c_lexer.py::TestLiteralPrefixes/TestLiteralPrefixTiers/TestDigitSeparator{,Tiers}`；`tests/engine/lexer/test_number_digit_separator.py`；门禁变异 103/104/105/106 | —（抽象成立） | 已过 |
| 6 | **注释归属**（行中/行尾/前置/容器项间） | 引擎统一槽位模型，各语言布局只消费槽位 | **原样** | `renderer/renderer_architecture.md`（注释处理节）；`tests/engine/renderer/test_comment_slots.py` + C/verilog 渲染门禁 | —（抽象成立） | 已过（本轮 #32/#33 的修复未引入语言分支） |

## 可实现性（leak 候选的内置化骨架；审查轮细化）

- **入口/链接（#4）**：包声明 → 根文件集 + `include`/`import` 解析器 + 单位种类；引擎维护
  unit graph（包含边 + 单位定义边），分析器/linter/报告统一消费；判据 = 同一
  `ProjectChecker.check(paths)` 服务两门语言 + 多文件真实语料跑通（阶段 5 判据 5 复用）。
- **精化基座（#3）**：把 C 的 `pre_scan`+raw 组合在第二门语言复现一次；只加声明即成立 ⇒ 抽象
  成立；需改引擎 ⇒ 把 raw/understand/sites 提升为引擎能力面（钩子 + 声明键），语言包只声明形态。
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

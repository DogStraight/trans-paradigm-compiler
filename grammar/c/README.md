# grammar/c — C 语言包（核心基线 ≈ C99 语法面 + 标准增量插件族）

> 主体语言包之一。形态定调见 `ROADMAP.md`「C 语言包」：**核心基线 + 标准增量插件**，
> c11 / c17 / c23 各为一个插件目录，`requires` 链表达标准包含关系——
> 「启用某个组合 = 等效某个标准的语法面」，**零引擎新机制**。
> C 包接受域现状（`python tools/c_acceptance.py`：42 条 / 接受 40 / 空洞 2）与渲染保真
> 现状见 `docs/gaps/gap-language-pack-scope.md`「C 语言包：接受域现状」/「C 包渲染/保真面
> 现状」节；外部参照见 `docs/references.md`「C 语言文法参照」。

## 现状（0.1.3 交付面）

**接受面：`python tools/c_acceptance.py` → 接受 40 / 空洞 2（共 42 条）**：
`#include` / `#define`（预处理属阶段 4，单独立项）。
（空洞数 2026-09-26 从 3 降到 2：变参 `...` 落地；接受数同日 32 → 34：`_Alignas` /
`_Atomic` 两条增量用例，再 34 → 35：c23 小写拼写，再 35 → 36：c23 类型词，
再 36 → 38：c23 属性说明符的两条位点用例——见下「标准增量插件」。）

已落地：

- **词法**：C99 全 37 关键字；标点 / 多字符运算符；`/* */` 与 `//` 注释；
  整型（十 / 八 / 十六进制 + `U`/`L`/`LL` 后缀）、浮点（指数 / 后缀 /
  **前导点** `.5`）、字符与字符串字面量（**段内转义** `"say \"hi\""`）。
- **声明与类型**：翻译单元；说明符序列（存储类 / 类型限定符 / 函数说明符
  `inline`）；声明符递归（多级指针 / 数组 / 函数后缀 / 括号声明符 / 参数表）；
  `struct`/`union`（带标签与匿名）/`enum`；typedef 名作类型；
  位域；初始化器（含**指示符** `.field=` / `[i]=`）；**变参尾段 `...`**。
- **语句**：compound / 表达式 / 空 / `if`(含 `else`) / `switch`(含 `case`/`default`) /
  `while` / `do` / `for`(含 C99 声明式初值) / `goto` / 标号 / `break` / `continue` /
  `return`；`Stmt` 选替 15 分支。
- **表达式**：全部优先级与结合性（40 项运算符表）、赋值族、条件 `?:`、
  **逗号运算符**（`CommaExpr` + `FullExpr` 选择器）、一元 / 后缀、
  **链式后缀**（`a.b.c` / `f(x)[i]` / `p->a[i]` / `(*fp)(x)`）、`sizeof` 两形态、
  **强制转换** `(T)x` 与**复合字面量** `(T){…}`（关键字起头的类型名）。
- **标准增量插件**：`c11` / `c17` / `c23` 三档齐备（见下「标准档位」）。语法增量逐项：
  · **c11**（6 个新关键字**全部有规则**）：`_Static_assert`（**文件 / 块 / struct·union
    成员表三处作用域**；成员位走容器级空槽位 `@StructMemberExtra`）、
    `_Alignof`、`_Generic`、`_Noreturn`、`_Thread_local`、`_Alignas`（常量表达式与
    类型名两形态）、`_Atomic`（限定符形态 + `_Atomic(T)` 说明符形态）；
  · **c17**：无新语法（缺陷修正版，只表达包含关系）；
  · **c23**：`static_assert`（小写关键字化，**文件 / 块 / struct·union 成员表三处作用域**；
    C23 §6.7.10 起 **消息可省** ⇒ 按标准两条产生式落成 Verilog `FuncDecl` 同款的
    **inline 分派器 + 两分支**：两参 `StaticAssertC23MsgDecl` / 单参
    `StaticAssertC23NoMsgDecl`）、`nullptr`、
    `true`/`false`、`bool`、`typeof`/`typeof_unqual`、`constexpr`，**c11 三个关键字的
    C23 拼写** `alignas` / `alignof` / `thread_local`（同构造异拼写，见下条约定），
    以及**类型词** `_BitInt(N)`（宽度收 `@Expression`，"是不是整型常量表达式/宽度范围"
    归语义层）与 `_Decimal32`/`_Decimal64`/`_Decimal128`（含**十进制浮点字面量后缀**
    `1.5df`/`1.5dd`/`1.5dl`），以及**属性说明符 `[[…]]`**
    （C23 §6.7.12；N3096 §6.7.12.1 / N3220 §6.7.13.2：**位点三类全部落地**——
    说明符位、`[[fallthrough]];` 这类"属性声明"，以及 **①声明符内**
    （`void f [[deprecated]] (void);`，§6.7.6 的 identifier 之后、后缀链之前）与
    **②枚举项**（`A [[deprecated]] = 1`，§6.7.2.2 的 `=` 之前）；带前缀名
    `[[gnu::unused]]` 也认。**实参形态**（2026-09-28 收口两条）：实参收
    `@ArgumentList` ⇒ **多实参** `[[gnu::nonnull(1, 2)]]` / `[[gnu::format(printf, 1, 2)]]`
    / `[[clang::no_sanitize("a", "b")]]` 可用；**属性表尾随逗号** `[[nodiscard,]]` 可用
    （`AttributeList` 独立可选元素 + 单独绑定）。**未覆盖 ①②④⑤** 见「未做」表与
    `plugins/c23/21_attributes.toml` 头注）。
  ⚠ **"加规则"之外还有一类：合并既有配置**（2026-09-26 为十进制字面量后缀补的引擎能力）。
  它**不是**语法增量：`df`/`dd`/`dl` 作用在**核心基线的数字形态**上
  （`base/_number.toml` 的 `[[number.based]] name = "c_dec"`）。改核心文件会让**基线档**
  也接受 `1.5dd`（污染档位语义）；插件整条重抄 `c_dec` 则知识重复、必然漂移。故给声明加了
  **合并语义** `merge = "by-name"`（同名声明之间按 `name` 合并命名条目列表——
  `core/config_registry.py::merge_by_name`）：`plugins/c23/_number_c23.toml` 只写
  `name = "c_dec"` + `suffix`，其余字段由核心供给。**缺省仍是"后者覆盖"**（对既有配置
  零影响）；明细见 `core/config_lifecycle.md` §4b。判据：基线档 `1.5dd` 仍切两个 token、
  c23 档合成一个且核心其余后缀形态不受影响
  （`test_c23_increment_plugin.py::TestC23InjectionPoints::test_decimal_literal_suffix_*`）。
  ⚠ **落地方式全是"声明的注入"**（`[ExtRule.inject] targets = […]`，引擎侧
  `inject_productions` 的直接注入 = 树层 `insert_choice_candidate`）：插件往核心基线的
  **既有交替里加一支**，核心文件一行不动。此前插件注释把这类增量记为"做不了、
  需引擎补『改』路径"——**那是错的**（机制早就有了，缺的是声明），见
  `plugins/c23/tpc.toml` 的历史更正段。
  ⚠ **"往序列中段插元素"只有一条路：空槽位**（2026-09-28 为属性位点补的引擎能力）。
  注入只能并入**某一条既有元素**或越界追加到**末尾**，插不了中段——把中段做成一条
  **原子规则槽位**（核心侧 `production = []`，宿主写 `@Slot*`），注入就退化成"给规则
  加形态"。样板 = `01_declarations.toml` 的 `AttributeSlot`（**声明符内与枚举项共用
  同一个槽位**，一处声明两处生效）；语义见 `grammar/grammar_rule_fields.md` §production
  与 `docs/language_walkthrough.md`「规则注入」。
  ⚠ **同构造异拼写（如 `_Alignas` vs `alignas`）的包内约定（2026-09-26 定）**：
  **c23 侧各写一条同形规则**（先例 = `static_assert`），不做跨插件 token 引用、也不用
  `inject_replace_rule` 去改别的插件的规则。理由：词法层 **token 类型由拼写决定**
  （`keyword_type(拼写)`，`[id.keyword]` 的键名只是可读名）⇒"一个 token 类型两种拼写"
  表达不了；改别人规则的 production 只有软路径。**代价**：同一构造两种拼写 =
  **两个节点名**（`AlignasConstSpec` / `AlignasC23Spec`）——按构造匹配的分析器需同时认。
  判据：`test_c23_increment_plugin.py::TestC23InjectionPoints::test_c23_spellings_reuse_the_c11_hosts`
  （宿主必须与 c11 版一致，否则两拼写的可达位点会漂移）。

**linter**：三份样本（`ring_buffer.h` / `ring_buffer.c` / `edge_comments.c`）上**零诊断**
（2026-09-26 实测；此前合法代码误报 14 / 7 / 2 条，成因与修点在
`linter/checkers/matcher.py` 的 `_no_progress_ok` / `_match_seq` 与
`linter/discovery.py` 的 `_container_end` / `_advance_match` 文档里，逐条回归守见
`test_c_corpus.py`、`test_c_corpus_impl.py`、`test_c_declarations.py`，门禁有效性由
`tools/check_gate_efficacy.py` 的 4 条变异抽查）。**已知边界**：块内诊断粒度粗——
`CompoundStmt` 不是块规则，块内多个错误只报一条（见 `TODO.md` 同项）。

未做（各自有归属，不在本包偷偷绕过）：

| 项 | 归属 |
|---|---|
| 预处理（`#include` / `#define` / `#if` / `#` / `##` / 变参宏） | 阶段 4，单独立项（引擎前置见 ROADMAP「注入机制：四类注入面，按需实现」——③ 具体路径修改与 ④ 移除语法路径仍缺结构化面） |
| typedef 名起头的强制转换（`(myint)x`） | 语义层切片 1b（需符号表 / 作用域 / 声明顺序），草案见 ROADMAP |
| 逐声明符位宽（`int a : 3, b : 4;`） | 已知边界：包内宽度绑在整个成员声明后；标准里位宽属声明符（形态改动） |
| `[[属性]]`（c23）的**实参形态** | **已收口两条（2026-09-28）**：✅ **多实参** `[[gnu::nonnull(1, 2)]]`（实参由 `@Expression` 改收 `@ArgumentList`——`Expression` 是 assignment-expression 层级、不含逗号）+ ✅ **属性表尾随逗号** `[[nodiscard,]]`（`AttributeList` 加独立可选元素 `(comma)?` + **单独绑定**，**不得塞进 `items`**：join 分隔符会叠加成 `, ,`）。**仍未覆盖 ①②④⑤**，"现状 / 为什么不做 / 触发条件"逐条登记在 `plugins/c23/21_attributes.toml` 头注与 `TODO.md`：① 空实参 `[[deprecated()]]`（**低优先**：实测可配置面实现，代价 +1 规则 +1 AST 节点层；触发 = 真实语料）；② 相邻字面量拼接 `[[deprecated("a" "b")]]`（**不做**：硬拼只能覆盖 `literal.string+` 一种形态、+2 规则；旧记的"备选写全序列会被 `parser/follow.py` 的 choice 盲区卡掉"已随该盲区修复作废）；④ 空属性表 `[[]]`（**不做**：`@Attribute?` 一行即可，但**与③合体后 `[[,]]` 会被接受**）；⑤ 配平 token 序列 `[[f(int)]]` / `[[f(1 2)]]`（**暂不做**：现役 production 微语法是闭集，需新增元素类型，改动面横跨 parser/linter/preprocessor 10+ 处分派表；触发 = 真实语料出现非表达式 token 序列）。**位点已全部落地**（2026-09-28：说明符位 / 属性声明 / 声明符内 / 枚举项——后两处走**共用空槽位** `@AttributeSlot`）；另有**一处过接受**（`(f) [[deprecated]]` 也认，标准只允许紧跟 identifier 之后）如实登记在 `plugins/c23/21_attributes.toml` 头注。判据 `test_c23_increment_plugin.py`：`test_attribute_known_boundaries`（①②④⑤ 仍须被拒）+ `test_attribute_over_acceptance_boundaries`（③ 的 `[[nodiscard,,]]` / `[[,]]` 仍须被拒）+ `test_attribute_list_binds_trailing_comma_separately` / `test_attribute_args_bind_through_argument_list` |
| 十进制浮点**字面量后缀**（`1.5df`/`1.5dd`/`1.5dl`） | ✅ **已落地**（2026-09-26）：走声明级合并 `merge = "by-name"`（`plugins/c23/_number_c23.toml` 只补 `c_dec` 的 `suffix`），**不是**改核心 `base/_number.toml`（那会让基线档也接受 `1.5dd`） |
| **C11/C23 语法面缺口 6 条样本**（`_Static_assert(` 单参 / `u8` 字符与字符串字面量 / 二进制常量 / 数字分隔符 / `enum` 固定底层类型） | 阶段 5「标准等效断言面」实测（oracle = gcc 16.1.0 `-std=… -pedantic-errors`）：**合法标准代码当前被拒**。逐条判据、标准归属、成因与修法在 `docs/gaps/gap-language-pack-scope.md`「C 标准等效缺口」；用 `tests/languages/c/test_c_standard_conformance.py` 的 `xfail(strict=True)` 钉住（修好一条就红一条，提醒转正）。成员表位已在循环 #35 转正（容器级空槽位）；剩 `_Static_assert(` 单参前置 = 规则文件不按 `enabled` 门控（规则会漏进 c11/c17 档） |
| VLA | 与语义/求值强耦合，先记缺口（见缺口档接受域清单逐条标注） |
| 完整类型系统 / 求值 / 实现定义行为 / K&R 老式定义 | **明确不做**（超出一致性检查工具链的定位） |

⚠ **typedef 歧义的实际边界（2026-09-26 实测，判代价用）**：C 的 typedef 名与普通
标识符同处一个命名空间，本包按既定分层**语法层宽进**——`Stmt` 候选里 `@ExprStmt` 在
`@Declaration` 之前，故**标识符打头**的语句先按表达式解：`myint *b;`（`myint` 是
typedef 名）进 AST 是 `ExprStmt` + `BinaryOp`（乘法），与真实编译器的读法**相反**。
实测代价只有两样、且都不含语义损伤：① 排版按乘法给空格（`myint * b;`）而非指针惯例；
② 基于 AST 的后续分析看到与编译器不同的形态。**渲染不改语义**——10 条歧义形态
（`*b` / `**b` / `*b = 0` / `*b, *c` / `(b)` / `(b) * c` / `*b[4]` / `(*fp)(int)` /
`a * b` / `a *b = c`）渲染前后 **token 序列逐项相同**（C 空白无关 ⇒ 序列相同即语义
相同），该性质由 `test_c_render_fidelity.py` 的"显著 token 序列"判据守着。
消歧归 ROADMAP「C 语义层切片 1b」（含作者指示的 raw 路径方案）。

## 文件结构

```
grammar/c/
├── tpc.toml                 # 包入口：[engine] uses 能力清单 / lexer / parser / renderer style / [plugins] enabled
├── token.toml               # C99 全 37 关键字
├── base/
│   ├── _token.toml          # 标点、多字符运算符、bracket 配对、字面量形态、[string] escape
│   ├── _lexer.toml          # token 类别 + 注释语法（/* */ 与 //）
│   ├── _number.toml         # 数字形态（进制 / suffix 尾段 / lead_dot 前导点）
│   ├── _operator.toml       # 运算符优先级 / 结合性 / 一元位置（C99 §6.5；刻意不含逗号）
│   └── _style.toml          # 渲染风格：缩进 4、页宽 80（C 惯例）
├── 00_expressions.toml      # 原子 / 表达式入口 / 运算符分层 / 后缀链 / 转换 / 复合字面量 / sizeof / 逗号
├── 01_declarations.toml     # 翻译单元、声明、说明符序列、声明符递归、FuncSpec、Identifier
│                            #   （含**空槽位** AttributeSlot——声明符内 / 枚举项共用）
├── 02_types.toml            # struct/union/enum、成员声明与位域、typedef 名作类型
├── 03_statements.toml       # 语句族与控制流（整表达式位点引 @FullExpr）
├── 04_comments.toml         # Comment 规则（渲染保真需要它是真节点）
└── plugins/
    ├── c11/                 # _Static_assert（含块作用域注入）+ _Alignof / _Generic /
    │                        #   _Noreturn / _Thread_local + C11 新关键字词法扩展
    ├── c17/                 # 无语法文件，只声明 requires = ["c11"]（缺陷修正版）
    └── c23/                 # static_assert / nullptr / true·false / bool / typeof /
                             #   constexpr + C23 新关键字词法扩展（requires c17）
```

## 标准档位：启用组合 = 等效某个标准

- **默认**（`tpc.toml` 的 `[plugins] enabled`）= 核心基线 ≈ C99 语法面。
  `enabled = ["c11", "c17", "c23"]` 即 c23 全档；只列 `["c11"]` 即 C11 档。
- **包含关系在加载期可执行**：组件级 `requires`（c23→c17→c11→核心基线）——
  只启用 c17 而不启用 c11 会**响亮失败**，不会静默少加载。
- ⚠ **未声明关键字 ≠ 拒绝**：某档下未声明为关键字的词仍是合法标识符
  （词法完整、语法按已落地子集引用）——这是判据，不是缺口。
- **档位可进程内切换**：引擎级 `enabled=` 覆盖参数已落地——
  `ConfigRegistry.load_language/load_all/resolve(..., enabled=[...])`（`None` = 用包内
  `[plugins] enabled`；显式档位会被登记为该包"当前档位"，`Lexer` 之类隐式消费方自动跟随）。
  于是**同一个 pack、同一次进程内** `enabled=["c11"]` → `enabled=[]` 会真的换档。
  判据：`tests/languages/c/test_c_standard_tiers.py` 的 **构造 × 4 档矩阵**（构造数按
`pytest tests/languages/c/test_c_standard_tiers.py --collect-only -q` 实测；每构造在同
  一进程内切 4 档断言"解析成哪个节点"，能直接抓出缓存串档；该文件共 43 例）。两条静默
  失效根因已修（声明缓存键、解析缓存键都须含档位）——细节见
  `docs/gaps/gap-language-pack-scope.md`「运行时档位：`enabled` 的语义边界」。
- ⚠ **`enabled` 只门控"声明面"**：插件的**规则文件与 Python 组件**走另一条路径
  （`setup_grammar` → `load_all_components(<pack>/plugins)`），不受 `enabled` 影响。
  C 包插件是纯 TOML、c4 插件是纯 Python，两条路径当前**恰好正交**；语义边界与两种候选
  语义（只门控声明面 / 门控一切）见 `docs/gaps/gap-language-pack-scope.md` 同名节。
  ⚠ **已有一个真实症状**（2026-09-26 实测）：`[[属性]]` **不依赖任何新关键字**，故
  **基线档也解析出 `AttributeSpec`**——"档位 = 接受域"在纯语法增量上不成立，判据见
  `test_c_standard_tiers.py::TestKeywordFreeIncrementsAreNotTierGated`。
- **"加标准"= 声明式注入，不改核心文件**：各插件用
  `[ExtRule.inject] targets = ["@核心规则.production[N]"]` 往既有交替里**加一支**
  （c11：`_Static_assert`→`Stmt`、`_Alignof`/`_Generic`→两处原子清单、
  `_Noreturn`→`FuncSpec`、`_Thread_local`→`StorageClass`、`_Alignas`/`_Atomic`
  →`TypeQualifier`；c23：`nullptr`/`true`/`false`→原子清单、`bool`/`typeof`→`SimpleType`、
  `constexpr`→`StorageClass`、`AttributeSpec`→`TypeQualifier` + **空槽位
  `AttributeSlot`**）。
  注入点的选择原则：**挑最窄的那条规则**——`SimpleType` 被声明/成员/参数/类型名四处引用，
  一次注入四处生效；`TypeQualifier` 被 **6 处说明符位**引用（`Declaration`/`SpecRest`/
  `FuncDef`/`MemberSpec`/`ParamSpec`/`TypeName`），`_Alignas`/`_Atomic` 都挂它；
  **中段位点则挑"空槽位"**（`AttributeSlot` 被声明符内与枚举项共用，同样一处声明两处生效）。
  反例（说明"最窄点"确实存在）：`_Alignas` 本该按标准的 declaration-specifiers 走，
  但本包**没有**统一的说明符序列规则，6 处各自列举——挂 `TypeQualifier` 是唯一
  一次到位的点（组合合法性归语义层，同核心基线口径）。
  判据守：`tests/languages/c/test_c_increment_plugin.py`（"原候选一支不少、序不变、
  来源可追" + `_Alignas` 覆盖六处说明符位 + `_Atomic` 两形态同环境并存）+
  `test_c23_increment_plugin.py`。
  ⚠ 三条形态坑（都被 fail-fast 或实测拦住，写在这防重踩）：① `production` 是**一条产生式
  的元素序列**（列表长度 = slot 数），备选要在**同一元素内**用 `|`；② 裸交替与逗号同现时
  `|` **先结合**（`"a|b, X"` = `choice[a,(b,X)]`，不是 `(a|b),X`）；③ **别依赖跨元素回溯**：
  选择器只在**同一元素内**换候选，`_Atomic` 的两种形态若拆成两条规则，单 token 那条命中后
  后续元素失败**不会回头**（实测整条声明空 AST）——写成一个规则里的可选组即可。
- **仍未落地的标准增量**：只剩 `[[属性]]` 的**四条形态边界** ①②④⑤（① 空实参 = 低优先；
  ② 相邻字面量拼接 / ④ 空属性表 = 不做；⑤ 配平 token 序列 = 暂不做）——见「未做」表。
  ✅ ③ 尾随逗号与多实参已于 2026-09-28 收口（判据见 `test_c23_increment_plugin.py`）。
  ⚠ 另有一条**档位边界**（不是缺语法）：`[[属性]]` 不依赖新关键字 ⇒ **基线档也解析**
  （详见「标准档位」节末与 `TODO.md`）。

## 渲染保真（原文打印）

闭环在 `tests/languages/c/test_c_render_fidelity.py`（3 样本 `ring_buffer.h` /
`ring_buffer.c` / `edge_comments.c`），七条判据：非空 / 行数覆盖 ≥ 80% /
`difflib` ≥ 0.80 / 幂等 / **注释清单**（源里每条注释正文必须出现）/
**首注释源序** / **显著 token 序列逐项相同**（内容级对拍，重排只许动空白）。

实测 ratio：`ring_buffer.h` 0.9926、`ring_buffer.c` 0.9925、`edge_comments.c` 0.9822
（判据口径 = 非空 / 行覆盖 ≥80% / ratio / 幂等 / 注释清单 / 首注释源序 / 显著 token 序列）。
**已知偏差逐条记在缺口档**（`case`/标号缩进、`for (;;)` → `for (; ; )`、注释落在括号内
首元素前的位置、分隔符后行尾注释随折行漂移等）——都是不丢 token 的排版差异，
**不在这里重复登记**：口径与成因见
`docs/gaps/gap-language-pack-scope.md`「C 包渲染/保真面现状」的「已知偏差」表。

补布局前先跑 `python tools/render_coverage.py grammar/c`：**引擎对无渲染配置的规则
静默输出空串**，缺布局是无声的保真度损失（本包最初 70 条规则只有 1 条有配置）。

## 符号收集产物（`phase` 分期）

符号基座首片（`docs/gaps/gap-c-semantic-base.md`）：**只收集、不改 parser**、不做
`(myint)x` 形态判定。每条记录（JSON 可序列化）：

| 字段 | 含义 |
|---|---|
| `name` | 符号名 |
| `kind` | `typedef` / `tag`（struct·union·enum 标签）/ `variable` / `function` / `enumerator` |
| `scope` / `scope_kind` | 作用域路径与种类（`<global>` / `<global>/FuncDef` / `<global>/FuncDef/CompoundStmt`） |
| `decl_order` | 收集序（≈ 源序，供"先声明后使用"判定）；`pre_scan` 期无（`None`） |
| `decl_line` | 声明所在源行（parser 挂的 `_pos_line`） |
| `phase` | 名称来自哪个时期：`analyze`（后置分析器，精确）｜`pre_scan`（词法预扫描，粗） |

**分期语义（作者硬要求）**：`pre_scan` 期是**文本级、平坦、首见归属**的粗收集
（`base/_pre_scan.toml`；无作用域/无声明序，引擎兜底正则还会带入类型词等杂质——头注有
逐条实测）——**只作提示与分期对比**；`analyze` 期由后置 analyzer 插件给出精确作用域 +
声明序。同一位点两期都有记录时**两条都保留**（`phases_for` 可判），形态判定只看
`analyze`（`is_typedef` 内已过滤）。

**默认偏置（显式化）**：未声明标识符 = `_api.DEFAULT_TYPEDEF_BIAS`（`"not typedef"`）——
`is_typedef()` 的缺省即此值，调用点勿再各自硬编码。

**落点与读取入口**（声明式：收集点/路径全在 TOML，插件只做通用原语）：

| 位置 | 作用 |
|---|---|
| `01_declarations.toml` / `02_types.toml` / `03_statements.toml` 的 `[Rule.analyzer.c_symbol_collect]` | 收集点 + AST 路径 + `typedef`/函数标记（语言知识全在参数里） |
| `base/_pre_scan.toml` + `tpc.toml` 的 `[lexer] pre_scan` | `phase="pre_scan"` 的来源（**只收集、不声明 `rule_hints`** ⇒ 不重排 parser 候选） |
| `plugins/semantics/_{symbols,_api}.py` | 原语/产物装配 + 只读查询 API（`phase`/`is_typedef`/`records_for`） |

```python
# 复跑（仓库根；`rules`/`parser`/`lexer` 按 tests/languages/c/conftest.py 的 `c` fixture 构造）
from analyzer.traversal import AnalysisTraversal
from grammar.c.plugins.semantics import _api

at = AnalysisTraversal(rules, rules_dir="grammar/c")
at.analyze(parser.parse(lexer.tokenize(src)))
_api.product_from(at)                      # 仅 analyze 期产物（读 context.extra["c_symbols"]）
_api.two_phase_product(at, src, "grammar/c")  # 两期合并（逐条带 phase）
_api.declaration_view(at)                  # **声明位置派生视图**（见下：声明位置问题的唯一入口）
```

⚠ `ProjectChecker.check()` 的公开结果不含 `extra`（刻意的结果面收窄）——需要产物时直接
用 `AnalysisTraversal`（上例）。判据：`tests/languages/c/test_c_symbol_collection.py`
（正/负/声明顺序/作用域遮蔽/分期/只增不改六条，另附缺陷态变红证明见 `CHANGELOG`）。

**「声明位置」问题一律走 `_api.declaration_view(at)`（唯一入口）**：产物记录的 `scope`/`scope_kind`
是**分析作用域**（P1 公开面，语义不变），而"这条声明在哪声明 / 算不算文件域声明"要用派生视图：

| 字段 | 语义 |
|---|---|
| `decl_scope` | **声明位置**：`FuncDef` 位取**父作用域**；`ParamDecl` 位为 `"param"`；其余同 `scope` |
| `is_file_decl` | 是否**文件域声明**（形参位恒 False） |
| `is_param` | 是否形参（无 linkage、不参与文件域） |
| `scope` / `scope_kind` | 原分析作用域（取证用，**语义不变**） |

两处**当前仍成立**的基座偏差（下节）正是该视图存在的原因；N2 同时把三元组写进 `Symbol.attrs`
（**不进产物**，先例 = `phase` 落 attrs 的作者裁决）。判据 `tests/languages/c/test_c_declaration_view.py`
（开发期一次性对拍核验 **11 源 / 76 记录 IDENTICAL**，探针不入库；结论以判据为回归守卫）。

## 符号基座两处错位（**当前仍成立的偏差**）

> 登记位置说明：基座缺口档 `docs/gaps/gap-c-semantic-base.md` 已满（199/200 行）⇒ 本偏差
> **暂登记于本节 + `TODO.md`**，待该档裁剪时并入。**处置 = 派生视图，不改 P1 公开产物**。

- **事实**：`is_file` **不是存储字段**——P1 产物 7 字段（`{name,kind,scope,scope_kind,decl_order,
  decl_line,phase}`）与 `Symbol.attrs` 都没有它；消费者各自用 `scope.parent is None` 推导，而
  C 包**没有任何文件域谓词**（只有 pre_scan 哨兵 `SCOPE_FILE_UNKNOWN = "<file>"`）。
- **形态①（原型形参落 `<global>`）**：`void f(int x);` 的 `x` 与文件域对象声明**同形**
  （`kind=variable`、`scope=<global>`、`is_file=True`、`decl_node=ParamDecl`）⇒ 任何"文件域"检查
  都会把形参当声明（链接性片 S2 的 `static int x; void f(int x);` 误报即由此而来）。
  成因：`[ParamDecl.analyzer.c_symbol_collect]`（`01_declarations.toml:369`）无 `scope` 配置，
  原型外层 `Declaration` 也无 ⇒ 收集时当前作用域仍是 `<global>`。
- **形态②（函数定义符号落自己的作用域）**：`void defn(void){}` 的符号 `scope=<global>/FuncDef`、
  `scope_kind=function` ⇒ 与它的 `<global>` 声明**不同 scope**；后果：`void f(void); static void f(void){}`
  这类真 UB **漏报**、"定义后的 `extern`"继承链断。
  成因：标准原语先于自定义原语（`analyzer/traversal.py:236-237`）⇒ `scope_enter` 已压栈
  （`03_statements.toml:126`），随后 `c_symbol_collect`（`:128`）把函数名声明进自己的作用域。
- **处置**：`_api.declaration_view()`（`decl_scope`/`is_file_decl`/`is_param`）**派生视图**；
  **不改 P1 公开产物**（改 `scope`/`scope_kind` 值或记录集命中升级判据 ①，需作者按契约面流程裁，
  已另立）；**派生视图是"声明位置"唯一入口**（避免两套真相漂移）。

## 存储类语义约束（CSC · 本包首个 check 组件）

**分工**：语法层**宽进**（`StorageClass` 是裸交替：`typedef|extern|static|auto|register` +
c11 `_Thread_local` + c23 `thread_local`/`constexpr`，各注入一支；函数说明符 `inline`/`_Noreturn`
另在 `FuncSpec`）；语义层在本组件判**组合与位置**约束，诊断 `severity = "warning"`（**不阻断管线**）。

| 落点 | 作用 |
|---|---|
| `plugins/semantics/_api.py::spec_capture` | 收集期按 TOML `capture`（`specs` + `specs_rest`）把说明符归一成短串，按**包声明分类**（`SC_NODE_NAMES` / `FS_NODE_NAMES`）挂符号 attrs：`sc` / `fs` / `is_function` / `has_init` / 声明起点 |
| `plugins/checks/storage_class/rules/storage.toml` | 规则=数据：`id`/`kind`/`severity`/`default`/`message`（**条款引文与档位写在头注**） |
| `plugins/checks/storage_class/rules/_storage_check.py` | L2 handler：`fn(symbol, rule, context)`，只读 attrs；**按声明去重**（多声明符只报一条） |

**默认开关按"条款档位"**（Lead 拍板 ①：无法确认原文 ⇒ `default = false`）：
`CSC001/002/003` 默认开（取得原文/原文+权威一致引文；真实语料零误报）；
`CSC004/007/008/009/010/011/012` 默认关（条款位置明确但未取得原文句，opt-in）；
`CSC005/006`（C23 `constexpr` 共现要求）**不实现**——权威转述与示例反证"须与 static/extern 共现"
（`constexpr float f = 23.0f;` 即裸用），实现会全量误报；`CSC001/002` 对 `constexpr` 保守放行
（`CSC_PERMISSIVE_SPECS`，宁可漏报不误报）。

**CSC001 禁止朴素计数**：判定 = 分类出的 `sc` 表 + **例外表**（`{static|extern} × {_Thread_local|thread_local}`）
比对，故头文件高频合法形态 `static inline int f(void){}` 不报（判据锁定）。**已知边界**：一条规则 id
只能绑一个 `kind`，故 CSC001 只覆盖对象声明；`static extern int f(void);`（函数位）**未覆盖**（登记）。

判据：`tests/languages/c/test_c_storage_class_checks.py`（正/负样本逐条 × 默认开关 + 多声明符去重 +
真实语料零误报 + 语法宽进不回归）；缺陷态变红（去例外表 / 去去重 各一次；对应变异见
`tools/check_gate_efficacy.py`）。

## 结构类型语义（TAG/ENUM · 本包第二个 check 组件）

**范围（S1-a 片）**：`struct`/`union`/`enum` 的 **tag** 与**枚举常量**在同作用域内的约束。
语法层宽进（`struct`/`union` 共用 `StructSpecifier`、`enum` 走 `EnumSpecifier`，都按 `site="named"` 采 tag），
语义层在本组件判定；诊断 `severity = "warning"`（不阻断管线）。

| 落点 | 作用 |
|---|---|
| `02_types.toml:48`（`StructSpecifier`）/ `:145`（`EnumSpecifier`） | `tag_capture = { kind_path/body_path/default_kind }`：种类（`struct`/`union`/`enum`）与**有无体**（定义 vs 引用/前向声明）——语言知识在 TOML |
| `plugins/semantics/_api.py::_named_attrs` | `site="named"` 采集：把 `tag_kind`/`has_body` + 声明起点挂符号 attrs（`collect_named_site` 统一入口） |
| `plugins/checks/type_semantics/rules/types.toml` | 规则=数据（`id`/`kind`/`severity`/`default`/`message`；**条款引文与档位写在头注**） |
| `plugins/checks/type_semantics/rules/_tag_check.py` | L2 handler：只读 attrs + 同作用域符号表 `scope.symbols`；**按 `(规则, 名, 作用域)` 去重** |

**规则与档位**（`default` 由条款档位自动定）：
`TAG001` 同一 tag 内容至多定义一次（§6.7.2.3 原文；**只在冲突双方都带体**时报）、
`TAG002` 同一 tag 必须同用 struct/union/enum（§6.7.2.3 原文）、
`ENUM003` `enum E;` 无枚举列表只能出现在完整之后（§6.7.2.3 原文）⇒ 三条 **`default = true`**；
`ENUM001` 同作用域枚举常量重名、`ENUM002` 反向（普通标识符撞枚举常量）——依据是 §6.7.2.2 **脚注 107**
（非规范性）⇒ **`default = false`**（opt-in）。**枚举值重复永不实现**（§6.7.2.2 note 明确允许）。

**免误报两条硬约束**：① TAG001 只在**双方都带体**时报（§6.7.2.3：可见声明存在时该类型说明符
**不重声明 tag**）；② 全部判定限定**同作用域**（`scope.symbols` 只含首例，第二例用 `is not` 区分）。
实测：真实语料 **9 条带体定义 + 24 条无体引用**，naive"同 tag ≥2 次即报"会误报（未去重 24 条；
本实现的去重口径下缺陷态复现 3 条）。

判据：`tests/languages/c/test_c_type_semantics_checks.py`（13 正样本 × 全规则启用 + 9 负样本逐条 +
位置 + 三次定义去重 + 两档语料零误报 + 默认开关按档位）；缺陷态变红（去"双方带体" / 去作用域判定
各一次；对应变异见 `tools/check_gate_efficacy.py`）。**边界**：成员重名（C99 原文无约束句）、不完整类型使用、位域宽度、
枚举值 representable-as-int、跨 TU；C23 固定底层类型枚举（`enum E : int;`）本包语法面**尚未支持**
（lint 拒）⇒ ENUM003 的"固定底层类型恒完整"豁免暂不适用，将来支持时需同步。

## 标签与 goto 语义（LAB · 本包第三个 check 组件，走 **postpass**）

**范围（S4 片）**：① 同函数内 label 名唯一 ② `goto` 目标必须是所属函数内的 label
③ `case`/`default` 只能出现在 switch 语句内。三条均 **A 档原文**（§6.8.1 ×2、§6.8.6.1 ×1）
⇒ `default = true`、`severity = "warning"`（不阻断管线）。

**形态与其他两个 check 组件不同**：label/goto **不进符号表**（`analyzer.all_symbols` 只有函数）⇒
没有 `sym.kind` 可供 `[[checks]]` 分发；本组件用 **`[[analyzer.postpasses]]` 走 AST**
（先例：verilog `checks/unused_check`）。**AST 入口 = `analyzer._ast`**
（⚠ `AnalysisContext` **没有** `ast` 字段，实测 `vars(context)` 无 `ast`）；规则仍为数据
（`rules/labels.toml`，其 `kind` 永不被符号命中 ⇒ 引擎按 kind 分发天然 no-op），postpass 用
`analyzer.checks.active_rule_ids(analyzer)`（引擎为该类插件预留的同一激活逻辑）只跑激活规则，
并把函数内标签/跳转摘要 + 违规清单写 `context.extra["c_labels"]`（观测产物）。

| 落点 | 作用 |
|---|---|
| `plugins/checks/labels/tpc.toml` | `[analyzer] + [[analyzer.postpasses]] run = "rules/_label_check.py:run_label_checks"`、`produces = ["c_labels"]`（组件判定键之一 = 有 postpass ⇒ 本组件是**真组件**，与两个规则-only 组件形态不同） |
| `plugins/checks/labels/rules/labels.toml` | 规则数据：`LAB001`/`LAB002`/`LAB003` 的 `id`/`kind`/`severity`/`default`/`message` + 条款引文与档位头注 |
| `plugins/checks/labels/rules/_label_check.py` | postpass：按 `FuncDef` 分组收 `LabelStmt.name` / `GotoStmt.label` / switch 之外的 `CaseLabel`/`DefaultLabel`；节点名/字段名 = **包侧常量**（先例 `SC_NODE_NAMES`；组件 tpc.toml 自定义段会被引擎忽略） |

**三条硬要求（误报面实测驱动）**：
1. **只收 `LabelStmt`**——`case`/`default` 是 `CaseLabel`/`DefaultLabel` 独立节点；语料
   `ring_buffer.c` **同一文件**里既有 `done:`（LabelStmt）又有 `default:`（DefaultLabel），
   实测整文件 LabelStmt=1（缺陷态把它们当 label 收 ⇒ 该文件必报 `LAB001` 1 条）；
2. **前向 goto 用两遍扫描**（先收全函数内 label，再判 goto 目标；缺陷态单遍 ⇒ 合法
   `goto done;` 在该文件报 `LAB002` 1 条）；
3. **按函数分组**（label 具函数作用域、跨块可见）⇒ 不同函数同名 label 合法、嵌套块 label + 外层
   goto 合法；LAB003 按"**存在外层 `SwitchStmt` 体**"判 ⇒ Duff's device（switch→do/while→case）合法。

判据：`tests/languages/c/test_c_label_checks.py`（11 正样本 × 全规则启用 + 7 负样本逐条 + 位置 +
三次重复去重口径"第 2..n 处各一条" + 两档语料零误报 + `c_labels` 产物 + postpass 轨迹）；缺陷态变红：
上列三条硬要求逐条去掉（重复 label / switch 归属两例由 `tools/check_gate_efficacy.py` 变异覆盖；实测后果
见上）。**测试注意**：`plugin_loader._loaded_components` 是**测试级全局态**
（`tests/conftest.py` 逐测试还原）⇒ 依赖 postpass 的测试须逐测试 `load_all_components(plugins_dir)`。
**能力声明**：`[analyzer]` 段 ⇒ `analyzer.primitives.v1`、`rules/*.toml` ⇒ `checks.rules.v1`，
均已声明 ⇒ **本组件不需要新的 `[engine] uses` / `[plugins] enabled` 条目**。
**边界**：VLA 跳入（需类型面）、`case` 值重复 / 多个 `default`（原文未取得 + 需常量求值）、
label 未使用（无条款约束，风格）、宏展开产生的标签、扩展语法（`__label__`/`asm goto`）、跨 TU。

## 宏实参个数（MAC · 本包第四个 check 组件，走 `ast_optional` postpass）

**分工**（作者 2026-10-17）：宏的**形式化语法**（`#define` 的宏名/形参表/宏体算子形态）
走 linter（`linter/macro_syntax.py`，AST 前，对原始源码）；**语义级**（实参个数，需宏表 +
调用点上下文）走本组件。规则 **A 档**：C99+TC §6.10.3 原文（段 1903/1904/1918）⇒
`default = true`、`severity = "warning"`（不阻断管线；需退出码 1 用 `checks.overrides` 提级）。

| 落点 | 作用 |
|---|---|
| `plugins/checks/macro_args/tpc.toml` | `[analyzer] + [[analyzer.postpasses]] run = "rules/_macro_args_check.py:run_macro_arg_checks"`、**`ast_optional = true`**（解析失败也执行的关键）、`produces = ["c_macro_args"]` |
| `plugins/checks/macro_args/rules/macro_args.toml` | 规则数据 `MAC001`（`kind = "macro_call"` = 本组件自用标记，符号 kind 分发天然 no-op）+ 条款原文/档位/**不实现**登记 |
| `plugins/checks/macro_args/rules/_macro_args_check.py` | postpass：读引擎注入的 `CTX_MACRO_INVOCATIONS`（展开期事实），逐调用点判 arity；诊断挂**调用点替身节点**（`_pos_original = True`，位置已是原始源坐标） |

**为什么必须 `ast_optional`**：实参不足时展开结果常是非法语法（`F(1)` → `1+`）⇒ parse 失败
⇒ 常规语义阶段跳过整文件。事实型 postpass 不依赖 AST，故解析失败也跑（机制见
`analyzer/semantic_checks.md` §5.4）；`test_too_few_args_reported_even_when_parse_fails`
是该键的直接判据。

**判定口径**（gcc 16.1.0 `-pedantic-errors` 四档对拍）：非变参宏 `slots == 形参数`（n == 0 的
合法形态只有 `Z()`：括号内空 token 序列 = 0 个实参；`Z(/*c*/)` 同——注释在翻译阶段已换成
空白）；变参宏 `slots >= 具名形参数`。合法零误报形态：`Z()` / `Z( )` / `Z(/*c*/)` / `O()` /
`F(,)` / 变参恰好具名 / 头文件宏在本文件调用 / 后置定义前的同名调用 / 重定义前后各按其时形参。
**顺序语义**：形参表取**调用点时点**的可见值（`preprocessor/macro_timeline.py`：`scan_directives`
输出的定义/取消事件按原始源行号记账；引擎在 `map_invocations_to_source` 里回源+过滤）——展开器
仍用最终宏表（历史近似），检查侧不跟着误判。
**边界（登记不实现）**：变参"恰好具名个数"（C99–C17 pedantic 级、C23 起接受 ⇒ 无档位感知
不判）、宏体**内部替换**产生的嵌套调用（无源码坐标，不记事实）、`#if` 表达式内调用、
被包含文件内的调用点（无本文件坐标；头文件定义按 include 行快照）、行拼接段内调用点
（行列不可靠 ⇒ 丢弃）、`#undef` **之前**的调用点（展开器最终宏表 ⇒ 根本不展开 ⇒ 无事实）。
**接缝重扫出的调用**（`#define g f` + `g(2)` 展开出的 `f(2)`）与**跨行调用**（`F(1,`
+ 下一行 `2)`）**有**事实、照常判（同一文本点可能两条事实：外层与内层各一条，不合并）。
判据：`tests/languages/c/test_c_macro_args_checks.py`（25 条：少给/多给/零参/变参缺具名 +
合法零误报 + 原始行定位 + 规则可关闭 + include 两向 + 定义时间线四态 + 豁免 + 边界守卫 +
接缝三态 + 跨行两态）；`tests/engine/preprocessor/test_macro_timeline.py` 13 条（事件记账/时点解析/回源过滤）；
缺陷态变红 = 门禁变异
（去掉调用点事实 / 去掉 `ast_optional` 执行 / 去掉零参判定 / 去掉原始坐标跳过映射 / 去掉定义时间线过滤）。

## 预处理面（阶段 4 首片 A）

配置挂载：`tpc.toml` 的 `[preprocessor] macro_config` / `directives` / `expand` 均指向
`base/_macro.toml`；`#` / `##` 是 `base/_token.toml` 的符号声明。

声明面（`base/_macro.toml` 的 `[macro_recognition]`）：

| 键 | 值 | 含义 |
|---|---|---|
| `shape` | `"symbol.base.hash,name"` | 指令形态：`#` 前缀 + 名字位（候选 `macro.define`/`undef`/`include`） |
| `call_shape` | `"name"` | **显式"无前缀"** ⇒ C 的**裸标识符宏调用**（引擎不默认允许空前缀） |
| `call` | `[]` | 名字位任意标识符（是否真展开由**宏表**决定） |
| `stringize_operator` / `paste_operator` / `variadic_name` | `"#"` / `"##"` / `"__VA_ARGS__"` | 宏算子（语言包声明；未声明不启用） |
| `call_args` / `arg_separator` | `bracket.l_parentheses,args,bracket.r_parentheses` / `symbol.base.comma` | 带参宏实参形态（定义侧与调用侧同形） |

**当前支持**：对象/函数/变参宏、`#` 字符串化（token 间空白折叠、字面量内部不动）、
`##` 粘贴（**未展开拼写**）、hideset 重扫描（自引用/互递归抑制）、
**接缝重扫**（替换文本 + 源码后续一起重扫：`g(2)` 别名 / `f(2)(9)` ⇒ GCC 同语义；接缝 hideset
按 Prosser 交集口径）、**跨行调用**（实参列表 / 名字-开括号跨物理行，行数不变展开）、
`#undef`、字符串/字符/行注释/块注释**掩码（含宏体内部）**、名字与 `(` 间注释、
**`#include` 真实包含**（内容进分析流、渲染前剪枝）、**`#if`/`#elif` 整型常量表达式**
（声明面 `[condition]`，交付面见 `docs/gaps/gap-c-preprocessor-scope.md` ㉑）、
**宏实参个数检查**（`plugins/checks/macro_args/`，见上节 MAC）。
**不含**：`#line`/`#error`（`#pragma`/`_Pragma` 走保真穿透 + marker）、
C23 项（`#warning`/`#elifdef`/`#embed`/`__VA_OPT__`/`__has_include`）。
边界档案：`docs/gaps/gap-c-preprocessor-scope.md`；门禁：`tests/engine/preprocessor/test_macro_*.py`。
**已声明边界**（详情与用例见 `preprocessor/README.md`「已知边界」）：跨行调用仅 splice 处置、
接缝重扫不跨行、前瞻上限外不展开（256 行 / 8192 字符）、沿用最终宏表、渲染行结构可重排
——以守卫断言锁在 `tests/engine/preprocessor/test_macro_multiline_call.py` / `test_macro_rescan.py`。

## P4 理解路径（两段协作）

歧义路径（`x = (myint)y;`：`myint` 是不是类型名）走**两段协作**，能力都必须有：

| 段 | 落点 | 做什么 |
|---|---|---|
| **承载** | `parser/block_parser.py`（引擎，P4 第一步） | raw 节点：`_verbatim_text`（渲染权威）+ `raw_names`/`raw_line`/`raw_column`/`raw_order` + **`raw_candidate`**（候选子树，已还原源码原文）+ `raw_substituted`（取证）。承载期 `sub_node == []` |
| **理解** | `plugins/semantics/_raw_understand.py`（analyzer postpass） | 语义二次确认（不绕过遍历期 P4 校验 `validate_raw_statement`）+ **结构选定**（候选里出现 `UNDERSTOOD_STRUCTURES`）⇒ 结论挂 `raw_understand`，摘要进 `context.extra["c_raw_understanding"]` |
| **改树** | `plugins/semantics/_raw_transform.py`（transform 插件） | 按结论把 `raw_candidate` 提升为 `sub_node`（`RawStatement > ExprStmt > … > CastExpr`），**保留 `_verbatim_text`** |

**契约 A3 的有意升级 + 不变式**（承载期 → 提升后）：

> **渲染权威 = `_verbatim_text`**（`renderer/node_renderer.py` 对带该标记的节点整段直出、
> 不遍历子节点）；**子树只是分析的确定结构，其显著 token 序列必须与 `_verbatim_text` 等价**。

三条推论（都有判据）：① 提升**不改渲染**（直出早返回）；② `Node.iter_children()` 含属性挂载的
子节点 ⇒ 提升后候选同时挂在 `sub_node` 与 `raw_candidate`，按 `id` 去重 ⇒ 遍历**恰好一次**；
③ 提升幂等（`sub_node` 非空即跳过）。

**诚实边界**：`(t){1}` 复合字面量在承载期建候选失败 ⇒ 不提升、不报错（raw 仍直出，
行为与本批之前一致）；该形态要进入理解路径需先补承载期。判据：
`tests/languages/c/test_c_raw_understanding.py`（管线级：结构/保真/幂等/负样本/边界）、
`tests/engine/analyzer/test_p4_raw_understanding.py`（两段单元判据，含去重与幂等）。

## 写包者须知（本包实测教训，写新包必看）

1. **叶子规则要语言包自己定义**：`Identifier` 这类规则**引擎不内置**，漏定义时
   `@Identifier` 匹配为空，症状是 `match_length 0` / `expected ';' got 'id'`
   ——**看起来像规则形态问题**（本包为此证伪了五个形态假设才定位到规则缺失）。
2. **token 键不能重复**：同串两键（`equal` / `assign` 都是 `=`）词法取后者，
   所有引用前者的规则**静默失配**，报错方向完全看不出是命名问题。
3. **可选位点会掩盖词法失效**：字面量正则多转义一层时数字从不被识别，而当时
   数组长度与枚举值都写成可选 ⇒ 症状是"静默为空"而非报错。加可选捕获要配非空断言。
4. **表达式环三件套**（缺一即 `setup_grammar` 报 `RecursionError`）：原子
   `is_atom = true`、入口规则 `pratt = true`、选择器 `inline = true` 且 production
   为**单条交替**。见 `00_expressions.toml` 头注与 `parser/expression_conventions.md`。
5. **空洞是无声的**：不属任何语句入口 FIRST 集的构造会被**整体跳过、既不解析也不
   诊断**——补能力前后跑 `tools/c_acceptance.py` 对照，别只看测试是否绿。
6. **缺口先落档再闭环**：本包词法面三条"配置表达不了"的缺口先记档（各写明为什么
   现机制表达不了），随后各补一个声明键全部闭环——记档不是拖延，是防止下一个包重踩。
7. **引用 token 时先确认它声明在哪张表**：完整类型名 = 表名 + 键名，**不是**固定的
   `symbol.base.*`。`ellipsis = "..."` 声明在 `[symbol.extend]` 下 ⇒ 引用要写
   `symbol.extend.ellipsis`；写成 `symbol.base.ellipsis` 的症状是"该元素永不匹配"，
   与"形态表达不了"**一模一样**——本包为此把变参 `...` 误记成"需引擎侧形态"的缺口
   整整一轮（真根因还有一条引擎缺陷：lexer 最长匹配曾要求中间前缀也声明过，
   `...` 卡在未声明的 `..` 上被降级成三个 `.`；两条都修好后是纯配置可达）。
8. **解析进 AST ≠ 保真**：尾段写成**独立可选元素**（紧跟重复组之后）时，`items` 绑定
   拿不到它 ⇒ 渲染把 `...` 静默丢掉（实测输出 `int printf(const char *fmt);`）。
   落重复组迭代项的写法（`(comma,(@ParamDecl|symbol.extend.ellipsis))*`）才会进
   `items`、按源序渲染。若尾段是**标点**（尾逗号），则改走**单独绑定** + 布局显式渲染
   （先例：`EnumBody` / `InitList` 的 `trailing_comma`、c23 属性表尾逗号）——标点塞进
   `items` 会与 join 分隔符叠加成 `, ,`。改参数表/列表类规则后**都要跑一次渲染对拍**。
9. **块语句"建成块规则"还是"建成普通语句"，先看包有没有自己的语句序**：c4 的
   `BlockStmt` 是块规则（`is_block = true`，body 由 `parse_block_body` 循环产出，
   renderer 用 `role = "flatten"`），linter 因而拿到块体（`_discover_block` /
   `_block_body`），块内每条坏语句各报一条；本包的同位规则 `CompoundStmt` 是普通语句
   （`@Stmt*` 由父 checker 内联匹配），块内多个错误只报一条。**但改成块规则不是免费
   的**：块体语句随即改走**引擎的规则选择器序**（`RuleSelector` 按规则装载序排候选），
   而本包刻意用 `Stmt` 的有序交替表达"`@ExprStmt` 先于 `@Declaration`"——实测改成块
   规则后 `void f(void) { x; }` 的体内语句会从 `ExprStmt` 变成 `Declaration`。
   故这条取舍的先决条件是"包能声明块体语句的候选顺序"（包侧无此表达面）。见
   `TODO.md`「C 块内诊断粒度粗」。
10. **要给"序列中段"加形态，别硬注——用空槽位**：注入只能并入**某一条既有元素**
    或越界追加到**末尾**，插不了中段（实测两条死路：`choice[repeat, @Attr]` 里"可空
    repeat 永远先成功 ⇒ 属性支试不到"、中段根本没有交替点）。做法 = 核心把中段做成
    一条**空槽位**规则（`production = []` 的非块规则 + 宿主写 `@Slot*`），插件注进槽位
    ——"插元素"退化成"给规则加形态"，还能让多个位点共用同一槽位。样板：本包
    `01_declarations.toml` 的 `AttributeSlot`（声明符内 / 枚举项共用）；语义见
    `grammar/grammar_rule_fields.md` §production、`docs/language_walkthrough.md`「规则注入」。

## 参照

- **ISO/IEC 9899:1999（C99）**：§6.4 词法、§6.5 表达式、§6.7 声明、§6.8 语句。
- [`clang`](https://github.com/llvm/llvm-project) 手写 parser：后缀链的
  "leading part + 后缀循环"（`ParsePostfixExpressionSuffix`）是本包 `PostfixExpr`
  的形态来源。
- [`tree-sitter-c`](https://github.com/tree-sitter/tree-sitter-c)：消歧与
  `prec` 声明对照（并记了一处本包**照标准、比它宽**：下标 `[ expression ]` 允许逗号）。
- 借入点与"不实现"的原因逐条记在 `docs/references.md`「C 语言文法参照」。

## 配套文档

- `grammar/README.md`（语言包目录约定、inject 归组）
- `docs/gaps/gap-language-pack-scope.md`（语言包范围 / C 语言包：接受域现状 / C 包渲染·保真面现状）
- `linter/linter_architecture.md`（linter 分层与已知边界；语句发现/区间判定口径）
- `parser/expression_conventions.md`（表达式隐式约定，含 `pratt_level`）
- `core/component_protocol.md`（加语法结构 / 插件的工作流）

# Gap — 语言包范围与 yaml 边界（规模 / SV / 插件划分 / 增强语法）

- 状态：范围声明（刻意选择）+ 现状跟踪（C 包接受域 / 渲染保真 / 运行时档位边界）
- 关联：ROADMAP「SystemVerilog 语言包」「C 语言包」；`grammar/yaml/`、`grammar/c/`
- 参照：Clang 式分层（core 语法 + 插件增量）；YAML 1.2 规范（plain 标量严格性）

## 边界是什么

1. **中小语言**（接受）：配置驱动语法是 DSL/子集/自定义扩展的最佳点（c4、Verilog
   核心）。大语言推荐做**精选子集**——C++ 规模语法的墙是**规则规模与语义深度**
   （数百 production/模板实例化/重载），不是上下文敏感（解析器经符号表解决
   `a*b` 声明 vs 乘法）；TOML 配置无法压缩，也不是本工具目标。
2. **配置有学习曲线**（接受）：语法包横跨五类配置面（语法 production / 节点 `$N`
   绑定 / analyzer 钩子 / transform 输出 / renderer layout），各有隐式约定。二次开发
   入口：`docs/MODEL_INDEX.md` + `core/component_protocol.md`。
3. **非行为验证器**（接受）：校验良构（语法/结构/命名/跨模块一致），不仿真/不综合，
   不判断硬件正确性——前端/规范执行工具，非正确性证明器。
4. **无 SystemVerilog**（backlog）：包目标 Verilog-2005；SV 构造（interface/class/
   always_ff/assertion/package/UVM）不在当前范围。加 SV = **core + plugin 增量**
   路线项（ROADMAP），非引擎改动。
5. **Verilog-2005 标准面已齐；可综合核心 vs 仿真/库插件**（接受 + 余量跟踪）：主包
   覆盖可综合子集；仿真/库语法在 `plugins/syntax/`（gates 26/UDP/specify（含
   defparam）/configs/nettypes/attributes + sim（initial/fork/过程 assign 等））。
   剩余余量（darkriscv 嵌套条件编译位置精度等）与 `docs/references.md` 跟踪。
   **头部参数列表续项不带关键字**（`#(W = 8, D = 4)`）未支持（现只接受每项重复
   `parameter`）：2026-10-19 扫 `tests/e2e/samples/real` 18 个 `.v/.sv` 及全 samples
   的 58 个 module `#(...)` 头 = **0 例** ⇒ 按"无需求不补语法"记**既定取舍**
   （触发：真实项目出现；届时补规则 + 用例）。
6. **yaml 缩进推断锁**（接受 + 摩擦）：`[indent] level="auto"` 首结构行锁定单位；
   混单位文件锁定后错解析；渲染器经 AST-root `_indent_unit` 戳重缩进到锁定单位
   ——块标量逐字内容仅在源单单位时保持对齐。
7. **yaml plain 标量配置宽松近似**（摩擦）：`[plain]` 模式（字符类 +
   `stop_space_after`/`no_space_after_tokens`/`flow_terminators`）覆盖真实配置值形态
   （`${{}}`/URL/多词/CJK/词内 `,{}[]`）——偏离 YAML 1.2 严格 plain 规则。剩余 gap：
   数字引导多点多值（`1.2.3` 拆分，number 分支赢）、无 tab 分隔词、值不跨行、带转义
   引号不支持。
8. **增强语法 linted 非豁免**（事实）：前置 linter 共享 parser 规则表（含插件语法），
   合法 `type`/`type.role`/`impl` 构造过 lint 门禁；`no_lint=True` 是逃生门但不需要。

**为什么是范围（影响面）**：1/3/4/5 是产品定位（面向可配置规范执行的 DSL/子集工具），
做大语言/SV/仿真是路线项非缺陷；6/7 是 yaml 包以"配置宽松"换"覆盖真实值形态"的取舍；
8 澄清增强语法不需逃生门（防误导）。1/2/3/8 不改；4 在 ROADMAP；5/6/7 按需处理（yaml
`1.2.3` 拆分需 plain 分支优先级重排，混单位是捕获层约定、改动需 yaml 语料门禁）。

## C 语言包：接受域现状

- **判据（每族都要有）**：正样本解析通过（进 AST）+ 负样本被拒（linter/parser 报错），
  两向都要断言——只有正样本会漏掉"语法过宽"。
- **盘点工具**：`python tools/c_acceptance.py`（42 条构造逐条试解析，报"进 AST / 空 AST /
  词法抛错"）——当前 **42 条 / 接受 42 / 空洞 0**（**口径注**：两条预处理用例按"**被消费且无异常**"
  接受——指令行被替换为整行 marker 注释，**不代表 `#include` / `#define` 已真实实现**，见
  `docs/gaps/gap-c-preprocessor-scope.md` ⑭）。空洞是无声的：不属任何语句入口 FIRST 集的
  构造会被整体跳过而不报错，只跑测试套件看不出还差哪一族。
- **仍存的接受边界**（其余族已落地，由 `tests/languages/c/**` 与上述工具守住）：
  | 边界 | 归属 |
  |---|---|
  | `#include` / `#define`（工具计数已为 0——按"被消费且无异常"接受；**能力面仍是缺口**） | 阶段 4 预处理，ROADMAP「C 语言包」 |
  | `c89` 基线切层（把 C99 新增项从核心基线剥出） | **不做**（2026-10-09 定）：核心基线 = C99 语法面，"C89 等效"不是目标 |
  | VLA（C99 新增） | 与语义/求值强耦合，延后 |
  | typedef 名起头的强制转换 `(myint)x` | 需符号表/作用域/声明顺序；失败模式是**整个函数截断丢内容**（不只是该语句）→ `docs/gaps/gap-c-semantic-base.md` |
  | 逐声明符位宽 `int a : 3, b : 4;` | 本包宽度绑在整个成员声明后（一个 `DeclaratorList` 共用一个宽度）；见 `grammar/c/02_types.toml::StructMember` 注释 |
  | 明确不做（取舍） | 独立编译/链接、优化、完整类型推导与求值、实现定义行为（位宽/对齐）、K&R 老式函数定义 |
- ⚠ 工具的构造清单必须与本表**逐行对照**：清单自己也会漏项（"专治无声空洞的工具自己
  有一个无声空洞"），纪律写在 `tools/c_acceptance.py` 的清单注释里。

## C 标准等效缺口（阶段 5「标准等效断言面」；#33 立表 / #35 收口成员位）

> 阶段 5 缺的是**按标准分档的断言面**（ROADMAP「C 语言包」）。第一批先把**静态断言族**
> 做成接受/拒绝双向断言，并用 oracle 把「合法但被拒」的标准项逐条照出来——本节是
> 缺口全表（当前余 **3 条样本**，成员位与字面量族已转正）；判据在
> `tests/languages/c/test_c_standard_conformance.py`（`xfail(strict=True)`：**修好一条就红一条**，
> 提醒移出清单并转正）。

**oracle**：`gcc 16.1.0`（MinGW-W64），逐样本
`gcc -std=c11|c17|c23 -pedantic-errors -fsyntax-only case.c`。下表「gcc」列 = 该样本首个
不接受的标准档位之前全部 OK；tpc 列 = 当前实现（`enabled` 档位下）的实测归宿。

| # | 构造（合法标准代码） | 标准归属 | gcc | tpc 现状 | 成因 / 修法 |
|---|---|---|---|---|---|
| 1 | `_Static_assert(1);`（下划线拼写、单参） | C23 §6.7.10（消息可省，与 `static_assert` 同语法） | c23 OK | 拒绝 | c23 插件不能为它写规则：`enabled` 只门控**声明面**，插件规则文件无条件加载 ⇒ c23 里引用 `keyword._Static_assert` 的规则会在 c11/c17 档生效，把 C11 该拒的形态放进来。修法 = 规则按档位门控（`enabled` 语义扩展） |
| 2 | `int n = 1'000'000;` | C23 §6.4.4.1（digit separator） | c23 OK | 拒绝 | 数字扫描器的 DFA 不支持分隔符（引擎 `lexer/number_gen.py`；c23 侧需声明式开关） |
| 3 | `enum e : int { A };` | C23 §6.7.2.2（enum-type-specifier） | c23 OK | 拒绝 | `EnumSpecifier` 缺"标签后 `: 类型说明符`"位；core 生产式要加可选组，属包内语法改动 |

**已收口**：① C23 单参 `static_assert(1)`（循环 #33）；② **字面量前缀族 + 二进制常量**
（循环 #37，原表 u8 字符串 / u8 字符 / 二进制三行）——修法 = 引擎 `[string] prefixes`
声明面（前缀进 token 正文，按档位由插件 `token_ext` 增删：L 在核心、u/U/u8 字符串在 c11、
u8 字符在 c23）+ c23 数字形态按名合并给 `c_prefix` 加 `0b` 分支；
③ **静态断言的 struct/union
成员表位**（循环 #35，原表 #1/#2）——修法 = 容器级**空槽位**
（`StructBody = { (@StructMember|@StructMemberExtra)* }`，增量注入 `@StructMemberExtra`），
**不碰 `StructMember` 自身**：注入它会让 FIRST 混入 `keyword._Static_assert`，顶层同类语句
被误分类成 `StructMember` 报 `phase-statement` 假红（干净对照见
`policy/collaboration.md`「因果句必须带对照」的循环 #33 先例）。C23 两形态同时改成
Verilog `FuncDecl` 同款的 **inline 分派器 + 两分支**（两参/单参各自节点名）。
接受面继承档位矩阵（构造数按 `pytest --collect-only -q` 实测），拒绝面与下档三态
（generic / rejected）在 `test_c_standard_conformance.py::TestRejectSide /
TestBelowTierState / TestStaticAssertMemberPosition`；`gcc` 对照样本见 `_GAPS` 每条注释。

**下档三态是"接受域"口径的一部分**（"未声明关键字 ≠ 拒绝"）：同一形态在未达档位时要么
被当普通构造照常解析（`bool f;` / `_Static_assert(1, "x");` 在基线档当 typedef 名/函数调用），
要么整体套不进任何语句形态（`typeof(int) z;` / `_BitInt(8) a;` 在基线档 ⇒ 空 AST）。
两态都有断言，避免"没报错 = 支持"的误读。

## C 包渲染/保真面现状

**闭环判据** = `tests/languages/c/test_c_render_fidelity.py`（**62 例**；3 样本
`ring_buffer.h` / `ring_buffer.c` / `edge_comments.c`）。源文本 → tokenize → parse →
render → 与源比对，七条：

1. **非空**（缺渲染配置时引擎静默输出空串——本包最初 1/70 覆盖率的真实症状）；
2. **行数覆盖**：渲染行数 ≥ 源文件有效行数 **×80%**（防"只渲染出一部分"）；
3. **`difflib` 比值** ≥ 0.80（容忍格式化差异，抓内容丢失）；
4. **幂等**（渲染结果再过一遍管线，逐字相同）；
5. **注释清单**：源里每一条注释正文都必须在输出里出现（抓"某条被静默吞掉"）；
6. **首注释源序**：同一位置领到的多条独占行注释，渲染顺序与源一致；
7. **显著 token 序列逐项相同**（`(type, content)` 序列，trivia 与注释除外）——内容级
   对拍，重排只许动空白、不许动 token 的序；`i++` → `++i` 这类 difflib 抓不到的
   顺序错由它一眼看出，且语言无关。

| 项 | 实测 |
|---|---|
| `python tools/render_coverage.py grammar/c` | **115 条规则 / 115 有渲染配置（100%）** |
| `samples/ring_buffer.h` ratio | **0.992553** |
| `samples/ring_buffer.c` ratio | **0.992543** |
| `samples/edge_comments.c` ratio | **0.982216** |

- 表内 ratio 口径 = 判据 3 的 `difflib.SequenceMatcher(None, src, out).ratio()`（复现：
  `python -m pytest tests/languages/c/test_c_render_fidelity.py -q`——判据阈值 0.80，
  四位小数是实测记录）；行覆盖口径 = 判据 2 的"行数 ≥ 源有效行 ×80%"，**不是**逐行命中。
- 引擎另有 `keep_blank` 级（按源结构位置回插空行，`renderer/fidelity.py`），语义由
  `tests/engine/renderer/test_fidelity.py` 覆盖，本包不复制门禁。

**注释三级形态（设计意图）的落地位置**：

| 级 | 载体 | 实测 |
|---|---|---|
| line（`//`，独占行） | `Comment` **节点**（list-spec 消费的 repeat 上浮为迭代项，容器首元素前由 claim 领为子节点） | `enum` / struct 体 / 语句间 / 顶层均保住 |
| block（`/* … */`，独占行） | 同上（`Comment` 节点） | 保住 |
| inline（行中，前后同行有代码） | 节点**元信息**槽 `_comment_slots`（`inline_after` 锚 token / `inline` / `trailing`），不另立节点 | `int a /* c */, b` / `f(a /* c */, b)` 均保住 |

### 已知偏差

（逐条；#11 为位置漂移（单份、幂等）；#10 为引擎潜伏残洞、现有布局未触发；#8/#9 已于循环 #30/#31 修复删除，历史见 CHANGELOG）

| # | 现象 | 原因 / 现状 |
|---|---|---|
| 1 | `case` 体不额外缩进、标号缩进与源不同（`done:` 被缩进） | `CaseLabel`/`LabelStmt` 是独立语句规则（C99 里 label 只拥有**一条**语句）；要修需"标签后同级后续子节点多缩进一级"的引擎能力 |
| 2 | `for (;;)` → `for (; ; )` | 三段用字面 `"; "` 拼以保 `for (int i = 0; …)` 的空格；空段多出空格，合法 C |
| 3 | 注释落在**括号内首元素前**时被提到括号外 | `_lift_gap_comments` 项间窗口上界用"迭代末行"；**收紧窗口已验证不可行**（上界改迭代首行后 6 处门禁变红）。要修需把归属判据改为**迭代 token 跨度** |
| 4 | 注释项前多一个行尾空格 | 列表折叠后注释项独占行，父布局的分隔空格留在行尾；纯空白差异（输出合法、幂等） |
| 5 | `#include` **未真实包含**（`expand_macros` 默认 false 时管线报 `parse truncated`；默认口径由 A2 ① 统一后指令被消费但**内容未进流**） | A1 已把 `#`/`##` 声明为符号/算子 ⇒ **不再有** `Unexpected token: #`；真实实现（`path_forms` 接线 + 内容进流 + 缺文件/循环给诊断）归 **A2 ②**，两路径口径统一归 **A2 ③**。复现：`run_pipeline_on_source("#include <stdio.h>\n", rules_dir="grammar/c")`；口径注见 `gap-c-preprocessor-scope.md` ⑭ |
| 6 | 分隔符后**行尾**注释跨折行落位漂移（首遍 `first, /* c */` + 换行 + `second;`，次遍 `first,` + 换行 + `second /* c */;`，第三遍起收敛 ⇒ **判据 4 不幂等**） | `_attach_line_end` 把行尾注释挂 `context.current_node`，分隔符后被吞时挂的是**列表容器**、容器 `trailing` 槽渲染在容器末尾。**2026-09-28 定案：不修渲染**（否决"锚点感知 LineSuffix"与"挂刚结束的项节点"），**归入原始路径（raw）还原**（先例 = 宏 `MacroCall._macro_source_text`）。注释从不丢失，症状只是"位置漂移 + 一遍不幂等"；最小复现见 `tests/fuzz/README.md` |
| 7 | 类型名里的指针星号与类型词之间不留空格（`sizeof(char *)` → `sizeof(char*)`、`(char *)q` → `(char*)q`） | 纯排版差异（token 序列不变、语义不变，判据 7 照过）；要改成 `char *` 需同时动两处布局并**重录**三份样本比值，故记为已知偏差 |
| 11 | 初始化列表**尾逗号后的注释**落到列表外：`int a[] = {1, 2, /* c */ }` → `int a[] = {1, 2,} /* c */;`（注释**单份、幂等、产物合法**，只是位置从 `}` 前移到 `}` 后） | 闭括号前没有后续元素可挂行内锚 ⇒ 按"闭括号前注释挂当前节点 `trailing`"渲染（`parser/_production.py::collect_following_comments`），容器 `trailing` 槽渲染在容器末尾（与 #6 同一落点机制）。修法需容器内"尾注释"槽位（`}` 前落地），属引擎注释模型扩展；当前以"不丢、不重、幂等"优先，位置漂移登记在案。 |
| 10 | **引擎潜伏残洞**：行终止注释在 flat / Fill 路径仍可落行中（`group(Concat([Text("a"), LineSuffix(" // n"), Line()]))` → `a // n b`，`b` 会被并进注释；`Fill` 逐项就地冲刷同理） | 与 #9 无关。`_resolve_suffix_union` 只堵"两支 pending 不同"路径（2026-10-19），pending 相等（通常都为空）时仍保留 Union，而 flatten 把 `Line` 渲染成空格。**现有 C/verilog/yaml 布局未用 `fill`/`line_suffix` 原语 ⇒ 未触发**；彻底修法 = `flatten` 不把 `line_ending=True` 的 LineSuffix 文本化（代价：改 flat 刻意行为 + `test_suffix_in_flat_group` 期望）。触发条件：某语言包开始用 `fill`，或在可 flat 的 `line` 里带行尾注释 |

**#8 修复的独立审计**（循环 #30，反例可复跑）：Doc 级构造 **12** 例，**2 例成立**（手工 `Union`
两支各带独有行终止后缀文本 ⇒ flat 独有文本丢失；生产 `group`/`flatten` 把同一 suffix 复制进
两支，22 份真实文档 `both_nonempty = 0` ⇒ 该形态不可达，语义由
`tests/engine/renderer/test_doc_line_suffix.py::TestLineSuffixUnion` 锁 broken 侧）、**10 例不
成立**（flat group / Fill / nested union 与 HEAD 同输出 ⇒ 属既有残洞 #10，非本轮引入）。真实语料
触发面：C 样本 3 / verilog `tests/e2e/samples/real` 18 / yaml 测试字面量 96·101 的 union mismatch
均为 0，仅 C 四构造形态各 1 次。

## 运行时档位：`enabled` 的语义边界

- **入口**：`ConfigRegistry.load_language / load_all / resolve(..., enabled=[...])`
  （`None` = 用包内 `[plugins] enabled`）。显式档位会被登记为该包"当前档位"，故
  `Lexer` 之类隐式消费方无需额外参数即可跟随（缓存键含档位）。
- **判据**：`tests/languages/c/test_c_standard_tiers.py` 的 **27 例参数化 × 4 档矩阵**
  （`enabled=[]` / `["c11"]` / `["c11","c17"]` / `["c11","c17","c23"]`，按**解析成哪个
  节点**判定；复现：`python -m pytest tests/languages/c/test_c_standard_tiers.py --collect-only -q`），
  外加同进程连续切档、`Lexer` 跟随档位、非法 `enabled` 参数与清单里不可解析的插件名
  **fail-fast**。另有 2 条 **keyword-free** 增量用例（`[[属性]]` 基线档也解析）在
  `TestKeywordFreeIncrementsAreNotTierGated`，**不属**该 ×4 矩阵。
- **边界（不是 bug）**：`enabled` 只决定**声明面**（`tpc.toml` 声明合并，含
  `[lexer] token_ext`）；插件的**规则文件与 Python 组件**由 `setup_grammar` →
  `load_all_components(<pack>/plugins)` 加载，**不看** `enabled`。⇒ **不依赖新关键字的
  增量在基线档也解析**（"档位 = 接受域"对它不成立）；补齐前不新增依赖该语义的声明。

## 关联条目

- ROADMAP「SystemVerilog 语言包（远期 backlog）」/「C 语言包」（预处理阶段 4 / 切片 1b）
- `grammar/yaml/`（6/7 的消费方）、`grammar/c/`（接受域 / 档位 / 渲染现状的消费方）
- 门禁：`tools/c_acceptance.py`、`tools/render_coverage.py`、
  `tests/languages/c/test_c_render_fidelity.py`、`tests/languages/c/test_c_standard_tiers.py`
- `docs/references.md`「C 语言文法参照」（外部参照源）

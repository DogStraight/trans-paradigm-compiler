# Gap — 语言包范围与 yaml 边界（规模 / SV / 插件划分 / 增强语法）

- 状态：范围声明（刻意选择）
- 关联：ROADMAP「SystemVerilog 语言包」；`grammar/yaml/`
- 参照：Language server/编译器前端对大型语法的工程组织（Clang 分层）

## 边界是什么

1. **中小语言**（接受）：配置驱动语法是 DSL/子集/自定义扩展的最佳点（c4、
   Verilog 核心）。C++ 规模语法墙不是上下文敏感（解析器经符号表解决
   `a*b` 声明 vs 乘法）——墙是**规则规模与语义深度**（数百 production/模板
   实例化/重载/复杂类型），TOML 配置无法压缩、也不是本工具目标。大语言推荐
   做**精选子集**（Verilog 包本身就是可综合子集，仿真构造移插件）。
2. **配置有学习曲线**（接受）：语法包横跨五类配置面（语法 production/节点
   `$N` 绑定/analyzer 钩子/transform 输出/renderer layout），各有隐式约定。
   二次开发入口：`docs/MODEL_INDEX.md` + `core/component_protocol.md`。
3. **非行为验证器**（接受）：校验良构（语法/结构/命名/跨模块一致），不仿真/
   不综合，不判断硬件正确性——前端/规范执行工具，非正确性证明器。
4. **无 SystemVerilog**（backlog）：包目标 Verilog-2005；SV 构造
   （interface/class/always_ff/assertion/package/UVM）不在当前范围。加 SV =
   **core + plugin 增量**路线项（ROADMAP「SystemVerilog 语言包」），非引擎改动。
5. **Verilog-2005 标准面已齐；可综合核心 vs 仿真/库插件**（接受 + 余量跟踪）：
   主包覆盖可综合子集；仿真/库语法在 `plugins/syntax/`（gates 26/UDP/
   specify（含 defparam）/configs/nettypes/attributes + sim（initial/fork/
   过程 assign 等））。剩余余量（darkriscv 嵌套条件编译位置精度等）与
   references.md 跟踪。
6. **yaml 缩进推断锁**（接受 + 摩擦）：`[indent] level="auto"` 首结构行锁定
   单位；混单位文件锁定后错解析；渲染器经 AST-root `_indent_unit` 戳重缩进到
   锁定单位——块标量逐字内容仅在源单单位时保持对齐。
7. **yaml plain 标量配置宽松近似**（摩擦）：`[plain]` 模式（字符类 +
   `stop_space_after`/`no_space_after_tokens`/`flow_terminators`）覆盖真实
   配置值形态（`${{}}`/URL/多词/CJK/词内 `,{}[]`）——偏离 YAML 1.2 严格
   plain 规则。剩余 gap：数字引导多点多值（`1.2.3` 拆分，number 分支赢）、
   无 tab 分隔词、值不跨行、带转义引号不支持。
8. **增强语法 linted 非豁免**（事实）：前置 linter 共享 parser 规则表（含插件
   语法），合法 `type`/`type.role`/`impl` 构造过 lint 门禁；`no_lint=True`
   是逃生门但不需要。

## 为什么是范围（影响面）

1/3/4/5 是产品定位（面向可配置规范执行的 DSL/子集工具），做大语言/SV/仿真是
路线项非缺陷；yaml 6/7 是 yaml 包以"配置宽松"换"覆盖真实值形态"的取舍；
8 澄清增强语法不需逃生门（防误导）。

## 成熟解法参照（见贤思齐）

- SV/大语言支持：Clang 式分层（core 语法 + 插件增量）是 ROADMAP 方向，不重新
  发明单体内核。
- yaml plain 严格性：YAML 1.2 规范是裁判；tpc 取"配置宽松"实为覆盖真实配置
  形态的工程取舍（见 `grammar/yaml/` 现有注释）。

## 可实现性

- 4：ROADMAP「SystemVerilog 语言包」（远期 backlog）——core+plugin 增量路径。
- 5：剩余余量（语法/位置精度）按需处理。
- 6/7：yaml 包专项（如需）：7 的 `1.2.3` 拆分需 plain 分支优先级重排（number
  vs plain 消歧）；6 的混单位是捕获层约定，改动需 yaml 语料门禁。
- 1/2/3/8：不改（范围/文档事实）。

## 关联条目

- ROADMAP「SystemVerilog 语言包（远期 backlog）」
- `grammar/yaml/`（6/7 的消费方）


## C 语言包：分层草案与 C99 接受域清单（0.1.3 WS1 阶段 0，2026-09-25）

> 形态**不需要再议**（ROADMAP 2026-08-29 定调「标准插件族」）：`grammar/c/` 核心基线
> ≈ c99 语法面，c11/c17/c23 各为增量插件、`requires` 链表达标准包含关系。
> 本节是**阶段 0 的定界产物**（首轮草案 v0）——逐条在阶段 1–3 落地时复核并转成
> 接受域断言；`c4` 保持不动（它的定位是"从零搭语言模板 + 语言无关性验证"）。

### 规模参照（实测）

| 包 | TOML | Python | 说明 |
|---|---|---|---|
| `grammar/c4` | 11 文件 / **821 行** | 1 | Tiny C 子集（全局变量 / 函数定义 / enum / 表达式 / 语句），是 C 核心基线的**起点参照** |
| `grammar/verilog` | 80 文件 / 8238 行 | 34 | 分层与插件划分的**形态参照**（`00_blocks`/`01_module`/`02_declarations`/`03_always`/`04_statements` + `plugins/syntax/*`） |

### `grammar/c/` 分层草案（命名参照 verilog 的数字前缀法）

```
grammar/c/
├── tpc.toml                 # [engine] uses / [lexer] / [parser] / [pipeline]（照 c4 入口形态）
├── base/
│   ├── _token.toml          # 关键字表（C99 §6.4.1）、标点、bracket 配对
│   ├── _lexer.toml          # token 类别 + 运算符优先级/结合性表
│   └── _number.toml         # 整数字面量（进制/后缀 U L LL）+ 浮点 + 字符/字符串转义
├── 00_translation_unit.toml # 翻译单元 = 外部声明序列（根块规则）
├── 01_declarations.toml     # 声明与声明符：基础类型、限定符、存储类、多级指针、
│                            #   数组、函数声明符（C 的**声明符递归**是核心难点）
├── 02_types.toml            # struct/union/enum（含位域）、typedef、标签命名空间
├── 03_statements.toml       # compound/if/switch/while/do/for/goto/label/break/continue/return
├── 04_expressions.toml      # 全部优先级与结合性（照 c4 的表达式规则扩全）
└── plugins/                 # 语言包插件（按 verilog 的分族方式）
    ├── checks/              # 诊断族（命名/类型/未使用/…；随语义层推进）
    ├── elaboration/         # 精化项（C 的"事实"：译注单元符号、结构体布局、常量折叠…）
    └── c11/ c17/ c23/       # 增量标准插件（阶段 4 之后；`requires` 链表达包含关系）
```

**为什么不建 `plugins/syntax/` 子层**：verilog 的 `plugins/syntax/*` 是**聚类**（原插件名不变、
引用兼容的重组），C 包从零起步没有历史聚类债，核心语法直接放包根的数字前缀文件即可；
等增量标准插件（c11+）出现时，它们各自是一个插件目录，天然就是"增量即插件"。

### C99 接受域清单（首轮，逐条标注）

**判据（每族都要有）**：正样本解析通过（进 AST）+ 负样本被拒（linter/parser 报错），
两向都要断言——只有正样本会漏掉"语法过宽"。

**盘点工具**：`python tools/c_acceptance.py`（27 条构造逐条试解析，报"进 AST / 空 AST /
词法抛错"）——**空洞是无声的**：不属任何语句入口 FIRST 集的构造会被整体跳过而不报错，
只跑测试套件看不出还差哪一族。当前 **接受 20 / 空洞 7**（空洞：`.5`、字符串内转义引号、
逗号运算符、强制转换、复合字面量、预处理两项；**链式后缀 `a.b.c` / `f(x)[i]` 已于
2026-09-25 从空洞转为接受**）。

| 族 | 条目 | 阶段 | 备注 |
|---|---|---|---|
| 词法 | 关键字（C99 全 37 个）、标点/运算符、注释（`/* */` 与 `//`） | 1 | `//` 是 C99 新增（C89 无）→ 归核心基线需明确 |
| 词法 | 整数常量（十进制/八进制/十六进制 + `U`/`L`/`LL` 后缀）、浮点（含指数/后缀）、字符与字符串字面量（含转义表） | 1 | 字面量形态多，**逐形态正负样本** |
| 词法 | 标识符与关键字冲突、行拼接（`\` 续行） | 1 | 续行属预处理面（阶段 4 复核） |
| 声明 | 基础类型（`void/char/short/int/long/long long/float/double/_Bool/_Complex`）+ 符号/无符号 | 1 | `long long`/`_Bool`/`_Complex` 是 C99 新增 |
| 声明 | 声明符递归：多级指针、数组（含 `[]` 不定长）、函数声明符、函数指针、返回函数指针 | 1–2 | **C 语法最难点**；用 c4 的声明符规则起步 |
| 声明 | 存储类（`typedef/extern/static/auto/register`）、类型限定符（`const/volatile/restrict`）与**函数说明符**（`inline`，C99 §6.7.4） | 2 | `restrict` 仅指针、`inline` 仅函数——都是**约束**（语义层），语法层宽进 |
| 声明 | **实测补洞（2026-09-25）**：`inline` / `_Complex` 此前整条解析失败（`FuncSpec` 规则缺失、`SimpleType` 未含 `_Complex`）→ 已补，见 `tests/languages/c/test_c_declarations.py::TestC99Specifiers` | — | 同批实测仍**不支持**的：前导点浮点（`.5`）、字符串内转义引号、强制转换 `(T)x`、逗号运算符、复合字面量 |
| 表达式 | **链式后缀补洞（2026-09-25）**：`a.b.c` / `f(x)[i]` / `p->a[i]` / `(*fp)(x)` 此前不支持（三个后缀规则都是单级）→ 改为 `PostfixExpr{base, suffixes}`（原子 + 后缀+，同 clang 手写路径的"leading part + 后缀循环"），见 `tests/languages/c/test_c_postfix.py` 28 例 | 3 | 参照见 `docs/references.md`「C 语言文法参照」（ISO C99 §6.5.2 + clang + tree-sitter-c） |
| 词法 | **后缀实测补洞（2026-09-25）**：整型后缀（`42u`/`1ULL`/`0x1Fu`）与浮点后缀（`1.5f`/`1e3L`）此前被切成"数字 + 标识符" → 已补（`[[number.based]] suffix` 键，DFA 之后的声明式尾段），门禁 `tests/engine/lexer/test_number_suffix.py` | 1 | 组合合法性（`1UL` 合法 / `1ff` 非法）**不在词法层判定**——C 的 pp-number 本就宽进（tree-sitter-c 同样按字符类宽进），约束归语义层 |
| 声明 | 初始化器（标量/聚合/指示符 `.field=`、`[i]=`） | 2 | 指示符是 C99 新增 |
| 类型 | `struct`/`union`（含**位域**）、`enum`、标签命名空间（tag vs ordinary） | 2 | 命名空间分离属**语义**层（先语法后语义） |
| 语句 | compound / 表达式语句 / 空语句 / `if`(含 `else`) / `switch`(含 `case`/`default`) / `while` / `do` / `for`(含 C99 声明式 `for(int i…)`) / `goto` / 标号 / `break` / `continue` / `return` | 3 | `for` 声明式是 C99 新增（归核心基线需明确） |
| 表达式 | 全部优先级与结合性、赋值（含 `+= -= *= /= %= <<= >>= &= ^= \|=`）、条件 `?:`、逗号、`sizeof`（含 `sizeof(T)`）、类型转换、下标、成员 `.`/`->`、调用、一元/后缀（`++/--`） | 3 | 用 c4 表达式规则扩全；`sizeof(T)` 需类型名可解析 |
| 复合字面量 | `(T){…}`（C99 新增） | 3 | 与"cast + 初始化器"消歧 |
| 变长数组 | VLA（C99 新增） | 延后 | 与语义/求值强耦合，先记缺口 |
| 函数 | 原型（含 `void` 参数列表、`...` 变参）与定义 | 2 | `...` 是 C99 标准化的变参写法 |
| 预处理 | `#include` / `#define`（对象宏、函数宏、变参宏、`#`/`##`）/ `#if` 表达式 / `#ifdef`/`#ifndef`/`#elif` / `#line`/`#error`/`#pragma` / 预定义宏 | **阶段 4（单独立项）** | 引擎前置见 ROADMAP「注入机制补『改』路径」；条件编译反向映射精度是最大风险 |
| 明确不做（取舍） | 独立编译/链接、优化、完整类型推导与求值（语义层是渐进项）、实现定义行为（位宽/对齐）、K&R 老式函数定义 | — | 各自在缺口档或 ROADMAP 有归属；不做的原因：超出一致性检查工具链的定位 |

### 阶段 0 结论（进阶段 1 的前置）

1. **载体**：新建 `grammar/c/`，`c4` 不动（决策已定，2026-09-25）。
2. **首个可验收切片**：阶段 1 = 词法 + 声明的**类型与声明符**两族出正负样本（不是"全部词法"）
   ——因为声明符递归是后续一切的地基，其形态决定 AST 形状。
3. **标准增量归位待定项**：`//` 注释、`long long`、`_Bool`、`for` 声明式、指示符初始化、
   复合字面量、变参 `...` **都是 C99 相对 C89 的新增**。"c99 核心基线"若含它们，
   则"C89 等效"就不可表达——需在阶段 1 决定是否再切一层 `c89` 基线（**记为首个待决项**，
   不阻塞阶段 1 开工）。

### 阶段 1 现状（2026-09-25）

**已落地**（`grammar/c/`）：`tpc.toml`（能力清单 + lexer/parser 入口）、`base/_token.toml`
（C99 标点/多字符运算符/括号/字面量/标识符；`#` **不**作注释）、`base/_lexer.toml`
（`/* */` + `//`）、`base/_number.toml`（十/八/十六进制）、`token.toml`（C99 全部 37
关键字）、`00_expressions.toml`（叶子 `Identifier`）、`01_declarations.toml`（翻译单元 +
声明 + 说明符序列 + 声明符：多级指针 / 数组 / 函数后缀 / 括号声明符 / 参数表）。

**验收**：`tests/languages/c/test_c_declarations.py` **20 passed**（正样本 15：声明进 AST
且声明符结构可查，含函数指针递归 `int (*fp)(int);`、逗号列表、多词说明符、
`typedef`；负样本 5：缺声明符 / 悬空指针 / 括号不闭合 / 参数表尾逗号 / 缺分号）。

**阶段 2a 已落地**（`grammar/c/02_types.toml`）：`struct/union` 说明符（带标签 / 匿名，
成员体可选）、`enum`（带标签 / 匿名，枚举项含 `= 数字字面量`）、成员声明、
**typedef 名作类型**（`myint x;`）。验收 `tests/languages/c/test_c_types.py` 12 例
（含 `typedef struct { … } T;`、匿名 enum、带值枚举）。

**阶段 2a 的两条实测坑（已修，写包者注意）**：

1. **token 键重复定义**：`_token.toml` 里 `equal = "="` 与 `assign = "="` 同串两键，
   词法取**后者** → 所有引用 `symbol.base.equal` 的规则**静默失配**（枚举值 `= 2`
   报错方向完全看不出是命名问题）。加 token 时要查重（同串多键 = 静默覆盖）。
2. **字面量正则过度转义**：`[literal] number` 写成 TOML `"\\\\d+"`（解码为 `\\d+`）
   而非 `"\\d+"`（解码为 `\d+`）→ 数字**从不**被识别为 `literal.number`；因为
   数组长度与枚举值当时都写成可选，症状是"静默为空"而非报错。**可选位点会掩盖
   词法失效**——加可选捕获时要配一条"非空"断言。

**仍留阶段 3/词法**：成员/变量初始化器（含指示符 `.f=`/`[i]=`）、
数组长度用常量表达式（当前只接受数字字面量）、函数体与语句、表达式族
（运算符表 / 一元二元后缀 / cast / sizeof）、字符/字符串转义表。
**已知写法取舍**：typedef 名**只允许出现在首个说明符位置**（`unsigned myint x;` 暂不支持）
——若允许它进说明符重复项，贪婪匹配会把声明符名当类型名吃掉（实测）。

**包作者须知（本轮实测教训，写包必看）**：

1. **`Identifier` 这类叶子规则要语言包自己定义**——引擎不内置（c4 / yaml / verilog
   各自定义一份）。漏定义时 `@Identifier` 引用**匹配为空**，症状是"parser 报
   `match_length 0`、linter 报 `expected ';' got 'id'`"，**看起来像规则形态问题**；
   本轮为此先后证伪了五个形态假设（带括号 token 组 / 说明符层级 / 后缀规则组 /
   首元素带量词组 / `@Rule|@Rule` 交替），真因只是规则缺失。
   → 加新包时先对齐一份"引擎不内置、必须自带"的规则清单。
2. **linter 近似边界**：语句发现按"首 token 能起始某条语句规则"挑候选；不属于任何
   语句入口 FIRST 集的顶层构造会被**整体跳过，既不解析也不诊断**（实测
   `struct point p;` 在阶段 1 即如此，而 `int x` 缺分号会报错）。阶段 2 加入
   struct/union/enum 后该行为自然改变——不要把它当期望行为钉住。


### 前导点浮点 `.5`（2026-09-25）

浮点本身已可用（`3.14` / `1e10` / `1.e5` / **`0.5`** 都是单个 `literal.number`——最后
一个靠把 `c_dec` 的 `size.digits` 从 `nonzero` 放开为 `any`，让内置浮点链作用到
0 开头的小数）。但 **`.5`**（C99 允许的"小数点开头"形态）表达不了：数字形态由
`size`（前缀数字）/ `base_prefix` 描述，**没有"以点开头"的位置**，故 `.5` 被切成
`.` + `5`。

⚠ 同族的**整型后缀**（`42u` / `1ULL` / `0x1Fu` / `1.5f`）已于同日修好：
`[[number.based]]` 新增 `suffix = { chars, max }` 键（**DFA 之后的声明式尾段**，由
`number_runner` 在接受位之后消费——不做成 DFA 转移的原因见 `lexer/number_gen.py`
的键说明：全局字符类别里 `f`/`F` 已是十六进制 digit，按类别加边会与 hex 值自环撞键）。
对应用例已转正向（`test_c_lexer.py::TestNumberForms`），引擎侧门禁见
`tests/engine/lexer/test_number_suffix.py`（含 `0x1FF` 撞键判据）。


### 字符串内的转义引号（2026-09-25）

`"a\"b"`（字符串里含转义引号）捕获**提前终止**：`[string] delimiters` 的 delim 模式按
"下一个定界符"结束，**不识别反斜杠转义**（与 `docs/gaps/gap-lexer-capture-boundaries.md`
记录的捕获边界同类）。真实代码里 `printf("say \"hi\"")` 很常见，故这条**有实际影响**。

上面两条缺口（前导点浮点 / 字符串内转义引号）都由
`tests/languages/c/test_c_lexer.py::TestRecordedLexicalGaps` 反向守：修好后对应用例
会失败并提醒同步本档。


## 增量插件形态实测：**启用入口 = `[plugins] enabled`**（2026-09-25，含一处自我更正）

C 包首个标准增量插件 `grammar/c/plugins/c11/` 已落地（`_Static_assert` + C11 六个新
关键字的词法扩展）。实测三点：

1. **增量确实住在插件里、不碰基座**：`StaticAssertDecl` 只出现在插件目录，
   核心基线文件（`00_*`/`01_*`/`02_*`/`03_*`）不含它——"加标准 = 加插件"成立，
   已由 `tests/languages/c/test_c_increment_plugin.py` 按**扫描文件**的方式守住。
2. `<pack>/plugins/` 是**随包自动发现**的：`setup_grammar(rules_dir, register, ext_dirs)`
   没有 enabled 参数；`load_language(pack, plugins_dir=…)` 传与不传都加载到同一份。
3. 语言包 `tpc.toml` 的 `[plugins] enabled` 是**打包/分发面**清单，不是运行时开关。

**缺口**：ROADMAP 定调的"`enabled` 组合等效某个标准"目前**无法在一次运行里表达**
（只能在打包面或 pack 副本上切换两档）。要做"语法接受域断言（对标各标准语法规范）"
（ROADMAP C 包条目里的验收项），就需要一个**运行时可选的插件组合**入口。

**候选**：给 `load_language` / `setup_grammar` 一个显式的 `enabled` 覆盖（或 `ext_dirs`
收敛成"插件组合"声明），语义与打包面的 `[plugins] enabled` 统一到一处清单——
顺带把"两处各有一份启用清单"这个潜在散点一并消除。判据：同一 pack、同一次进程内，
两档组合各自可加载并解析出不同规则表；且 `requires` 链（c17→c11→核心）在缺前置时
**响亮失败**（组件依赖排序已有该行为，`core/plugin_loader.py` 的 `META_REQUIRES`）。


### 精化（同日实测）：规则加载与词法扩展走**两条不同**路径

- **规则文件**（`[grammar] files`）：`setup_grammar(<pack>, register)` **自动扫描**
  `<pack>/plugins/`，故规则会进来（`StaticAssertDecl` 在规则表里 ✓）。
- **词法扩展**（`[lexer] token_ext`）：经 `ConfigRegistry.load_language(pack,
  plugins_dir=…)` 与 `setup_grammar(..., ext_dirs=[…/plugins])` **都未生效**——
  `_Static_assert` 仍是标识符，于是 `_Static_assert(1, "x");` 被解析成 `ExprStmt`
  （函数调用），插件规则永远匹配不到。verilog 侧的可复现用法是把 `ext_dirs` 传给
  **`LinterScanner(rules_dir=…, ext_dirs=["…/plugins"])`**（`tests/languages/verilog/
  test_2005_batch2.py:115`）。

**结论**：C 包首个增量插件目前是"**规则层已增量、词法层未接通**"的半成品。
下一步（按"先成因后动手"）：读 `Lexer` / `LinterScanner` 对 `ext_dirs` 的消费路径
（`core.define.DEFAULT_EXT_DIRS` 的派生链是入口），确认语言包插件目录该以什么身份
进入词法扩展；接通后把 `test_construct_not_yet_parsed_as_plugin_node` 改为断言
`["StaticAssertDecl"]`。**不要**改断言迁就现状。


### ⚠ 自我更正（同轮）：启用入口**存在**，就在语言包 `[plugins] enabled`

上一版本档写"本仓没有运行时的启用/停用开关、`[plugins] enabled` 只是打包面清单"——
**该结论是错的**，实测反证：

- C 包加 `[plugins] enabled = ["c11"]` **之前**：`_Static_assert` 被分词为 `id`，
  `_Static_assert(1, "x");` 解析成 `ExprStmt`（函数调用），插件规则永不匹配；
- 加**之后**：`_Static_assert` 即为 `keyword._Static_assert`，解析成
  `StaticAssertDecl` ✓；
- 对照证据：verilog 的 `nand`（`plugins/syntax/gates/_token_ext.toml` 声明）在 verilog
  下**无需任何 `ext_dirs`** 就是关键字——因为 verilog 的 `enabled` 列了 `gates`；
- `Lexer(..., ext_dirs=…)` / `setup_grammar(..., ext_dirs=…)` 传插件的**实测都无效**
  （三种粒度试过），真正生效的是 `load_language` 时按 `enabled` 合并声明。

**由此**：ROADMAP 的"`enabled` 组合等效某个标准"**在运行时即可表达**（改这份清单）。
仅剩一处待办：**同一次进程内切两档**（基线档 / c11 档）需要重载配置或 pack 副本——
若要做"各标准接受域断言"的对照测试，需要一个显式的组合覆盖入口（`enabled` 覆盖参数），
或按档位准备 pack 副本。这是**易用性**问题，不再是**能力缺失**。


## C 包渲染/保真面现状（原文打印闭环已通，2026-09-25）

**闭环已成立**（`tests/languages/c/test_c_render_fidelity.py`，29 例全绿，3 个样本
`ring_buffer.h` / `ring_buffer.c` / `edge_comments.c`）：源文本 → tokenize → parse →
render → 与源比对，七条判据：

1. **非空**（缺渲染配置时引擎**静默输出空串**，只断言"没报错"抓不到——这正是本包
   最初 1/70 覆盖率的真实症状）；
2. **行数覆盖** ≥ 源有效行 80%（防"只渲染出一部分"）；
3. **`difflib` 比值** ≥ 0.80（容忍格式化差异，抓内容丢失）；
4. **幂等**（渲染结果再过一遍管线，逐字相同）；
5. **注释清单**：源里**每一条**注释正文都必须在输出里出现（比抽样锚点强，能抓
   "某一条被静默吞掉"）；
6. **首注释源序**：同一位置领到的多条独占行注释，渲染顺序与源一致（只守 4 或只守
   6 时，"倒序但恰好往返一致"的实现仍可能漏过）；
7. **显著 token 序列逐项相同**（`(type, content)` 序列，trivia 与注释除外）——
   **内容级对拍**：重排只许动空白、不许动 token 的序。比 difflib 强得多：
   `i++` → `++i` 只差 3 个字符（比值 0.99+），difflib 与行数判据**都抓不到**，
   序列判据一眼看出；语言无关（两侧都用包自己的 lexer）。

| 项 | 布局补齐前 | 现在 |
|---|---|---|
| `tools/render_coverage.py grammar/c` | 70 条规则 / 1 有渲染配置（1%） | **80 条 / 80（100%）** |
| `samples/ring_buffer.h` ratio / 有效行 | 0.0000 / 0（渲染为空串） | **0.9926** / 33（源 33） |
| `samples/ring_buffer.c` ratio / 有效行 | 0.0000 / 0 | **0.9925** / 117（源 117） |
| `samples/edge_comments.c` ratio / 有效行 | — | **0.9822** / 29（源 31） |

⚠ 三处**再记录**（说明原因，不是调阈值凑绿）：① `ring_buffer.c` 0.9780 → 0.9867 是
`i++` 修好后的直接结果（6 处 `i++`/`p++` 不再被写成 `++i`/`++p`）；② 升到 0.9822～0.9926
是本包补上 `[renderer] style`（**页宽 80 列**，C 惯例；此前用引擎默认 40 列，把正常
声明/调用折成多行）的结果；③ `ring_buffer.c` 再升到 **0.9925 且有效行 117 = 源 117**
是**链式后缀支持后样本长回自然写法**的结果（`r->items[i].key` 这类三级链；
见 `TODO.md` 阶段 3 条目与 `docs/references.md`「C 语言文法参照」）。

⚠ 本闭环测的是**默认 `full` 级**（与 verilog 参考 `tests/e2e/test_real_fidelity.py`
同口径）；引擎另有 `keep_blank` 级（按源结构位置回插空行，`renderer/fidelity.py`），
在本包三样本上实测比值 0.9857～0.9979、且幂等、非空行与 `full` 完全一致——空行是
`full` 级剩余差异的主要来源。该级语义由引擎侧门禁覆盖（`tests/engine/renderer/
test_fidelity.py`），本包不再复制门禁。

**为什么"覆盖率 100%"不是凑数**：分母 70 → 80 是因为补了 `Comment`（真规则，新增
`grammar/c/04_comments.toml`）、pratt 产物 `BinaryOp`/`UnaryOp`/`TernaryOp`、以及 6 个
`bracket.*` token 节点——后两类**不补布局就静默丢内容**（实测 `a[i]` 渲染成 `ai`）。

**已修的真实内容缺陷（不是格式问题）**：
- **后缀自增/自减被渲成前缀**（`i++` → `++i`）：pratt 产物 `UnaryOp` 用同一节点名承载
  前缀/后缀（`position` 字段区分），而布局原语此前无"按属性值换序"能力、只能二选一
  ——token 齐全但**顺序反了**（C 里两者语义不同）。新增 `when` 属性分发布局原语后修好
  （`renderer/primitives/when.py`），并由**判据 7（token 序列）**兜底。
- `StorageClass`/`TypeQualifier`/`SimpleType`/`StructOrUnion` 原先**一个字段都没有** →
  关键字文本完全不在 AST 里；`SpecRest` 无子节点 → `typedef struct X{…} Y;` 的**整个 struct 体**
  不在 AST 里。补最小 node 绑定后回填。
- 列表项前的独占行注释**整条丢失**（`enum e { // c` + 首项）：首注释被领到行首规则的
  **最内层**节点（项以标识符开头时是项内的 `Identifier`），项级取用够不到 → 渲染静默
  丢弃。取用端改为沿项**首脊线**下钻（`renderer/primitives/join.py::_hoist_head_comments`）。
- 多条首注释**顺序倒置**（`parser/_production.py::_insert_gap_comments` 按行升序遍历却
  逐条 `insert(0, …)`）：渲染出"后一行在前"，二次渲染又回正 ⇒ 不幂等。
- 硬拼列表（`join=""`，如声明符后缀链）首项即注释时**注释粘在代码上**：`//` 注释随即
  吞掉后续片段（实测 `int f(\n// c\nint a);` → `int f// c` + 换行 + `(int a);`，二次渲染
  整段被吃进注释 ⇒ **输出非法 C**）。

**注释三级形态（设计意图）的落地位置**（引擎既有机制，本轮补齐取用端）：

| 级 | 载体 | 实测 |
|---|---|---|
| line（`//`，独占行） | `Comment` **节点**（list-spec 消费的 repeat 上浮为迭代项，容器首元素前由 claim 领为子节点） | `enum` / struct 体 / 语句间 / 顶层均保住 |
| block（`/* … */`，独占行） | 同上（`Comment` 节点） | 保住 |
| inline（行中，前后同行有代码） | 节点**元信息**槽 `_comment_slots`（`inline_after` 锚 token / `inline` / `trailing`），不另立节点 | `int a /* c */, b` / `f(a /* c */, b)` 均保住 |

**已知偏差（逐条，均不丢 token）**：

| # | 现象 | 原因 / 现状 |
|---|---|---|
| 1 | `case` 体不额外缩进、标号缩进与源不同（`done:` 被缩进、`case` 体被反缩一级） | `CaseLabel`/`LabelStmt` 是独立语句规则（C99 语法里 label 只拥有**一条**语句，`case 0: a; b;` 的 `b` 本就不属于 label），渲染端 body 对所有子节点同等缩进 → 要修需"标签后同级后续子节点多缩进一级"的渲染能力（engine 侧新能力，非语言包） |
| 2 | `for (;;)` → `for (; ; )` | 三段用字面 `"; "` 拼以保 `for (int i = 0; …)` 的空格；空段多出空格，合法 C |
| 3 | 注释落在**括号内首元素前**时，位置被提到括号外（`int f(\n// c\nint a)` → 注释落在 `f` 与 `(int a)` 之间） | 解析端 `_lift_gap_comments` 的项间窗口上界用"迭代**末行**"，故迭代 token 跨度**内部**的注释也被当"该项之前"上浮。**收紧窗口已验证不可行**：上界改用迭代**首行**后 6 处门禁变红（端口表/具名端口/声明符表/case 项/真实语料无丢注释）——窗口的末行容差是给"注释在本次迭代匹配中被吞、语义上属该项之前"的形态留的。要修需把归属判据从行号窗口改为**迭代 token 跨度**（跨度内 → 归跨度内部消费方） |
| 4 | 注释项前多一个行尾空格（`int ` + 换行） | 列表折叠后注释项独占行，父布局的分隔空格留在行尾；纯空白差异（输出合法、幂等） |
| 5 | `#include` 在**词法层直接 ValueError**（`Unexpected token: #`） | `#` 未进符号表；预处理属阶段 4（先于本次改动存在） |
| 6 | 分隔符后的**行尾**注释在跨折行时落位漂移（首渲染 `first, /* c */` + 换行 + `second;`，次渲染 `first,` + 换行 + `second /* c */;`，第三遍起收敛 ⇒ **判据 4 不幂等**） | `_attach_line_end` 把行尾注释挂 `context.current_node`——分隔符后的注释在 repeat 组匹配中被吞，此刻是**列表容器**，容器 `trailing` 槽渲染在容器**末尾**（越过后续项）；同一注释在分隔符**之前**时挂的是**项**节点 trailing（渲染在该行尾）。挂点取决于"分隔符与下一项是否同行" ⇒ 折行即漂移。候选方向与风险见 `TODO.md`「保真度渲染：分隔符后行尾注释随折行漂移」；样本 `edge_comments.c` 用不折行的短注释绕开该形态 |

**未做（下一步）**：
1. 上面 3/6 两处**解析侧**改动（注释归属的 token 跨度判据、行尾注释挂点名）。
2. 外部 oracle（`clang-format`）对拍——**token 序列对拍已由判据 7 覆盖**（内容级、
   语言无关），"与外部格式化器的排版对拍"仍未做。

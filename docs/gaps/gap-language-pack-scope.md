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

| 族 | 条目 | 阶段 | 备注 |
|---|---|---|---|
| 词法 | 关键字（C99 全 37 个）、标点/运算符、注释（`/* */` 与 `//`） | 1 | `//` 是 C99 新增（C89 无）→ 归核心基线需明确 |
| 词法 | 整数常量（十进制/八进制/十六进制 + `U`/`L`/`LL` 后缀）、浮点（含指数/后缀）、字符与字符串字面量（含转义表） | 1 | 字面量形态多，**逐形态正负样本** |
| 词法 | 标识符与关键字冲突、行拼接（`\` 续行） | 1 | 续行属预处理面（阶段 4 复核） |
| 声明 | 基础类型（`void/char/short/int/long/long long/float/double/_Bool`）+ 符号/无符号 | 1 | `long long`/`_Bool` 是 C99 新增 |
| 声明 | 声明符递归：多级指针、数组（含 `[]` 不定长）、函数声明符、函数指针、返回函数指针 | 1–2 | **C 语法最难点**；用 c4 的声明符规则起步 |
| 声明 | 存储类（`typedef/extern/static/auto/register`）与类型限定符（`const/volatile/restrict`） | 2 | `restrict` 仅指针（C99） |
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

**仍留阶段 2b/3**：位域 `int x : 3`、成员/变量初始化器（含指示符 `.f=`/`[i]=`）、
数组长度用常量表达式（当前只接受数字字面量）、函数体与语句、表达式族
（运算符表 / 一元二元后缀 / cast / sizeof）、整型后缀与浮点字面量、字符/字符串转义表。
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

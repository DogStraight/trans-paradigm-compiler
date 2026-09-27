# grammar/c — C 语言包（核心基线 ≈ C99 语法面 + 标准增量插件族）

> 主体语言包之一。形态定调见 `ROADMAP.md`「C 语言包」：**核心基线 + 标准增量插件**，
> c11 / c17 / c23 各为一个插件目录，`requires` 链表达标准包含关系——
> 「启用某个组合 = 等效某个标准的语法面」，**零引擎新机制**。
> 分层草案与 C99 接受域清单（27 条逐条标注）见
> `docs/gaps/gap-language-pack-scope.md`「C 语言包」节；外部参照见
> `docs/references.md`「C 语言文法参照」。

## 现状（0.1.3 交付面）

**接受面：`python tools/c_acceptance.py` → 接受 26 / 空洞 2（共 28 条）**：
`#include` / `#define`（预处理属阶段 4，单独立项）。

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
- **标准增量插件**：`c11` / `c17` / `c23` 三档齐备（见下「标准档位」）。

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
| 预处理（`#include` / `#define` / `#if` / `#` / `##` / 变参宏） | 阶段 4，单独立项（引擎前置见 ROADMAP「注入机制补『改』路径」） |
| typedef 名起头的强制转换（`(myint)x`） | 语义层切片 1b（需符号表 / 作用域 / 声明顺序），草案见 ROADMAP |
| 逐声明符位宽（`int a : 3, b : 4;`） | 已知边界：包内宽度绑在整个成员声明后；标准里位宽属声明符（形态改动） |
| VLA、`_Alignof`、`_Generic` 等 | 见缺口档接受域清单逐条标注 |
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
├── 02_types.toml            # struct/union/enum、成员声明与位域、typedef 名作类型
├── 03_statements.toml       # 语句族与控制流（整表达式位点引 @FullExpr）
├── 04_comments.toml         # Comment 规则（渲染保真需要它是真节点）
└── plugins/
    ├── c11/                 # _Static_assert + C11 新关键字词法扩展
    ├── c17/                 # 无语法文件，只声明 requires = ["c11"]（缺陷修正版）
    └── c23/                 # 小写 static_assert + C23 新关键字词法扩展（requires c17）
```

## 标准档位：启用组合 = 等效某个标准

- **默认**（`tpc.toml` 的 `[plugins] enabled`）= 核心基线 ≈ C99 语法面。
  `enabled = ["c11", "c17", "c23"]` 即 c23 全档；只列 `["c11"]` 即 C11 档。
- **包含关系在加载期可执行**：组件级 `requires`（c23→c17→c11→核心基线）——
  只启用 c17 而不启用 c11 会**响亮失败**，不会静默少加载。
- ⚠ **未声明关键字 ≠ 拒绝**：某档下未声明为关键字的词仍是合法标识符
  （词法完整、语法按已落地子集引用）——这是判据，不是缺口。
- ⚠ **档位对照当前靠 pack 副本**：引擎级 `enabled` 覆盖参数（同一次进程内切档）
  **尚未落地**——按逐处清单实施后档位未按预期切换（两处缓存键是静默失效点），
  未经验证的改动已全部回退；逐处清单与陷阱见 `TODO.md`。三档对照测试
  （`tests/languages/c/test_c_standard_tiers.py`）在 pack 副本上成立。
- **需要"改"核心规则的那类增量未做**（`typeof` / `constexpr` / `[[属性]]` /
  `nullptr`）：它们要往既有规则的交替里塞分支，而现役 `grammar_inject` 只做
  production 的字符串子串补丁（且软失败）——具体待办见 ROADMAP
  「注入机制补『改』路径」。原因写在 `plugins/c23/tpc.toml` 头注。

## 渲染保真（原文打印）

闭环在 `tests/languages/c/test_c_render_fidelity.py`（3 样本 `ring_buffer.h` /
`ring_buffer.c` / `edge_comments.c`），七条判据：非空 / 行数覆盖 ≥ 80% /
`difflib` ≥ 0.80 / 幂等 / **注释清单**（源里每条注释正文必须出现）/
**首注释源序** / **显著 token 序列逐项相同**（内容级对拍，重排只许动空白）。

实测 ratio：`ring_buffer.h` 0.9926（33/33 行）、`ring_buffer.c` 0.9925（119/119）、
`edge_comments.c` 0.9822。**已知偏差逐条记在缺口档**（`case`/标号缩进、
`for (;;)` → `for (; ; )`、注释落在括号内首元素前的位置、分隔符后行尾注释随折行
漂移）——都是不丢 token 的排版差异，**不在这里重复登记**：口径与成因见
`docs/gaps/gap-language-pack-scope.md`「C 包渲染/保真面现状」表。

补布局前先跑 `python tools/render_coverage.py grammar/c`：**引擎对无渲染配置的规则
静默输出空串**，缺布局是无声的保真度损失（本包最初 70 条规则只有 1 条有配置）。

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
   `items`、按源序渲染。改参数表/列表类规则后**都要跑一次渲染对拍**。
7. **块语句"建成块规则"还是"建成普通语句"，先看包有没有自己的语句序**：c4 的
   `BlockStmt` 是块规则（`is_block = true`，body 由 `parse_block_body` 循环产出，
   renderer 用 `role = "flatten"`），linter 因而拿到块体（`_discover_block` /
   `_block_body`），块内每条坏语句各报一条；本包的同位规则 `CompoundStmt` 是普通语句
   （`@Stmt*` 由父 checker 内联匹配），块内多个错误只报一条。**但改成块规则不是免费
   的**：块体语句随即改走**引擎的规则选择器序**（`RuleSelector` 按规则装载序排候选），
   而本包刻意用 `Stmt` 的有序交替表达"`@ExprStmt` 先于 `@Declaration`"——实测改成块
   规则后 `void f(void) { x; }` 的体内语句会从 `ExprStmt` 变成 `Declaration`。
   故这条取舍的先决条件是"包能声明块体语句的候选顺序"（包侧无此表达面）。见
   `TODO.md`「C 块内诊断粒度粗」。

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
- `docs/gaps/gap-language-pack-scope.md`（分层草案 / 接受域清单 / 渲染保真现状）
- `linter/linter_architecture.md`（linter 分层与已知边界；语句发现/区间判定口径）
- `parser/expression_conventions.md`（表达式隐式约定，含 `pratt_level`）
- `core/component_protocol.md`（加语法结构 / 插件的工作流）

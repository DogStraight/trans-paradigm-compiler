# preprocessor — 宏展开 / 反向映射

> TOML 驱动的宏展开（`` `NAME ``、指令）与反向（渲染后把展开还原回宏调用），
> 语言无关。位置桥 = 锚 + 原文（source_text）消耗式回插。
> 锚形态两态（`mode`）：`line`（行首空体宏，整行占位）/ `inline`（行内空体宏，
> marker 占位）；未知 mode → fail-fast。非空体宏不建还原锚，宏体文本铺进流，
> 还原走宏区间 + 渲染 raw 拼接（`_macro_source_text`）。

## marker 的书写形态（声明驱动）

占位 marker（`tpc:<kind>:<seq>`）必须**以注释形态**穿过管线（parser 当 trivia
跳过、渲染端保留注释），所以它的书写标点 = **语言的**注释标点，全部从语言包
声明取（`[comment] pairs` / `[[capture]]`）：

- 读取点：`lexer/comment_syntax.py`（`CommentSyntax`：行注释起始 + 成对定界符）；
- 书写/识别约定：`_markers.py`（整行形态 `line_marker` / 行内形态 `inline_marker`）；
- 两种形态：**整行**（行注释独占一行：条件块占位 / 整行宏锚 / 指令行占位）与
  **行内**（块注释：空体宏锚）。

引擎不认识 `//` / `/* */`（yaml 是 `#`，c4 只有行注释且有两种）——语言包未声明
所需形态而该形态又被需要 → fail-fast（不静默降级）。

## 形态清单（哪些是声明列表、哪些是引擎机制）

**语言知识 → 语言包声明（列表形态）**：

| 形态 | 声明位置 | 消费点 |
|------|----------|--------|
| 注释标点（行注释起始 / 成对定界符） | `[comment] pairs` / `[[capture]]` | `lexer/comment_syntax.py` → `_markers.py`、`analyzer/suppress.py` |
| 宏形态（`shape` 生产式：前缀 token 名 + 名字位；段候选列表枚举） | `[macro_recognition]`（`shape` / `directive` / `call`） | `macro_shape.py`（声明解析）→ `lexer` 宏 token 扫描、`_expand.py`（文本层展开） |
| 带参宏实参形态（调用括号对 + 实参槽 + 分隔符；定义侧与调用侧同形） | `[macro_recognition]`（`call_args` / `arg_separator`） | `macro_shape.py`（声明解析 + 配平/切分）→ `_expand.py`（调用侧）、`primitives/define.py`（形参表） |
| 宏调用后随字面量后缀（`` `W'd0 `` 的 `'d0`；比 `[[number.based]]` 宽一档） | `[macro_recognition]`（`suffix_after_call`） | `macro_shape.py::load_macro_call_suffix`（编译形态模式）→ `_expand.py`（区间扩展） |
| include 路径形态（开 / 闭定界符 + 解析策略：相对优先 or 仅 search_dirs） | `[directive_handlers.include]`（`path_forms`；未声明→引擎默认两形态） | `primitives/include.py`（形态匹配 + 路径解析） |
| 宏**定义侧**形式语法（变参占位 `...` 等；linter 阶段检查的启用判据与形态） | `[macro_syntax]`（`variadic_marker`；与 `[macro_recognition]` 同文件） | `macro_shape.py::load_macro_syntax`（声明解析；**未声明 ⇒ 不启用**）→ `linter/macro_syntax.py` |
| 数字形态（位宽字面量等） | `[[number.based]]` | `lexer/number_gen.py` |
| 括号对 / 逗号等标点 | `[bracket] pairs` / `[symbol.*]` | lexer / parser / linter |

**引擎机制 → 不进语言包**（形态确定之后的"怎么替换/怎么还原"）：三种处置机制
（`splice` / `line` / `inline`）与其执行；**选哪一种由语言包策略决定**
（见下节「宏处置策略」）；注释形态的可用性由声明**推导**（有行注释 → 整行形态
可用；有块注释 → 行内形态可用）；指令行切分 = **前缀 + 关键字 + 空白 + 参数**
（`primitives/registry.py::split_directive`：关键字拼写取自声明候选、分隔空白不
假定为单个空格——扫描侧取关键字与各 handler 取参数同源一份实现）。

## 宏处置策略（插件能力）

引擎只做**文本操作**（替换 / 锚书写 / 还原 / 区间与行映射）；"这个宏调用该怎么
处置"是**语言知识** → 语言包通过 `[capabilities] macro_policy = "file.py:fn"`
声明策略（与 formatter 同款，见 `core/component_protocol.md`）：

- 引擎给**通用文本事实**（调用点上下文，`preprocessor/_expand.py::_call_site`）：
  名字 / 宏体 / 是否带参 / 行号与行内起止列 / 行内前后文 / 是否行首行尾 /
  是否独占该行；
- 策略返回**处置枚举**（引擎机制面，与铺条目 `mode` 同词）：
  `splice`（宏体铺进流 + 宏区间）/ `line`（整行占位）/ `inline`（行内注释锚）；
- 未声明能力 → 默认 `splice`；方案非法（mode 未知 / `line` 用于同行多调用）
  → fail-fast（不静默降级）；
- 查找按 **rules_dir** 作用域（`core/plugin_loader.py::get_capability_in`）：
  只有该语言包 `plugins/` 下的组件才有资格应答，同进程切语言不串用。

verilog 的判定表见 `grammar/verilog/plugins/macro_policy/README.md`。
引擎侧不再留任何宏相关的语言知识（前缀 / 名字位候选 / 实参形态 / 后随字面量后缀
全部按 `[macro_recognition]` 声明取）。

> 为什么策略走**插件**而不是一张纯 TOML 策略表：判定"这个调用点该怎么处置"的条件
> 本身就是语言知识，写成表会演化成小型 DSL；且与 analyzer 已有的"L1 声明式 + L2 插件
> handler/postpass"分工重复——引擎只负责给**文本事实**，策略判定留给语言包代码。

## 跨语言文本能力原型（现状与上提触发条件）

> **三层归属（作者 2026-10-17 定）**：① **文本级宏 → 本模块**（预处理**只做文本级宏处理**）；
> ② **卫生宏 → 语法结构**（当语法处理，不属预处理器）；③ **过程宏 → 插件能力位**（"做中间层
> 转换"的能力可以在**插件侧**展示 ⇒ 它可以是一个插件能力）。**主管线不关心后两者**。
> 文本操作的能力原型**按需求实现**，**先满足 C**；**只考虑 C 标准中的宏**——特定编译器才需要的
> 宏（编译器专属扩展）**不考虑**。
>
> **定位边界（作者 2026-10-17 澄清）**：tpc **不执行任何代码**（不是执行器 / 编译器后端）；
> 对宏的唯一要求是**保证语法结构往返**（解析出结构 + 渲染回等价文本）。因此**过程宏可当作
> "一种特殊的语法"**——只需表达它的**调用形态**并保真往返，**不展开、不执行**。
> ⇒ **"宏原型"不存在"编译期执行层"**；原型面 = **变换（展开/占位）+ 还原（锚 + 原文 + 区间）**
> 这两件现役能力（`splice`/`line`/`inline` 与位置桥）。语言层面的"卫生宏 / 过程宏"分层**不构成
> tpc 需求**，只影响两件事：**该语言的调用形态能否用语法规则表达**、**往返是否可行**。
> **能力判据**：宏"展开后才有语法结构"（C / Verilog 式）⇒ tpc 需**展开 + 还原**（现役够）；
> 宏"必须执行才能确定展开内容"（过程宏式）⇒ tpc **不展开**，把调用形态当**不透明语法**保真往返。

"**在预处理器里实现原型、语言接上去**"是本模块**已采纳**的形态，与
`core/component_protocol.md`「引擎 vs 插件的能力边界」同源（引擎侧留**占位 + 简单实现**，
语言特有的完整实现集中到语言适配层）：

- **原型注册面** = `primitives/registry.py`（`register(name, kind)`）；已注册 **替换**
  `define` / `undef`、**包含** `include`、**条件** `ifdef`（`kind="control"`）。
- 语言包"接上去"走**声明**（不写 py）：`[macro_recognition]`（关键字拼写 / 形态 / 实参 /
  后缀）、`[directive_handlers.include] path_forms`（路径策略；未声明 ⇒ 引擎默认两形态）。
- **仍在代码侧的只有"处置判定"**（`[capabilities] macro_policy`）。评估（2026-10-17，
  `_drafts/preprocessor_prototype_assessment.md`）结论：**今天不上提**——按
  `component_protocol.md`「语言间分布」判据，上提要"多语言共有且形态稳定"，而实测只有 verilog
  一个声明方；且"**不用依赖插件**"的准确表述是"**加语言不写代码**"（6 项成本中 5 项不免除，
  真收益 = 无 py 即无模块缓存 + 非法检查可前置到装载期）。**触发条件**：第二个语言包出现
  **同形**处置判定 ⇒ 以可选 `[macro_policy] when`（既有 `call_site` 事实的**合取** → mode，
  小表非 DSL）上提；**替代而非并存**（两处同时声明 ⇒ 加载期 `ConfigError`）。

## 宏算子与调用形态（阶段 4 首片 A · 语言包声明）

| 键（`[macro_recognition]`） | 含义 |
|---|---|
| `call_shape` | **调用**形态：单元素 `"name"` = **显式无前缀**（C 的裸标识符调用）；`"<token>,name"` = 该前缀；**未声明 ⇒ 沿用 `shape` 前缀**（verilog 语义不变） |
| `stringize_operator` / `paste_operator` / `variadic_name` | `#` / `##` / 变参占位；**未声明 ⇒ 该语义不启用**（verilog 零影响） |
| `string_delimiters` / `escape` | 不在本段声明：字符串/字符字面量形态取自 token 表 `[string]`（与 lexer 捕获器同源），供 `#` 字符串化与**掩码**共用 |

引擎保证：宏匹配与**掩码**（字符串/字符/行注释/块注释，**含替换进流的宏体**）在
**同一次扫描内**生效；裸标识符调用的整词边界由 `core.token_protocol.IDENT_RE`
派生（不另写标识符字符类）；`[expand] max_iterations` 只是**资源上限守卫**
（同一算法上的预算，不是第二套算法）。

**阶段 4 首片 A 的已知边界**：`#include` 缺文件/循环仍只 `print` 警告（**A2 修**：
改诊断）；`#if`/`#elif` 整型表达式、`#line`/`#error`/`#pragma`/`_Pragma` 与 C23 项
（`#warning`/`#elifdef`/`#embed`/`__VA_OPT__`/`__has_include`）**未实现**（范围基线见
`docs/gaps/gap-c-preprocessor-scope.md`）；`-E` 字节保真不承诺；`__DATE__`/`__TIME__`
**永久排除**（破坏幂等）。

已声明边界（端到端用例里以**守卫断言**锁住，落地时必须显式改断言）：

- **替换结果里再出现的调用不重扫**（token 级 hideset 重扫留 A2）：`#define g f` +
  `#define f(x) x+1` + `g(2)` ⇒ 当前 `f(2)`（GCC `2+1`）；`#define f(a) a*g` +
  `#define g(a) f(a)` + `f(2)(9)` ⇒ 当前 `2*g(9)`（GCC `2*9*g`）。
- **实参跨行的调用不展开**（替换区间跨行会改输出行数/行映射，冻结契约面未动）：
  `#define F(a,b) a+b` + `int r = F(1,` + `            2);` ⇒ 当前原样保留
  （GCC `int r = 1+2;`）。
- 宏算子字符串化按**实参原文切片**（`#__VA_ARGS__` 的间隔空白保留：`V(a ,  b)` ⇒
  `"a , b"`，与 GCC 一致）；体展开里的嵌套调用无原文时退回 token 拼接。

## 文件清单

| 文件 | 一句话 |
|------|--------|
| `_expand.py` | 宏展开（strip 指令 + `` `NAME `` 引用展开）+ 指令扫描的注释跨度 |
| `macro_shape.py` | 宏形态声明读取（`[macro_recognition]` 生产式解析：前缀 token 文本 + 名字候选 + 实参形态 + `call_shape`/算子；`[macro_syntax]` 定义侧形式语法，未声明 ⇒ 不启用） |
| `macro_expand.py` | 宏展开核心（hideset 重扫描 + `#`/`##`/变参 + 掩码；`#` 字符串化的 token 间空白折叠） |
| `_reverse.py` | 宏反向（统一位置桥：锚 + 原文回插） |
| `_bridge.py` | 统一位置桥（Anchor Bridge）——锚 + 原文消耗式回插引擎 |
| `_markers.py` | tpc marker 书写/识别（注释形态声明驱动） |
| `primitives/` | 指令处理原语（define/ifdef/include/undef 等） |

> 入口：`_expand.py`（展开）/ `_reverse.py`（反向）；宏还原门禁见
> `tests/e2e/`（test_comment_restore / 宏还原）。

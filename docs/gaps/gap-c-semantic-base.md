# Gap — C 语义基座（符号表 / 作用域 / 声明顺序）（ROADMAP「C 语义层切片 1b」）

- 状态：**已拍板（作者 2026-10-10）**——方向 = linter 判"候选是否收敛"（不收敛出**内部
  warning**）→ parser 歧义位点走 **raw 暂缓建树** → **analyzer 插件**补理解路径；
  **P1→P4 分片实施**（P1 = C 包符号收集产物，含**分期标注**）。裁决全表见末节 `## 已拍板`
- 关联：`ROADMAP.md`「C 语义层切片 1b」（与 C 包阶段 3 共用前置；阶段 3 已交付，残片见 `TODO.md`「五、搁置」）；
  `docs/gaps/gap-semantic-elaboration-boundaries.md`（两套 scope 并存）；`grammar/c/**`
- 参照：`docs/references.md`「C 语言文法参照」；GCC `gcc/c/c-parser.h`；
  clang `clang/lib/Parse/ParseTentative.cpp`；tree-sitter-c `grammar.js`

## 缺口是什么

语义基座 = 符号表（typedef 名 / 标签命名空间 / 普通标识符）+ 作用域栈（块 / 函数原型 / 文件）
+ **声明顺序敏感性**。当前 C 包**没有**这一层，故下列四条现状成立（均为实测）：

1. **`(myint)x` 被拒，且失败模式是"整个函数截断丢内容"**（比"该语句失败"严重）。
   `CastTypeName` 只认类型关键字起头、不含 `@TypedefName`（`grammar/c/00_expressions.toml:352-363`），
   而 `ParenthesizedExpr` 吃掉 `(myint)` 后剩 `x` 无法成句 ⇒ 整条函数语句失配 ⇒ 解析截断。
   实测：输入 `typedef int myint;\nvoid f(int x) { myint y = (myint)x; }\n`
   的 AST 只剩前一条 `Declaration`，渲染输出仅 `typedef int myint;`（显著 token 序列**不保真**）。
   若真实语料出现该形态，`tests/languages/c/test_c_render_fidelity.py` 的保真判据会红
   （现有 3 样本未覆盖）。`(myint){1}`（复合字面量）同形同因。
2. **`myint *b;` 被读成表达式语句且与"同名非 typedef"完全不可分**。
   `Stmt` 候选中 `@ExprStmt` 排在 `@Declaration` 之前（`grammar/c/03_statements.toml:41-49`，
   这是刻意的语法层宽进）⇒ `myint *b;` 进 AST 为 `ExprStmt` + `BinaryOp`（渲染按乘法排版
   `myint * b;`）；且实测**把 typedef 声明换成 `int myint;` 后形状逐字不变**——同文本的两种
   读法在当前管线里不可分辨（token 保真 ✔，语义形态 ✘）。
3. **`sizeof(myint)` 无 typedef 声明也判类型名（纯宽进）**。
   `@TypeName` 含 `@TypedefName`（`grammar/c/00_expressions.toml:339-350`），
   而 `@TypedefName` 是"标识符作类型"的语法占位（`grammar/c/02_types.toml:178-194`）——
   实测 `unsigned n = sizeof(myint);`（全文无任何 typedef）同样进 `SizeofTypeExpr` + `TypeName`。
   属刻意宽进（`ROADMAP.md` 切片 1b「待决 ④」），需要符号表才能收窄。
4. **引擎侧语义钩子已接线但空转，且两套 scope 机制并存**：
   - `parser/block_parser.py:27-32` 已把 `scope_stack.lookup` 作为 `scope_lookup_fn` 传给
     `get_candidate_rules`（`parser/rule_selector.py:141-168`）——**但**
     `parser/parser_core.py:168` 的 `_ScopeStack.register` **全仓无调用方**（实测 grep）⇒
     符号 store 恒空、`lookup` 恒返回 `None`。`parse_sentence`（`block_parser.py:37-44`）
     与 atom 路径（`parser/parser_core.py:196-215`）都**不记录"还有别的候选也成立"**。
   - 词法预扫描 `lexer/pre_scan.py`（`{name: kind}` + `rule_hints`）机制齐备；C 包现已声明（`base/_pre_scan.toml`）。
    ⚠ **2026-10-22**：方向 = 两阶段 lint（符号判定后移 analyze），落地后删；作者拍板**暂缓为专项整治**（ADR-0024 / ROADMAP P2.9）。
   - analyzer 侧另有**完整**的 `analyzer/scope.py::Scope/Symbol`（post-parse，声明驱动
     `[*.analyzer.scope/symbol]`）——C 包未声明，且与 parser 侧 `_ScopeStack` **无共享**。

## 为什么纯语法不可绕过（实测量化）

两条"不引入符号谓词"的硬拼路径各修一半、各坏一半（把 `grammar/c` 复制一份打补丁后实测）：

| 输入 | 现状 | 补丁 A：`CastTypeName` 加 `@TypedefName` | 补丁 B：`@Declaration` 提到 `@ExprStmt` 前 | 编译器读法 |
|---|---|---|---|---|
| `(myint)x`（typedef 已声明） | ✘ 截断 | ✔ `CastExpr` | ✘ 截断 | `CastExpr` |
| `(a)*b`（`a` 是普通变量） | ✔ `BinaryOp` | **✘ `CastExpr`（误判）** | ✔ `BinaryOp` | `BinaryOp` |
| `a * b;`（合法表达式语句） | ✔ `ExprStmt` | ✔ | **✘ `Declaration`（误判）** | `ExprStmt` |
| `myint *b;`（非 typedef） | `ExprStmt` | `ExprStmt` | `Declaration`（与 typedef 版仍不可分） | `ExprStmt` |

⇒ **"该标识符是不是 typedef 名"是不可绕过的谓词**；这也解释了切片 1a（类型关键字起头）
为何能纯语法落地——类型关键字不可能起始表达式。补丁 B 的同类回归此前已记录在
`grammar/c/03_statements.toml:41-44`。

**复跑片段**（存任意路径后在仓库根 `python <file>`；不依赖任何草稿文件）：

```python
import os, sys; sys.path.insert(0, os.getcwd())
from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister, iter_nodes
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
P, G = "grammar/c", "grammar/c/plugins"
ConfigRegistry.load_language(P, plugins_dir=G)
rules = setup_grammar(P, GrammarRulesRegister(), ext_dirs=[G])
stmt = [n for n, r in rules.items() if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()]
parser = Parser(rules_dir=P, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file="")
lexer = Lexer(rules_dir=P, ext_dirs=[G])
for src in ("typedef int myint;\nvoid f(int x) { myint y = (myint)x; }\n",
            "typedef int myint;\nvoid f(void) { myint *b; }\n",
            "unsigned n = sizeof(myint);\n"):
    ast = parser.parse(lexer.tokenize(src))
    print(src.splitlines()[-1], "->", sorted({n.node_name for n in iter_nodes(ast)}), flush=True)
print("scope_stack:", parser.scope_stack.dump(), "pre_symbols:", parser.pre_symbols)
```

补丁 A/B 的复现 = 对 `<pack>/00_expressions.toml` 的 `CastTypeName` production
（`...|@AnonEnumSpecifier",` 行）追加 `|@TypedefName` / 对 `<pack>/03_statements.toml` 的
`Stmt` production（`:49` 行）把 `@Declaration` 前移，再跑上面片段。

## 成熟解法参照（见贤思齐）

- **GCC**（源码 `gcc/c/c-parser.h`）：令牌自带符号类别 —— `enum c_id_kind { C_ID_ID,
  **C_ID_TYPENAME**, … }` 写进 `struct c_token.id_kind`；未知标识符的偏置**按位置声明**：
  `enum c_lookahead_kind { cla_prefer_type, cla_nonabstract_decl, cla_prefer_id }` +
  `c_parser_declspecs(..., c_lookahead_kind)`。
  🔥 **直接借鉴**：①类型名判定必须在"决定语法形态的那一刻"可得；②把隐式的候选顺序换成
  **逐位点声明的偏置**。📌 **不实现**：Objective-C 类名/地址空间等种类，及其 bison 栈形态。
- **clang**（源码 `clang/lib/Parse/ParseTentative.cpp`）：`Parser::TPResult {True, False, Ambiguous}`
  三态 + `TentativeParsingAction`（试解析 → `Commit()`/`Revert()`）；类型名判定走**令牌标注**
  （`tok::annot_typename`、`TryAnnotateTypeOrScopeToken`、`Actions.ClassifyName`），
  歧义定则 "Declarations take precedence over expressions"。
  🔥 **直接借鉴**：三态 + 试解析回滚是歧义位标准构件（tpc 已有快照/回滚与 atom 最长匹配，
  缺的只是"问符号"这一步）；标注把"查一次"固化，避免逐位点重复查询。
  📌 **不实现**：模板/`typename`/Objective-C 面与 parse 期 Sema 回调链。
- **tree-sitter-c**（源码 `grammar.js`）：**没有符号表** —— `conflicts` 显式声明
  `[$.type_specifier, $.expression]`，`_type_identifier: alias($.identifier, $.type_identifier)`
  允许任何标识符当类型名，`prec.dynamic(-1, …)` 降优先度，靠 GLR 择一。
  💡 **启发**：允许"不判"也能出可用 CST（对应本仓 raw 路径）；📌 **不实现**：GLR/冲突体系
  （等于换解析器，成本与收益不成比例）。

## 机制现状（循环 #2 调研实测；P2–P4 的前置事实）

- **内部 warning 载体**：今天**没有**非用户通道（`LintDiagnostic` 的 severity/blocking 都进用户
  输出与 `--json`；`_trace_out` 只是 stderr 文本）⇒ 需一条**旁路**（`lookahead` 记录 →
  `scanner.scan()` 按次取走 → pipeline 上下文新字段；先例 `Discovery._unrecognized`）。
  **作者裁决：内部机制，不进诊断 / `--json` / exit code**。
- **raw 暂缓建树的承载**：渲染侧对任何带 `_verbatim_text` 的节点整段直出（`node_renderer.py`），
  先例 = 宏 splice ⇒ **渲染零改动**；AST 侧照 `MacroCall` 形态（内容 + 源文本 + token 区间），
  但必须**消费整个区间**（否则走 truncation 会被判失败、停管线）。
- **符号回滚（循环 #3 已补）**：快照纳入符号 store、`restore` 按撤销日志精确还原（含**同深度**
  register）、pratt 分支补作用域帧、`Parser.parse()` 每轮重建 store；**剩余** = `sibling_counter`
  与簿记集合不在快照内（只影响 `path=`/观测面）、`restore` 只截不补（更深快照回滚未支持）。
- **两侧 token 流不同源**：linter 吃展开态、parser 吃词法 tokens ⇒ 位点传递不能用 token 索引，
  须用**行/列**（作者裁决）并由 parser 侧重定位。
- **`phase` 落法（作者裁决）**：先走 `Symbol` 的 `attrs`（零引擎改动、`to_dict` 自然带出），
  将来需要升一等字段时单独立项。
- **收敛判定口径（P2a）**：上下文过滤后 `errs == 0` 的候选 ≥2 且 `(errs, consumed)` 无法区分
  ⇒ **未收敛**；唯一最优或可区分 ⇒ 收敛（伪候选问题见
  `docs/gaps/gap-parser-linter-approximation.md`）。

## 可实现性

**落点三案**（判据 = `core/component_protocol.md` §1c：普适性 / 配置 vs 代码 / 增量）：

| 案 | 评 | 建议 |
|---|---|---|
| (a) C 包 analyzer 插件 | 语言特有判定（typedef 与变量同名互斥、标签命名空间独立、遮蔽、声明顺序）需算法 ⇒ 插件；复用既有 analyzer `Scope/Symbol` 骨架、只写差 | **推荐**（首片落这里） |
| (b) 引擎原语（把符号能力前移到 parse 期） | 引擎已有两套 scope 模型（parser `_ScopeStack` 空转 / analyzer `Scope` post-parse）⇒ 不是从零造；verilog 已用同族声明（`typed_ports`/elaboration）⇒ 非单语言。但"parse 期可查"是**新契约面** | **待拍板**（拍板点 1/2/3/6） |
| (c) 引擎配置字段 | "是不是 typedef 名"需作用域+顺序（状态/算法），不可表单穷举 ⇒ 命中 §1c 反例；且会把复杂度搬进契约面 | **不做** |

**已拍板方向（作者 2026-10-10）——三层接力，不走 parser 谓词键 / 运行期钩子**：

> ① 声明式谓词键、② 运行期查询钩子：**延后**（现在不做）。**关键在 linter**——linter 先过
> 歧义路径；**路径无法收敛时 linter 给出内部 warning**；之后 **parser 经过此处走 raw 路径、
> 暂缓建树**；之后由**分析器插件**实现理解路径。作者原话要点："raw 路径是把问题**上移一层**
> 解决的好方法——宏体我们就是这么解决的"，故 raw 作为**内部机制**存在（不升格为公开判据）。
> ③ 两遍：只允许 **pre-scan 重排候选**、不允许影响形态（保持 fail-open）。④ 未声明标识符
> 默认偏置**显式化**。⑤ 符号**提前注册**且**分期标注**（名称来自哪个时期必须可区分）。
> ⑥ parser `_ScopeStack` 与 analyzer `Scope/Symbol` **不合并**——但两者**本质是一套识别系统
> 在不同时期的表现**（能力不同），机制文档须写明这层关系。⑦ 两遍影响形态：非核心问题，
> 按上述 fail-open 处理。⑧ C 包 `pre_scan` 落地：落（含"预扫描不精确"偏差登记）。

**原四选一评估**（保留作背景，结论已被上面的拍板取代）：
- **① 回溯式 + 声明式谓词闸门**：曾为首选（`(` 后试解析类型名 → 问符号谓词），现**延后**——
  谓词键是 parser 契约面，作者要求先由 linter 承担"收敛与否"的判定。
- **② 查询钩子**（pack 提供 `is_type_name` callable）：**延后**（与①同缺口，且倾向先用数据）。
- **③ 两遍**：真两遍破"先声明后使用"⇒ 原不做；2026-10-22 定为**两阶段 lint**（lint 符号无关 →
  parse raw → analyze 裁决），"保留 pre_scan"作废；**暂缓为专项整治**（刻度后集中处理）。
- **④ raw 路径**：**采纳为内部机制**——不选边、保留原样节点交后端定，渲染走引擎既有
  raw 直出（先例 `_verbatim_text`）。它能立刻把"整函数截断丢内容"变成"完整保留"，且不碰
  契约面。

**分片实施顺序**（每片独立可验证；细节计划见 `ROADMAP.md`「C 语义层切片 1b」）：
**P1** C 包声明式符号收集产物（作用域 + 声明序 + **分期标注**，纯包侧）→
**P2** linter 歧义路径收敛判定 + **内部 warning**（引擎侧通道，机制调研中）→
**P3** parser 歧义位点 raw、暂缓建树（内部机制）→
**P4** analyzer 插件消费 raw + 符号，实现理解路径（`(myint)x` 判定在此闭环）。

**最小首片（P1）**：C 包的**声明式符号收集产物**——每条符号
`{name, kind（typedef/标签/变量/枚举常量）, scope, decl_order, phase（pre_scan/analyze）}`，
未声明标识符默认 `not typedef`（显式化）。判据：正 `typedef int myint; myint v;` ⇒
`myint`=typedef、`v`=variable；负 `int myint; myint *b;` ⇒ `myint`=variable（**不得** typedef）；
声明顺序 `myint v; typedef int myint;` ⇒ 使用点处不在作用域；作用域：块内 typedef 出块失效、
内层遮蔽外层各一例；**分期**：同名在两期的记录可区分；回归 `pytest tests/` 零失败 +
`tools/c_acceptance.py` 仍 42/42（**口径**：两条预处理用例按"被消费且无异常"接受，**不代表已真实
实现**，见 `docs/gaps/gap-c-preprocessor-scope.md` ⑭）+ smoke 绿。

## 关联条目

- `ROADMAP.md`「C 语义层切片 1b」（含判据 ①-⑤ 与待决 ①-④）+ C 包阶段 3（已交付，残片见 `TODO.md`「五、搁置」）
- 两套 scope 并存的工程事实：`docs/gaps/gap-semantic-elaboration-boundaries.md`
- C 包接受域现状（含 `(myint)x` 行）：`docs/gaps/gap-language-pack-scope.md`
- 保真判据：`tests/languages/c/test_c_render_fidelity.py`；接受面盘点：`tools/c_acceptance.py`
- 引擎侧实现点：`parser/parser_core.py`（`_ScopeStack`）、`parser/rule_selector.py`
  （`scope_lookup_fn`/`pre_hints`）、`parser/block_parser.py`、`lexer/pre_scan.py`、
  `analyzer/scope.py`、`core/define.py`（`peek`）

## 已拍板（作者 2026-10-10）

| # | 问题 | 作者裁决 |
|---|---|---|
| 1 | `[Rule.parser]` 声明式谓词键（新契约面） | **延后**——先由 linter 承担"候选是否收敛"的判定 |
| 2 | 运行期查询钩子（callable 注入） | **延后**（按 Lead 表述：能不用 callable 就不用） |
| 3 | 符号注册时机 | **提前注册**；但注册须**分期标注**——"什么名称来自什么时期"要能区别 |
| 4 | 未声明标识符默认偏置 | **显式化**（默认 `not typedef`，可声明覆盖） |
| 5 | raw 路径是否升格 | **作为内部机制存在**，不升格为公开一等判据；先例 = 宏体（raw 源区间），"把问题上移一层" |
| 6 | 两套 scope 是否合并 | **不合并**；但机制文档须写明两者**本质是一套识别系统的不同时期**、能力不同 |
| 7 | 两遍是否允许影响形态 | 非核心问题——**只允许 pre-scan 重排候选、不允许影响形态**（fail-open） |
| 8 | C 包 `pre_scan` 是否落地 | **曾落，现将删**（2026-10-22 方向变更：两侧改两阶段 lint，见决策 ③ 更新与 `docs/decisions/0024-two-phase-lint-prescan-retirement.md`） |

**关键设计句（作者原话要点）**：关键在 **linter** —— linter 先过歧义路径；路径**无法收敛**
时 linter 给出**内部 warning**；之后 parser 经过此处**走 raw 路径、暂缓建树**；之后由
**分析器插件**实现**理解路径**。

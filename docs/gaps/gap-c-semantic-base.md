# Gap — C 语义基座（符号表 / 作用域 / 声明顺序）（ROADMAP「C 语义层切片 1b」）

- 状态：未立项（设计输入已备：框架级拍板点 1-7 见末节 `## 待拍板`，8 为细节级）
- 关联：`ROADMAP.md`「C 语义层切片 1b」（与 C 包阶段 3「结构类型与作用域语义」共用前置）；
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
   - 词法预扫描 `lexer/pre_scan.py`（`{name: kind}` + `rule_hints`，只做**候选重排**）机制齐备，
     但 C 包未声明 `[lexer] pre_scan`（实测配置为空）；verilog 在用。
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

## 可实现性

**落点三案**（判据 = `core/component_protocol.md` §1c：普适性 / 配置 vs 代码 / 增量）：

| 案 | 评 | 建议 |
|---|---|---|
| (a) C 包 analyzer 插件 | 语言特有判定（typedef 与变量同名互斥、标签命名空间独立、遮蔽、声明顺序）需算法 ⇒ 插件；复用既有 analyzer `Scope/Symbol` 骨架、只写差 | **推荐**（首片落这里） |
| (b) 引擎原语（把符号能力前移到 parse 期） | 引擎已有两套 scope 模型（parser `_ScopeStack` 空转 / analyzer `Scope` post-parse）⇒ 不是从零造；verilog 已用同族声明（`typed_ports`/elaboration）⇒ 非单语言。但"parse 期可查"是**新契约面** | **待拍板**（拍板点 1/2/3/6） |
| (c) 引擎配置字段 | "是不是 typedef 名"需作用域+顺序（状态/算法），不可表单穷举 ⇒ 命中 §1c 反例；且会把复杂度搬进契约面 | **不做** |

**接口四选一**（形态 → 结论）：
- **① 回溯式**（`ROADMAP.md` 原首选）：`(` 后试解析类型名并**问符号谓词**，否即回滚按 `ParenthesizedExpr`。
  倚仗既有机制：atom 路径已是"多候选 + 快照 + 取最长消费"，`CastExpr` 天然消费更多
  ⇒ 只缺"谓词闸门"这一个声明式键。**方向推荐**（拍板点 1）。
- **② 查询钩子**：引擎在决策点调用 pack 提供的 `is_type_name`。与①**不互斥**（①=何时问、
  ②=怎么问）；倾向先用**数据**（声明式谓词）而非 callable（拍板点 2）。
- **③ 两遍**：真两遍（parse→建表→重解析）破 C 的"先声明后使用"语义且成本翻倍 ⇒ 不做；
  只取**既有 `[lexer] pre_scan` 的候选重排**（可改善 `myint *b;` 形态，纯包内配置），
  但预扫描自述"不是精确的"（`lexer/pre_scan.py:1-5`）⇒ 必须连带登记不精确偏差（拍板点 7/8）。
- **④ raw 路径**（作者 2026-09-26 指示）：不选边、保留原样节点交后端定，渲染走引擎既有
  `_verbatim_text`（`renderer/node_renderer.py:309`）。**作兜底但不升格**——它能立刻把
  "整函数截断丢内容"变成"完整保留"，且不碰契约面（拍板点 5）。

**最小首片**：C 包的**声明式符号收集产物**（纯后置 analyzer 插件，不改 parser）——
用既有 `[*.analyzer.scope/symbol]` 机制收集 typedef 名 / 标签 / 普通标识符 / 枚举常量，
产出带作用域与声明序的只读查询。判据：正 `typedef int myint; myint v;` ⇒ `myint`=typedef、
`v`=variable；负 `int myint; myint *b;` ⇒ `myint`=variable（**不得** typedef）；
声明顺序 `myint v; typedef int myint;` ⇒ 使用点为 None；作用域：块内 `typedef int t;` 出块失效；
回归 `pytest tests/ -q` 零失败 + `python tools/c_acceptance.py` 仍 40/42 + `pytest -m smoke` 绿。
**`(myint)x` 不在首片**（依赖拍板点 1/2/5）。

## 关联条目

- `ROADMAP.md`「C 语义层切片 1b」（含判据 ①-⑤ 与待决 ①-④）+「C 语言包」阶段 3
- 两套 scope 并存的工程事实：`docs/gaps/gap-semantic-elaboration-boundaries.md`
- C 包接受域现状（含 `(myint)x` 行）：`docs/gaps/gap-language-pack-scope.md`
- 保真判据：`tests/languages/c/test_c_render_fidelity.py`；接受面盘点：`tools/c_acceptance.py`
- 引擎侧实现点：`parser/parser_core.py`（`_ScopeStack`）、`parser/rule_selector.py`
  （`scope_lookup_fn`/`pre_hints`）、`parser/block_parser.py`、`lexer/pre_scan.py`、
  `analyzer/scope.py`、`core/define.py`（`peek`）

## 待拍板

**框架级（1-7，命中 `policy/collaboration.md`「升级回作者的判据」①：新增/改动引擎↔插件契约面）**：

1. **是否给 `[Rule.parser]` 引入声明式谓词键**（如 `requires = "<谓词名>"`，候选需先过符号判定）
   ——影响面：`core/define.py` 阶段字段校验 + capability 面；不做的后果 = 无法在纯语法层表达
   "这是类型名"，只能继续宽进。
2. **是否允许 pack 向 parser 提供运行期查询钩子**（`is_type_name` 类 callable）——影响面：契约面 +
   加载顺序/跨语言隔离/fail-fast；倾向先只用案①的数据式闸门。
3. **符号注册时机**：parse 期注册（须同时扩 `ParseContext.create_snapshot`，现有快照不含符号
   store ⇒ 失败候选会**泄漏符号**）vs 复用 analyzer `symbol_declare`（post-parse）。
4. **未声明标识符的默认偏置是否显式化**（GCC `c_lookahead_kind` 式，逐位点 `prefer_type`/`prefer_id`）
   ——影响面：新配置面；倾向先看真实语料误判面再定。
5. **raw 路径是否升格为一等能力**（含"候选是否收敛"信号成为 parser 一等判据）——影响面：
   parser 返回值契约 + 新节点类别语义；倾向先做"不截断"的最小兜底，不升格。
6. **parser 侧 `_ScopeStack` 与 analyzer 侧 `Scope/Symbol` 是否合并/共享**——影响面：引擎内部架构 +
   verilog/elaboration；不定的后果 = 同一份规则声明两处解释、长期漂移。
7. **两遍（`pre_scan`）是否允许影响解析形态**（现在只重排候选）——影响面：把 hint 升级为判据 ⇒
   预扫描的**不精确性**进入语义判定；倾向"允许重排、不允许过滤"（保持 fail-open）。

**细节级（8，维护者可自决 + 登记偏差）**：

8. **C 包 `[lexer] pre_scan` 声明是否落地**（typedef/标签两类 + `rule_hints`）：纯包内配置；
   落地须同步登记"预扫描不精确"（块内遮蔽、使用先于声明）为已知偏差。

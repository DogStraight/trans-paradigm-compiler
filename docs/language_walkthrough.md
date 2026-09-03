# 从零搭一门语言（Walkthrough，以 c4 为实例）

> 用 TransParadigm 的配置驱动框架，从零定义一个语言并跑通全管线
> （lex → parse → analyze → transform → render）。
> 本文以 **c4**（`grammar/c4/`，Tiny C 子集）为贯穿实例——它是项目
> 的第二语言，验证"语言知识全外部化 / 语言无关性"主张（Verilog 是第一个实例）。
>
> 面向读者：想拿本项目当骨架/改造的人、模型协作者。目标：照着本文，
> 理解"搭一门语言"需要写什么、会遇到什么机制问题。

---

## 0. 前置概念

一个语言包 = `grammar/<lang>/` 目录，包含：

```
grammar/<lang>/
├── tpc.toml          # 语言包入口：声明 [lexer]/[parser]/[renderer]/... 各配置指向的文件
├── token.toml        # 语言关键字（[id.keyword]）
├── base/             # 基础 token / lexer / operator / style 配置
├── 00_*.toml ...     # 语法规则文件（数字前缀排序，parser.rules 按此加载）
└── plugins/          # 语言插件（analyzer primitives / transform 槽位）
```

**单语言选择模型**：管线一次只用一种语言。初始化时选定：
`ConfigRegistry.load_language("grammar/<lang>")`——加载该语言包的声明并替换全部
配置（不混合、非热重载；切换 = 重新初始化）。

---

## 1. 开位置

建目录 + `tpc.toml` + 说明文档。规则文件按数字前缀排序：
`00_expression.toml`、`01_statement.toml`、`02_declaration.toml` …（规则少可单层，
`tpc.toml` 里 `parser.rules = { file = ["0*.toml"] }`）。

> ⚠ 不要先写半成品 `tpc.toml`：`config_registry` 会 fail-fast 校验，缺声明的
> 段/文件会抛 `ConfigError`。先放 README 固定位置，配置随实现逐步填。

---

## 2. 词法层（token + lexer）

**文件**：
- `base/_token.toml`：空白/换行、单字符符号 `[symbol.base]`、多字符符号
  `[symbol.extend]`、括号 `[bracket]`、字面量正则 `[literal]`、标识符 `[id.id]`
- `base/_lexer.toml`：注释 `[comment] pairs`、token 分类 `[token_category]`
- `token.toml`：关键字 `[id.keyword]`

**c4 要点**：
```toml
# base/_token.toml —— C 运算符 + 字面量
[symbol.extend]
is_equal = "=="
logic_double_and = "&&"
add_one = "++"
...
[literal]
string = "(\".*\")|('.*')"   # 字符 'a' 与字符串 "..." 共用
number = "\\d+"
```
```toml
# base/_lexer.toml —— c4 注释：// 与 # 都是行注释
[comment]
pairs = [["//", "\n", "line"], ["#", "\n", "line"]]
```
```toml
# token.toml —— c4 关键字
[id.keyword]
if = "if"
int = "int"
while = "while"
...
```

**验证**：`Lexer(rules_dir="grammar/c4")` tokenize 一段样例，检查数字、字符/字符串、
运算符、注释。

> 数字形态由配置驱动（P2.1）：`base/_number.toml` 声明 `[[number.based]]` 形态，
> 由 `lexer/number_gen.py` 编译为 FSM、`lexer/number_runner.py` 执行。

> 注释扫描走 `lexer/capture_runner.py::CaptureRunner`——原始文本捕获模式的
> 配置驱动执行器：`[comment] pairs` 是其 legacy 输入（归一化为 capture
> mode，`token_type = "comment"`）；字符串定界符由 `[string] delimiters`
> 声明（delim mode，`token_type = "literal.string"`，引擎不再硬编码引号）；
> heredoc/围栏等同类构造可声明 `[[capture]]` 段（`start`/`end`/`kind`/
> `token_type`，kind ∈ line/marker/delim/line_match/indent_leq）。
> indent_leq 是 YAML 块标量的列比较终止：`after`（前一显著 token 须在集合，
> 值位置判定）与 `next_chars`（后随字符须在集合）为触发条件，终止基准 =
> 触发行物理缩进列。
> `[indent] level` 支持 `"auto"`：缩进单位从文件启发式推导（首次结构缩进
> 行锁定，注释行不参与），lexer/main_lexer.py::_indent_aligned/_starts_comment；
> 锁定单位经 AST 根节点 `_indent_unit` 传递给 renderer（渲染与源文件单位一致，
> 块标量逐字内容相对列对齐不被破坏）。
> 裸标量（plain scalar）由 `[plain]` 段配置（`lexer/main_lexer.py` 的 plain
> 分支）：first/continuation 字符类（支持 A-Z 范围与 CJK 段）、
> stop_space_after（':' 后随空白即终止）、no_space_after_tokens（锚点/别名
> 名单词边界）、flow_terminators（括号内 { } [ ] , 终止、块语境吸收——
> 配置宽容，YAML flow 语境规则）。
> 无尺寸数字触发前缀（如 `'h`）由 `lexer/main_lexer.py::_build_unsized_prefixes`
> 从 `[[number.based]]` 形态推导（size=none + 单字符 base_prefix），不再硬编码。
> 详见 `lexer/capture_runner.py` 文件头与 `tests/engine/lexer/test_capture_runner.py`。

---

## 3. 语法规则（parse）

### 表达式：原子 + Pratt

- **原子规则**（`is_atom = true`）：Number、StringLit、Identifier、括号、调用、
  下标、sizeof、类型转换。pratt 的 `atom_parser` 遍历所有 is_atom 规则（production
  长的优先）。
- **运算符**：`base/_symbol_level.toml` 的 `[[operator]]` 数组，顺序 = 优先级从低
  到高；一元用 `position = "prefix"/"postfix"`。
- **表达式入口**：`Expression` 规则 `pratt = true`。表达式何时结束由 pratt 绑定
  强度决定（非运算符 token 自然终止中缀循环），后继合法性由派生 FOLLOW 校验
  （见 parser/follow.py），无需手写停止符（旧 `end_case` 已移除）。

```toml
# base/_symbol_level.toml —— 优先级（低→高）
[[operator]]
symbol = "="
arity = 2
assoc = "right"

[[operator]]
symbol = "?"
arity = 3
second = ":"
assoc = "right"

[[operator]]
symbol = "*"
arity = 1
position = "prefix"   # 一元解引用（与二元 * 同符号，按位置区分）
```
```toml
# 00_expression.toml —— 原子 + 入口
[Number.parser]
is_atom = true
production = ["literal.number"]

[Expression.parser]
production = ["@PrimaryExpr"]
pratt = true
```

> 💡 **语言差异 1——块边界推导**：块规则的起止符从 production 首尾**字面 token**
> 推导。原实现硬编码 `keyword.` 前缀（Verilog 的 module/begin/end 都是 keyword），
> c4 的 `{`/`}` 是 bracket 无法推导 → 匿名块无限递归。已放宽为"任何非 `@call`
> 字面 token"。见 §7。

### 语句/声明：is_statement 规则 + 根块

- 语句规则 `is_statement = true`，被 `parse_sentence` 按首 token 发现。
- 块规则 `is_block = true`：起止符从 production 首尾推导；body 由
  `parse_block_body` 逐句解析。
- **根块**（如 c4 的 `Program`）：无 block_start 的块规则 = 匿名根块，被
  `get_block_rule` 优先选中。

```toml
# 01_statement.toml —— if/else（body 用 @Stmt 选择器）
[IfStmt]
is_statement = true

[IfStmt.parser]
production = [
    "keyword.if",
    "bracket.l_parentheses",
    "@Expression",
    "bracket.r_parentheses",
    "@Stmt",
    "(keyword.else,@Stmt)?",
]
```

> 💡 **语言差异 2——语句后继语义（end_case 已移除）**：规则后继由派生 FOLLOW
> 机械推导——Verilog 语句以 `;`/块结束符为后继，C 以 `;`/`}` 为后继，全部从
> production 结构自动算出，语言包**无需手写后继 token 集合**。消歧用 `exclude`
> （负向前瞻）单独声明。见 §7。

---

## 4. 语义 + 产出（analyze / transform / render）

### transform：代码生成（c4 汇编）

`grammar/c4/plugins/asm_gen/_asm.py`：`@register_plugin` 的 `TransformPlugin`，
把 c4 AST 编译为 c4 VM 指令（符号表、表达式/语句/函数 → 指令、跳转回填），
产出 `AsmProgram`（sub_node = `AsmLine`，每条指令一行 text）。

```python
@register_plugin
class AsmGenPlugin(TransformPlugin):
    def process(self, ast, root_scope):
        if ast.node_name != "Program":   # 守卫：仅 c4 根块触发
            return ast
        ...编译为 AsmProgram...
```

插件放 `grammar/<lang>/plugins/<name>/`（组件），`tpc.toml` 的 `[transform] handlers`
声明；`setup_grammar` 按所选语言包自动加载组件（单语言不混合）。

### renderer：布局

`99_asm_render.toml`：
```toml
[AsmProgram.renderer.body]
indent = false   # body 项不缩进（顶格）；true=1 级缩进（默认），int=N 级

[AsmLine.renderer.layout]
ref = "text"
```

`renderer.body` 的 `indent` 字段控制 body 子项的缩进级别：
`true` = 缩进 1 级、`false` = 不缩进（顶格）、整数 = N 级，未声明默认 `true`。
汇编输出无嵌套块，逐行指令顶格（`indent = false`）。

**布局原语（ADR-0006 阶段 2 新增）：**

| 原语 | TOML 形态 | 语义 |
|------|-----------|------|
| `align` | `{ align = 5, doc = { line = [...] } }` | 绝对列对齐：doc 内换行缩进列 = `max(当前缩进列, align × 单位格数)`；首行不受影响（跨行对齐基准列） |
| `fill` | `{ fill = [{ref="a"}, {soft=true}, {ref="b"}] }` | 流式折行：内容/分隔符交替序列逐元素贪心放置，放得下 → 空格、放不下 → 换行（中间态折行） |
| `line_suffix` | `{ line_suffix = " // note" }` | 行尾锚定：内容推迟到下一个换行点之前输出（行尾注释锚定） |
| `intent` | `{ intent = "compact", items = "items" }` | 布局意图声明（ADR-0006 阶段 4a）：`compact`=紧凑列表（join+first_soft+nest 别名）、`wrap`=流式折行（fill）、`align`=对齐、`anchor`=行尾锚定。语言包声明"结构→布局意图"，引擎推导 Doc，消灭手拼 |

---

## 5. 测试

`tests/<lang>/test_*.py`：

```python
@pytest.fixture(scope="module")
def lang(config_loaded):
    ConfigRegistry.load_language("grammar/c4")
    register = GrammarRulesRegister()      # ⚠ 独立实例，勿用 get_default() 单例
    rules = setup_grammar("grammar/c4", register)
    ...
    yield ctx
    ConfigRegistry.load_language("grammar/verilog", plugins_dir="grammar/verilog/plugins")
```

> ⚠ 测试隔离：用独立 `GrammarRulesRegister` 实例，否则第二语言规则污染全局
> 单例缓存，其它语言测试的规则树会混合。

---

## 6. 验证

```bash
python -m pytest tests/languages/c4/ -q   # c4 集成测试（380 全量回归含此）
```

c4 输出示例（`int main(){ int x; x=1; return x; }`）：
```
ENT  0
LEA  0
PSH
IMM  1
SI
...
LEV
```

---

## 7. 过程中暴露的核心机制问题（第二语言验证的产出）

这是"从零搭语言"最有价值的部分——第二语言如实暴露了核心层的单语言假设与
Verilog 渗透。**每修一个，都是向"语言无关"迈进**：

| # | 机制问题 | 修复 |
|---|----------|------|
| 1 | 配置声明在 import 期只注册默认包，无法加载第二语言 | `ConfigRegistry.load_language(rules_dir)`（单语言选择） |
| 2 | glob 通配无匹配时 fallback 到含 `*` 字面路径（`Errno 22`） | 通配无匹配：required 显式报错 / 可选合法空 |
| 3 | `declare_cfg` 注册晚于 push（load_language 后 import）持有默认值 | 配置已加载时直接返回真实值 |
| 4 | **块边界推导硬编码 `keyword.*`**（Verilog 渗透，c4 的 `{}` 是 bracket） | 放宽为任何非 `@call` 字面 token |
| 5 | `load_all_toml` 把 `plugins/` 的 tpc.toml 当规则加载 | 跳过 `plugins/` 目录 |
| 6 | **语句 end_case 语义**：Verilog 用 newline 定界，C 用 `;`/`}` | 语言包按自身定界配置，不硬编码 |
| 7 | 组件加载只扫默认包 plugins/，多语言组件 grammar 混合 | 按所选语言包加载（单语言） |

---

## 8. 产出清单（c4 实例）

```
grammar/c4/
├── tpc.toml              # [lexer] + [parser] 入口
├── token.toml            # 关键字
├── base/_token.toml      # C 符号/括号/字面量/id
├── base/_lexer.toml      # 注释(// #) + token 分类
├── base/_symbol_level.toml  # C 运算符优先级
├── 00_expression.toml    # 表达式（原子 + Pratt）
├── 01_statement.toml     # if/while/return/块/空/表达式语句
├── 02_declaration.toml   # Program 根块 / 变量 / 函数 / enum
├── 99_asm_render.toml    # 汇编输出渲染
├── README.md             # 状态与决策
└── plugins/asm_gen/      # c4 → c4 VM 汇编生成插件
    ├── tpc.toml          # 组件声明（[transform] handlers）
    └── _asm.py           # AsmGenPlugin + 编译逻辑
```

---

## 附：与 Verilog 实例的关系

- Verilog = "一个已实现语言实例"（完整、带插件生态）。
- c4 = 第二个实例，证明**换一套语法配置即可搭新语言，无需改引擎**。
- 引擎（core/ + parser/ + lexer/ + transform/ 等）不含任何语言特定知识；
  语言知识全部在 `grammar/<lang>/`。

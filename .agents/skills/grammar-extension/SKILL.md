---
name: grammar-extension
description: 'tpc_compiler 语法扩展工作流：在已有语言包（grammar/verilog 等）上添加新关键字、新语法结构、增强类型系统——TOML 规则定义 → inject 挂载 → 测试验证。从零建一门语言见 docs/language_walkthrough.md（c4 实例）。'
user-invocable: false
argument-hint: '描述要添加的语法特性，如 "给 verilog 加一个带参数的 type 定义"'
---

# Grammar Extension 语法扩展工作流（tpc_compiler）

> 适用：在**已有语言包**上扩展语法。从零建一门语言（语言包级）走
> `docs/language_walkthrough.md`（c4 为最小模板）。两者共用同一套机制。

## 架构总览

```
grammar/<lang>/token.toml     ← 语言关键字（[id.keyword]）
grammar/<lang>/base/_token.toml ← 基础符号/字面量（主包，一般不动）
grammar/<lang>/00_*.toml      ← 语法规则（数字前缀控制加载顺序）
grammar/<lang>/plugins/<name>/ ← 插件：_token_ext.toml（插件关键字）+
                                  NN_*.toml（规则 + inject）+ handlers
parser/grammar_inject.py      ← 结构化注入（analyze → 树层合并 → serialize）
tests/languages/verilog/      ← 语言实例测试（新规则测试放这）
```

## production 书写（EBNF 变体，先读这条）

`build_tree` 会 `replace(" ", "")` **删除所有空格**——**序列必须用逗号**：

| 语义 | 写法 | 例子 |
|---|---|---|
| 序列 | **逗号 `,`** | `"keyword.force,@Identifier,symbol.base.equal,@Expression,symbol.base.semicolon"` |
| 选择 | `\|` | `"@Stmt\|symbol.base.semicolon"` |
| 可选 | 后缀 `?` | `"@BlockLabel?"` |
| 重复 | 后缀 `*`（0+）/ `+`（1+） | `"(...)*"` |
| 分组 | `(...)` | `"(keyword.assign\|keyword.force)"`（内部用 `\|` 或 `,`） |
| 规则调用 | `@Rule` | `@Expression` |
| 字面 token | `keyword.xxx` / `symbol.base.xxx` | `keyword.fork` |

⚠ 常见错：`"(a b)?"`（空格 seq）→ `GrammarError`。须写 `"(a,b)?"`。

## 步骤

### 1. 确定挂载层级

参考 `grammar/verilog/04_statements/00_base.toml` 的语句分层：

```
ModuleItem → DeclStmt | InstStmt | FuncStmt | AssignStmt | ProcStmt
Stmt       → CtrlStmt | ProcAssignStmt | ProcLocalDecl | CallStmt
  CtrlStmt → If/Case/For/While/Repeat/BeginEnd (+ 仿真经 SimCtrlStmt 容器)
  CallStmt → SubroutineCall | TaskCallStmt | NullStmt
  ProcStmt → AlwaysStmt
```

- 新关键字开头 → 挂对应层级（独占 token，风险低）
- `id` 开头 → inject 到调用处 production（如 `AnsiInputDecl.production[0]`）
- 过程体语句 → 注入 `@CtrlStmt` 或经容器（见第 4 步）

### 2. 加关键字

- 主包：`grammar/<lang>/token.toml` 的 `[id.keyword]`
- 插件：插件目录 `_token_ext.toml` 的 `[id.keyword]`（**多插件 token_ext 同名自动合并**——config_registry 已支持深合并，直接各写各的）

### 3. 语法规则文件

```toml
[RuleName]
is_statement = true            # 语句规则候选（需在语句分发里才设）

[RuleName.parser]
production = ["keyword.xxx", "@Identifier", "symbol.base.semicolon"]

[RuleName.parser.node]
name = "$2"

[RuleName.renderer]
layout = { line = [{ ref = "name" }, ";"] }

# 语义自声明
[RuleName.analyzer]
scope = { kind = "xxx" }
```

- **没有 `end_case`**（已整体移除）：后继合法性由 `parser/follow.py` 派生 FOLLOW 机械推导，不要写 end_case。
- **`exclude`**（负向前瞻）：仅用于消歧（如 `Declarator` 阻止 `@DeclaratorList` 贪吃 `.`），是唯一保留的显式声明。

### 4. Inject 挂载（增强语法）

```toml
[ExtRule.inject]
targets = ["@TargetRule"]              # 或 TargetRule.production[N]
```

两层注入（parser/grammar_inject.py）：
1. **直接注入**——`@ExtRule` 加入目标 production 的 choice
2. **传播注入**——引用 @Target 的规则替换为 `(@ExtRule|@Target)`

⚠ **多条规则注入同一 target → 用容器规则**（关键坑）：传播注入会逐条嵌套
`choice[A, choice[B, @Target]]`，且 `_write_prods` 污染单例规则表（浅拷贝共享
对象），每次 setup 叠加 → 全量测试 `RecursionError`。模式：

```toml
# 容器：多条仿真语句先挂到容器，容器再注入目标一次
[SimCtrlStmt.inject]
targets = ["@CtrlStmt"]

[SimCtrlStmt]
is_statement = true
[SimCtrlStmt.parser]
production = ["@A|@B|@C"]          # 各规则不再各自 inject
inline = true
```

（参考 `grammar/verilog/plugins/sim/90_sim_ctrl.toml`）

### 5. 语义/渲染

- analyzer：`[Rule.analyzer] scope = { kind, name_attr }` 自动声明符号
  （symbol_declare 机制取代手写 symbol 配置）；primitive 原语走
  `analyzer/primitives/`
- renderer：`layout`（text/ref/opt/group/line/join/nest DSL）——见
  `docs/component_protocol.md`、`docs/layout_spacing_prompt.md`

## 验证

```bash
python -m pytest tests/languages/verilog/ -q      # 新规则测试放这
python -m pytest tests/ -q                        # 全量（755 基线）
python tests/e2e/run_all_tests.py                 # e2e 93 组（FAIL 0）
```

- 新规则测试用**独立 `GrammarRulesRegister()`**（不要 `get_default()`）——
  全局单例 `self.rules` 累积 + 规则对象被 inject 改写，测试顺序敏感
- 跑完后 `git add -A && git commit`

## 常见场景速查

| 场景 | 挂载点 | 风险 |
|------|--------|------|
| 新关键字 `type xxx` | 文件顶层（Root/ModuleItem） | 低（独占 token） |
| 新端口类型 `spi.slave` | `AnsiInputDecl.production[0]` | 低 |
| 新过程语句 | `@CtrlStmt`（多规则→容器） | 中（传播嵌套） |
| 插件关键字 | 插件 `_token_ext.toml` | 低（同名自动合并） |
| 替换已有规则 | 插件同名 override | 中（属性映射 + renderer 全断） |

## 参考

- `docs/grammar_rule_fields.md` — 字段参考
- `parser/expression_conventions.md` — 表达式（Pratt，不走 BNF 翻译）
- `docs/config_lifecycle.md` — 配置三阶段（import 注册→load 推送→运行读取）
- `docs/language_walkthrough.md` — 从零搭一门语言（c4 实例）
- `grammar/c4/` — 最小语言包模板


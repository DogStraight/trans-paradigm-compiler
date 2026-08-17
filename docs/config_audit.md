# 配置审计报告 — 语言知识渗透与冗余配置摸底

> 日期：2026-08-18
> 目的：找出 (1) 类似 statement_entry 这类可推导的不必要配置；(2) 从配置渗透到核心
> 管线的语言知识（尤其写死的固定值）。**只摸底，不改代码**。
> 审计范围：core/ lexer/ parser/ linter/ analyzer/ transform/ renderer/ preprocessor/
> + grammar/ 两个语言包 + config/tpc_config.json。
> 铁律基准：语言知识（规则名、token 类型、结构名、表达式形态）一律由 grammar/ TOML
> 提供，引擎不得硬编码。

---

## A 类：语言知识渗透核心管线（写死的固定值）

### A1. `parser/_constants.py` — 语言约定常量集中写死在引擎 ✅ 已处理（2026-08-18）

- **token 类型**（comment/newline/id）：转移到 `core/token_protocol.py`（引擎 token 协议），
  `_constants.py` re-export 保持既有 import 路径。
- **ROOT_RULE_NAME**：`parser_core.parse` 改为从语法树自推导（`get_block_rule()` 优先匿名
  根块、回退第一个块规则），推导失败才用回退值。
- **COMMENT_NODE_NAME**：`block_parser._derive_comment_node_name` 从 "production == [comment]
  的规则" 自推导（verilog 推导得 Comment，c4 无注释规则回退）。
- **BLOCK_NODE_NAME**：确认为 parser 内部临时容器节点名（不泄漏到 AST），语法无关。
- 剩余回退值仅作语法树无法推导时的最后兜底，不再是语言知识。

### A2. `parser/pratt_parser.py` — pratt 内置前缀硬编码 AST 节点名 ✅ 已处理（2026-08-18）

`install_atom_name_map`：语言层从 is_atom 单字面 token production 规则推导
{token_type: 规则名}（如 literal.string → StringLiteral/StringLit、id → Identifier）
注入 pratt；内置前缀兜底产出的节点名据此对齐（语言定义原子规则即自动对齐，无规则
才回退内置名）。UnaryOp/BinaryOp/TernaryOp 保持为引擎表达式树约定——语言包声明
同名 renderer 布局对齐（verilog 已声明，方向是"语言对齐引擎"，非引擎写死语言）。

### A3. `analyzer/primitives/_symbol.py:76` — Verilog generate 语义写死在通用原语 ✅ 已处理（2026-08-18）

`Scope` 加 `allow_duplicate` 字段（由 `[analyzer.scope]` 规则字段声明），原语读字段而非
kind 名；`GenerateBlock` 的 scope 配置改 `{ kind = "generate", allow_duplicate = true }`。
语义由规则字段提供，引擎只承载——statement_entry 同款模式。

### A4. `core/utils.py:square_bracket_types` — 方括号 bracket 名字写死 ✅ 已处理（2026-08-18）

~~引擎假设语言把 `[]` 命名为 `square_bracket`，缺失即 fail-fast。~~

已改为按**字符** `"["` 在 `[bracket].pairs` 中定位配对（字符是词法数据，不依赖配对
命名）——任何命名（square_bracket/bracket/…）均可，消除名字约定门槛。

### A5. `analyzer/traversal.py:52` — 全局作用域名写死 ✅ 已处理（2026-08-18）

改 declare_cfg（`analyzer.root_scope`，默认 `{name="<global>", kind="global"}`），语言
包可在 `[analyzer]` 段覆盖。与 B2 同策略：默认值在引擎（协议兜底），语言包只在需要
不同值时显式声明——当前两个语言包均无需写。

### A6. `renderer/renderer.py` + `loader.py` — 默认风格值 ✅ 已处理（2026-08-18）

- `children_field` 从 style 配置移除：它是引擎 AST 协议（core.define.CHILDREN_FIELD），
  非风格；renderer 直接引用常量，`_style.toml` 删冗余行。
- `indent=4`/`max_inline=40` 引擎默认认定为**通用兜底值**（C 系语言共性，非 Verilog
  特定）；语言包可显式覆盖（verilog `_style.toml` 保留自描述）。

### A7. `transform/normalizer.py` — token 名前缀/字面量名硬编码 ✅ 已处理（2026-08-18）

`literal.` 与 `keyword.`/`symbol.` 同构（token 叶子节点名即 token 类型）——加入
`EXTRACT_PREFIXES`（取自 core.token_protocol.LITERAL_PREFIX），删除 `EXTRACT_NAMES`
具体字面量名列表（语言词法名不进引擎）。

### A8. `linter` 的 `_TRIVIA` — 4 处重复定义 ✅ 已处理（2026-08-18）

集中到 `core/token_protocol.py` 的 `TRIVIA_TOKEN_TYPES`（引擎 token 协议单一事实源），
linter 4 个文件（boundary/matcher/discovery/lookahead）改引用。

### A9. `lexer/lexer_utils.py:91` — 结构性校验隐含语言假设（弱）

```python
missing = [s for s in ("symbol", "space", "newline", "bracket", "id") if s not in td]
```

5 个段名是引擎硬依赖（合理，属引擎协议）；但**"必须有非空 `[id.keyword]` 关键字表"**
隐含"语言必须有关键字"的假设——纯符号语言（如 Lisp 式）没有关键字会 fail-fast。弱渗透，
记录备查。

---

## B 类：可推导/冗余的配置（statement_entry 同类）

### B1. `end_case` 大面积重复 ✅ 已处理（2026-08-18，收敛范围比初判小）

摸底后修正初判：真实模式是**三分类**，不是"newline 占绝大多数"——
①块规则 `[endX, newline]`（block_end 之外额外声明）②分号收尾规则 `[semicolon]`
（wrap 修复刻意**去掉** newline）③容器/循环规则 `[newline]`。盲目推导 newline 会
复活折行/else-chain bug，故推导**只取 production 末尾纯字面 token，不注入 newline**。

实施：
- `GrammarRule.effective_end_case`：显式声明优先；未声明的语句规则从 production 末尾
  纯字面 token（非 @call/(choice/无后缀，非 trivia）推导，容器/无字面结尾推导空
  （与 IfBlock/IfStmt 的结构定界一致，无需显式 []）。
- 消费点全部切换：parser `check_end_case`/`_get_block_end_for`/pratt `stop_tokens`、
  block_parser `_get_block_end`、linter `build_slice_tree`。
- 机械收敛 8 处声明（assign 3 + wire/reg/integer 3 + localparam/parameter 2——
  声明与推导逐字相同的分号规则）；块规则/`[newline]` 规则保留显式（真实语义决策）。
- 未声明→推导对 c4 同样生效（分号收尾语句规则自动获得推导值），行为等价。

### B2. `skip_types = ["newline", "space.fold"]` — 配置与引擎默认完全相同 ✅ 已处理（2026-08-18）

删 verilog/c4 语言包的显式行，引擎默认承担（parser_core.py 的 declare_cfg 默认值
注释已说明：newline/space.fold 是引擎 token 协议产物，所有语言通用，语言包有特殊
需求可覆盖）。

### B3. `verilog/tpc.toml` 的 `macro_config` 双份声明 ✅ 已处理（2026-08-18）

确认两份声明都指向 base/_macro.toml 全文件且都有消费者（lexer 读 macro_recognition，
preprocessor 读 macro_recognition+directives）。合并为单一 `preprocessor.macro_config`
（宏配置权威归属 preprocessor 段），lexer/main_lexer.py 改 declare 同一 key（注册制
支持多模块共享同一 key，删 `[lexer].macro_config` 行）。

### B4. `config/tpc_config.json` 的 `pipeline.default_test` / `pipeline.stages` — 死配置 ✅ 已处理（2026-08-18）

- `default_test`：无代码消费 → 删除（tpc_config.json + docs/api.md）。
- `pipeline.stages`：唯一引用者是 main.py 死函数 `_load_pipeline_stages`（无调用者）
  → 删函数 + 删配置。`stage` 单值仍被 run_pipeline 消费（存活）。

### B5. `is_atom` 13 处 —— 部分可推导

原子规则形态分两类：
- **纯字面 token 序列**（`Number`=`literal.number`、`StringLit`=`literal.string`、
  `Identifier`=`id`）：production 无任何 @call，可结构推导（全字面 token 即原子）。
- **复杂形态**（`ParenthesizedExpr` 括号包裹、`SelectExpr` 链式后缀、`BitWidthLiteral`
  三 token）：不可安全推导。
- **建议**：只对纯字面形态做默认推导（规则 production 全部是字面 token 且无 @call →
  默认 is_atom），复杂形态保留显式标记。预期收敛约一半（6-7 处）。

### B6. `[commands]` 指令段参数重复 ✅ 已处理（2026-08-18）

指令默认值 = 完整管线（preprocess/lint/parse/analyze/transform/render 全 true +
plugins.formatter=false），指令**只声明差异项**：
- format：`analyze=false, transform=false` + plugins.formatter=true
- lint：`parse/analyze/transform/render=false`
- expand/pipeline：纯默认 + plugins.formatter=true（零显式参数）
- main.py `_resolve_command` 合并默认；未声明指令名 = 纯默认（完整管线）

### B7. `_style.toml` 与引擎默认逐字重复 ✅ 已处理（归 A6）

`children_field` 从 style 移除（引擎协议）；`indent=4`/`max_inline=40` 保留为语言包
自描述（覆盖引擎兜底默认值的权力由语言包持有）。

---

## C 类：引擎约定但缺集中管理（非渗透，属工程卫生）

**已全部处理完毕（2026-08-18）**：

| 约定 | 处理 |
|------|------|
| token 类型命名协议（`keyword.`/`symbol.`/`bracket.l_`/`bracket.r_`/`literal.`/`macro.`） | ✅ 新建 `core/token_protocol.py`（前缀常量 + 构造函数）；lexer/main_lexer、core/utils、transform/normalizer、linter/discovery、linter/scanner、formatter/boundary 全部改引用协议常量 |
| `_find_user_config()` 双实现 | ✅ 抽到 `core/_user_config.py`（仅依赖 os 无循环风险）；core/define.py 与 core/config_registry.py 改为 re-export |
| AST 字段名 `sub_node`/`body` 不对称 | ✅ `CHILDREN_FIELD`/`BODY_FIELD` 协议常量集中到 `core/define.py` Node 类旁；Node.add_sub_node/iter_children、parser/_production、parser/attribute_binder、transform/normalizer、renderer（默认 children_field）统一引用 |

**认定合理、无需处理的项**：marker 协议 `tpc:macro:N`/`tpc:directive:N`（preprocessor↔renderer 内部协议）、`CTX_TOP="top"`（linter 内部约定）、formatter `ScopeKind` 枚举（Verilog 插件内，插件可带语言知识）、`main.py` scaffold 默认 `--lang verilog`（CLI 层默认值）。

---

## 修复优先级建议

| 优先级 | 项 | 理由 |
|--------|-----|------|
| 中 | B5（is_atom 纯字面形态可推导） | 约 6-7 处可收敛，需限制在"纯字面 token 序列"形态 |
| 弱 | A9（关键字表非空校验） | 纯符号语言会 fail-fast，仅记录备查 |

**原则总结**：statement_entry 一役确立的模式——"规则字段/结构自推导 > 集中配置 >
引擎写死"——在本报告中全面适用。A1-A8、B1-B4、B6、B7、C 类已全部处理完毕，剩余
B5（配置收敛类）与 A9（弱记录）。每项改动后跑 667 全测 + e2e 93 + lint 精度基线。

# Gap — C typedef 名强转（G4）：「解析前符号判定」的调查与方案

- 状态：**方案 B 已实施（#49，2026-10-22）**；真实语料 2/7 文件 `parse_ok=True`，
- 状态补充：T2c（#57）已删除 raw 承载/P4 安全网；本文 raw 相关叙述为历史（G4 后实际由解析期符号判定接管）。
  余 5 个 zlib 文件 = **预处理宏展开时序**（新暴露的另案边界，非 G4）
- 关联：`docs/gaps/gap-c-real-corpus.md`（G4 = 真实语料门禁唯一前置）、
  `docs/decisions/0024-two-phase-lint-prescan-retirement.md`（两阶段 lint / pre_scan 退役，
  与本案同属「解析前符号判定」战役）、`docs/gaps/gap-c-semantic-base.md`（⑥ 两套符号系统不合并）、
  `parser/parser_core.py::_ScopeStack`（既有但未接线的解析期作用域栈）

## 目标与判据位置

G4 = **typedef 名强转**（`(T)x` / `(T*)x`）在解析期无法消歧：`(id)` 是"类型名"还是"括号表达式"
只有**符号表**能定（`(a)*b` 在 `a` 为变量时是乘法）。它卡住 C 包阶段 5 的真实语料门禁
（退出判据 5）：7 个真实文件全部 `parse_ok=False`（截断），cJSON 56 条语法诊断主体即此类。

本档只做调查/方案（不动生产代码）；实现分片与判据见末节。

## 现状实测（check 路径 = `ProjectChecker`，即真实语料门禁路径）

最小复现矩阵（`typedef int T;` 前置；check 的 `parse_ok`/`syntax` 计数）：

| # | 形态 | parse_ok | syntax | 说明 |
|---|---|---|---|---|
| 1 | `void f(void){ T *p = (T*)0; }` | ❌ | 1 | 函数内声明 + 指针强转初值 |
| 2 | `void f(void){ T x = (T)y; }` | ✅ | 0 | 解析期符号判定直接建树（#49） |
| 3 | `T f(void){ return (T)x; }` | ❌ | 1 | 关键字语句（return） |
| 4 | `void f(void){ if ((T)x) y; }` | ❌ | 1 | 关键字语句（if） |
| 5 | `void f(void){ for (T i=0; i<(T)n; i++) { } }` | ❌ | 1 | 关键字语句（for） |
| 6 | `static T *gp = (T*)0;` | ❌ | 1 | 文件域声明 |
| 7 | `void f(void){ x = (T)y; }` | ✅ | 0 | 解析期符号判定直接建树（#49） |
| 8 | `void f(void){ g((T)0); }` | ✅ | 0 | 解析期符号判定直接建树（#49） |

真实语料（check 路径，当前基线）：**7/7 文件 `parse_ok=False`**；syntax 计数
cJSON 56 / zutil 7 / crc32 4 / adler32 3 / compress 6 / uncompr 5 / gzread 0（gzread 为
parser 截断而非 lint 报错）。G1/G2/G3 已收口（#44/#45），余量即 G4。

### 为什么现有机制覆盖不到（逐条实测）

1. **M1 资格判定形态窄**：`_type_name_hits` 只认"括号紧邻 `( id )`"；`(T*)` / `(T **)` /
   `(T * const)` 不命中（实测 `T *p = (T*)0;` 位点 warning 为 `symbol_dependent=False`）。
2. **站点面窄**：内部 warning 只在 **id 触发的未收敛语句**位产生；关键字触发的语句
   （`return`/`if`/`for`/…）走 L1 静态前缀决策，**不产生未收敛记录**（实测这些源
   `internal_warnings()==[]`），故没有 raw 位点；文件域声明同理（且关键字触发声明类
   规则被 `raw_exclude_rules` 排除）。
3. **符号门是错的来源**：M1 要求 `名字 ∈ pre_scan ∧ kind ∈ {typedef}`。真实语料里
   `typedef struct cJSON { … } cJSON;` 是**多行 typedef**，pre_scan 的"分号前末词"只捕到
   `struct cJSON` 的 **tag_struct**（不是 typedef 命名空间）⇒ cJSON 的 `cJSON` 永远不命中，
   即使形态/站点扩展也无用（实测：monkeypatch 放宽形态 + 去掉符号门后，最小多行 typedef
   用例与 cJSON 风格函数可 parse_ok，但 cJSON 文件仍 55 条——因为主体在关键字语句位）。
4. **raw 的展开路径限制（pipeline 路径）**：`_stage_parse` 只在 `lint_source == source`
   时接 raw；真实文件有 include/宏 ⇒ 不同源 ⇒ pipeline 路径 raw 关闭（check 路径 lint/parse
   同源，不受此限——所以门禁路径可走 raw，渲染路径不可）。

### 既有可复用件（说明为什么不是"从零造"）

- 解析期作用域栈 **已实现且未被使用**：`parser/parser_core.py::_ScopeStack` 有
  `register/lookup/snapshot/restore`（回滚含同深度撤销，判据 `test_symbol_rollback.py`）；
  `parser/_production.py::_push_rule_scope` 已支持 `[Rule.parser] scope = {kind=…}` 帧；
  `parser/rule_selector.py::select_candidates` 已预留 `scope_lookup_fn`（当前恒空）。
- 声明式捕获形态可复用：analyzer 侧 `[Rule.analyzer.c_symbol_collect]` 的路径式 capture
  已证明"语言知识在 TOML、引擎只走路径"的形态可落地。
- 分析期权威符号面（P1）与 E002/E003 安全网成熟——可作为判据对照，也可作为 raw 过渡方案的兜底面。

## 方案

### B（推荐，已实施 #49）parser 内符号表 + 规则符号门控（单遍「解析前符号判定」）

C 的声明先于使用 ⇒ 解析是**源序单遍**，解析到 `(` 时此前声明的 typedef 名已可查；
无需两遍解析。缺的是三块**引擎通用能力**（都不含语言知识）：

1. **声明式注册**：`[Rule.parser] register = { … }`——规则匹配成功后按路径取声明名与
   kind 注册进 `_ScopeStack`（路径形态与 analyzer capture 同族；何时注册 = 规则完成时；
   回溯由既有 `_ScopeStack` 日志回滚）。
2. **作用域帧落 C 包**：`[FuncDef.parser] scope = {kind="function"}`、块规则
   `scope = {kind="block"}` 等（引擎已支持，仅 C 包未声明）。
3. **规则符号门控**：`[Rule.parser] requires_symbol = "type_name"`——候选规则（含 atom
   候选）在尝试前查首 token 的 `_ScopeStack.lookup`，kind 命中包声明命名空间集合才可用；
   包声明面如 `[parser.symbol_namespaces] type_name = ["typedef"]`。

C 包改动：`CastTypeName` 增 `@TypedefName` 分支 + `requires_symbol = "type_name"`；
Declaration/ParamDecl 等按语法声明注册 typedef 名（以及变量/参数 kind，供遮蔽正确性）；
`(T*)` 由既有 Pointer 规则自然覆盖。**随后删除 parser 的 pre_scan hints 依赖**
（与 ADR-0024 的 pre_scan 退役合并）。

优点：AST 正确（不是 raw 猜测）；check 与 pipeline 同解（不依赖 lint/parse 同源）；
无 raw 面扩大、lint-only 不需语义回退；与"解析前符号判定"命名一致。
代价/风险：引擎契约扩展（框架级，需拍板 + ADR）；回溯/作用域正确性（既有基础设施 + 测试）；
宏展开后的 token 流上注册照样成立（声明可见）；全语言回归面（verilog A/B 必须 0/144）。

### A（备选，过渡）扩展 raw/两阶段

符号无关 M1（任意括号内 id 试替换）+ 形态扩 `(T*)` + 站点扩关键字语句/文件域 + 文件域与
展开路径承载；analyze 用精确符号表裁决与 E002/E003。实测原型：形态放宽 + 去符号门可修
最小 1/2/7/8 类与 cJSON 风格函数，但**关键字语句/文件域**仍需站点面扩展；且 AST 大段 raw
（未分析）、lint-only 语义变化、pipeline 展开路径要另做映射——与"解析前"方向相反。
仅当 B 被否/超预算时作过渡。

### C/D（否）

- C 表达式级 raw 原子：parser/Pratt 改动大、AST 仍是 raw 近似；B 覆盖后无必要。
- D 两遍解析：C 声明先于使用，单遍已够；多一遍无收益；否。

## 实施记录（#49，2026-10-22，方案 B）

**引擎（语言无关）**：`parser/parser_core.py::_ScopeStack` 接线——
`_symbol_gate`（`[Rule.parser] requires_symbol = {namespace, skip}`：首标识符的
`_ScopeStack.lookup` kind 须 ∈ `[parser] symbol_namespaces.<namespace>`）+
`_register_symbols`（`[Rule.parser] register = [{name_path|name_paths, kind,
when_marker?}]`，按序取首个 marker 命中者；回溯由既有作用域日志回滚）；
`grammar/grammar_rule_fields.md` 同步登记这两个解析字段。

**C 包**：`[parser] symbol_namespaces = { type_name = ["typedef"] }`；
`CastExpr` 类型名两支 = `@CastTypeName|@CastTypedefName`（新规则
`CastTypedefName` = 限定符* + `@TypedefName` + SpecRest* + 指针*，
`requires_symbol = {namespace="type_name", skip=[const/volatile/restrict]}`）；
`Declaration` 注册 typedef/function/variable 名、`ParamDecl` 注册形参、
`FuncDef` 注册函数名 + 函数作用域帧、`CompoundStmt` 块作用域帧。
顺带修 `else` 前独占行注释：`IfStmt` 的 `(keyword.else,@Stmt)?` 内联组改为
独立规则 `ElseClause`（规则边界才会跳过前导注释；内联组挡注释导致 cJSON
`parse_string` 函数体截断）——新增渲染布局，`render_coverage` 124/124。

**判据结果**：最小矩阵 **8/8 `parse_ok=True`**（check 与 pipeline 双路径）；
新增 `tests/languages/c/test_c_typedef_cast_symbols.py` 22 例（含反例 `(a)*b`
乘法/遮蔽/后置使用/tag 名）；C 套件 1237 passed；A/B verilog **0/144**；
lint accuracy 33/33 fp0；`render_coverage` 124/124；`c_acceptance` 49/0；
变异 118/118（新增 register 去掉、门控失效两条，均实测变红）。
真实语料：cJSON、gzread `parse_ok=True` syntax=0；zutil/crc32/adler32/
compress/uncompr 仍 `parse_ok=False`（余 = `gzgetc` 等**函数宏被应用到定义前
的原型**——预处理展开时序近似，非 G4；已登记 TODO 1.3，另轮修复）。

**参数变化登记**：linter 无解析期符号表，typedef 强转在 linter 侧由启发式
（CastTypedefName 可用）收敛 ⇒ 旧的 M1/raw 资格证据面（`test_linter_raw_
eligibility`、`test_linter_symbol_hints`、`test_linter_lookahead::test_no_full_
match_recorded`、`test_raw_corpus`、`test_parser_raw_site`）**67 条已 skip 登记**
（理由 = G4 后该面退役）；raw 机制本体（含其测试）随 pre_scan 专项整治
（ADR-0024）重建或删除，不在本轮回退。

## 判据草案（B 实施轮）

1. **最小矩阵**：上表 8 条全部 `parse_ok=True`；新增反例——`int a; x=(a)*b;` 仍按乘法
   （不得读成强转）、块内 `int T;` 遮蔽后 `(T)y` 不得按强转、typedef 后置使用（C 非法）
   不得按强转；`(T*)`/`(T **)`/限定符形态。
2. **真实语料**：7 文件 check `parse_ok=True`（含 stubs/include）；syntax 计数归零（或仅
   登记的非 G4 类——当前无）；cJSON 56→0；门禁可上（#49+，`eval_diag_baseline_c.py` +
   `tests/policy`）。
3. **双路径**：`tpc check` 与 pipeline（render）对同一矩阵都给 `parse_ok`/渲染保真；
   不再要求 lint/parse 同源。
4. **零回归**：A/B verilog 0/144；lint accuracy 33/33、fp 0；全量套件；pyright 0；
   变异：去 register、去 requires_symbol、去 scope 帧、去 CastTypeName 分支 ⇒ 各自变红。
5. **收口**：parser pre_symbols/pre_hints 与 `[pre_scan] rule_hints` 删除（ADR-0024 S4 前移）；
   文档（parser README / 规则字段 / C README）与测试同步。

## 预算与止损

- 分片：B1 引擎（register + 门控 + 包命名空间配置，含单测）→ B2 C 包接线与最小矩阵 →
  B3 真实语料 + 门禁 + 退役 pre_scan hints（可与专项整治共享）。
- 预算：B1+B2 两轮内；每轮全量验证。
- **止损**：若 B 两轮仍无法保持 verilog A/B 0/144 或回归面不可控 ⇒ 回退到 A（过渡 raw）
  并把 G4 拆为"门禁可上（raw 过渡）+ parser 符号表专项"两步，如实登记差距。

## 决策点（已拍板并实施）

- 作者 2026-10-22 拍板：走 **B**（parser 内符号表）且**同批删除 parser 侧 pre_scan 残面**。
  引擎契约面（`register`/`requires_symbol`/`symbol_namespaces`）随之落地；parser
  `pre_symbols`/`pre_hints`/`[pre_scan] rule_hints` 消费面删除（零消费，A/B 0/144）。

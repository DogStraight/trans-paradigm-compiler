# ADR-0024: 退役 lexer 预扫描——raw 资格符号无关化，符号判定后移 analyze

- Status: deferred（暂缓；**刻度主线完成后作专项整治，集中力量处理**）
  · #49 已删除 **parser 侧**的预扫描消费面（`pre_symbols`/`pre_hints`/`rule_hints`，
    零消费、A/B 0/144）；linter 侧唯一承重面（raw 资格）随本专项处理。
- Date: 2026-10-22（#45 调查轮：作者要求评估 `pre_scan` 存废 → 先出两阶段 lint 设计；
  同日作者拍板"这可能需要专项整治，之后再处理：lexer 做预扫描是耦合设计，先不管此处，
  先把刻度推进完成之后再集中力量去掉这个机制"）
- 关联：`docs/gaps/gap-c-semantic-base.md`（预扫描期 P1 / 决策 ③⑧⑨）、
  `docs/gaps/gap-parser-linter-approximation.md`（M1 资格判定 / raw 承载）、
  `linter/linter_architecture.md`（L1/L2 与内部 warning 面）、
  `docs/decisions/0021-long-term-deferral-strategy.md`（符号表延期策略）

## 背景

`pre_scan` 是 lexer 之后、parser 之前的**文本级正则扫描**（`lexer/pre_scan.py`，产出
`{name: kind}` + 行/列/深度），语义 = 平坦、首见归属、无声明顺序（模块自述"不是精确的"）。
作者判断"lexer 层选出的符号信息量严重不足，宁可延后到分析阶段"；本 ADR 把该判断落成
可执行的两阶段方案，并先查明现状消费面（#45 实测，临时改配置/禁用消费点后跑，已还原）：

| 消费点 | 位置 | 承重？ | 实测 |
|---|---|---|---|
| parser 候选重排（`pre_symbols`+`pre_hints`→`rule_selector`）**已删 #49** | （历史接线，现状已无消费面）arser/parser_core.py:460-512`；`parser/rule_selector.py:144-170`；配置 = verilog `[pre_scan.decl.*].rule_hints` | 否 | 删 verilog `rule_hints` ⇒ A/B **0/144**、verilog 套件全绿、无测试引用；C 包未声明 |
| linter raw 资格（唯一承重） | `linter/scanner.py:343-357,465-495`；`linter/lookahead.py:434-506,1036-1147`（①替换试解析 ②kind 过滤 ③先后/深度 ④raw 互斥）→ `symbol_dependent/eligible` → M2 摘诊断 `scanner.py:420-450` + parser raw 承载 | **是** | 禁用符号 → 合法 `x=(myint)y;` 由 0 诊断变 1 误报、parse 截断；`tests/languages/c` 9 红（raw 理解面）、linter 定向套件 33 红 |
| C 产物"两期"（`PHASE_PRE_SCAN`/`two_phase_product`/`pre_scan_records`） | `grammar/c/plugins/semantics/_api.py:473-533` | 否 | 管线无消费者（`build_product` 只出 analyze 一期；仅测试+文档引用） |
| `raw_exclude_rules`（raw 互斥规则名） | `linter/scanner.py:465-474` 借 `lexer.pre_scan` 配置段读取 | 半（语义非符号） | 可迁 linter 自有配置面 |
| 机制自身 | `lexer/pre_scan.py`、`lexer/__init__`、`core/global_state.py:145`、`core/engine_capabilities.py:39`、`pipeline` import、`analyzer/structure.py:317-329`、2 包 `_pre_scan.toml` | 随机制删 | 全仓提及 37 文件 / 236 行（含少量同名但无关的 formatter `pre_scan_passes`） |

**问题本质**：M1 需要"这个 id 是不是 typedef 名"这类**符号**信息，而符号表在 analyze 期才权威；
管线顺序 lint→parse→analyze 决定单遍实现无法在 lint 前拿到它，pre_scan 是临时折中。既有的
raw 安全网已经把"符号校验"放在 analyze 期（`analyzer/primitives/_raw_validate.py::validate_raw_statement`，
E002：作用域/声明序/深度精确；`_raw_understand`：E003 一致性；`_raw_transform`：提升），
因此**唯一要改的是"资格判定"这一层**：从"符号相关（名字在预扫描表且 kind=typedef）"改为
"符号无关（双读试解析）"，把符号判断整体后移。

## 决策

### 1. 两阶段裁决（符号判定后移 analyze）

- **阶段 A（lint，符号无关）**：未收敛位点改为**双读试解析**——同一句先按常规读（括号内 id
  作表达式）；失败再按"括号内 id 作类型名形态"替换后重跑同一候选集（替换 token 型由**包声明的
 语法级键**给出，如 `[linter] type_name_form = "keyword.int"`，不再依赖 name→kind）。替换读
  整句通过 ⇒ 该位点为**候选 raw**（带 `candidate_names` = 参与替换的 id 集合；`substitute_type`/
  `trial_rule` 配方面不变）。删除 M1 判据②（`symbol_dependent`/`symbol_names`/kind 过滤），
  保留判据①③④。
- **阶段 B（parse）**：raw 承载通道不变（`raw_sites` 的 region/配方/order → `build_raw_candidate`；
  渲染权威仍是 `_verbatim_text`）。
- **阶段 C（analyze，权威）**：安全网不变——`validate_raw_statement` 用 analyze 产物逐名判
  "此处是不是类型名"（不过 ⇒ E002 报错、不静默）；`_raw_understand` 做一致性（E003）与结构选定；
  `_raw_transform` 提升。**候选名是否真为类型名一律由 analyze 裁决**，linter 不再猜。

### 2. `tpc lint` = 纯语法检查（CLI 分工显式化）

候选 raw 位点在 lint-only 下不再产生 blocking 诊断（M2 摘诊断语义保留），以 `--json` 的
**deferred 候选表**暴露；"接受/拒绝"的最终结论只由 `tpc check`（完整管线）给出。
文档（`main.py` 帮助、`linter/linter_architecture.md`、C 包 README）与 CHANGELOG 明示该分工。

### 3. 退役 `pre_scan` 机制本体（S4 删除，清单固定）

- 引擎：`lexer/pre_scan.py`（`pre_scan`/`pre_scan_with_lines`/`load_pre_scan_config`/`_compile`）、
  `lexer/__init__` 导出、`core/global_state.py` 的 `lexer.pre_scan._CACHE` 键、
  `core/engine_capabilities.py` 能力族串、`pipeline._stage_prescan` 与 `_stage_parse` 的
  `pre_symbols`/`pre_hints` 接线；
- 语言包：`grammar/c/base/_pre_scan.toml`、`grammar/verilog/base/_pre_scan.toml`、两包 `tpc.toml`
  的 `[lexer] pre_scan` 行；
- 消费面（#49 前）：`parser/parser_core.py` 的 `pre_symbols/pre_hints`、`parser/rule_selector.py` 的 hint
  重排、`analyzer/structure.py:317-329`、`grammar/c/plugins/semantics/_api.py` 的
  `two_phase_product`/`pre_scan_records`/`merge_phases`/`phases_for`/`PHASE_PRE_SCAN`；
- `raw_exclude_rules` 迁 linter 自有声明面（`[linter] raw_exclude_rules`，语义不变）；
- 测试/工具/文档同步：`tests/engine/lexer/test_pre_scan_fallback.py`（删）、
  `test_linter_symbol_hints.py`/`test_linter_raw_eligibility.py`（改写）、
  `tests/languages/c/test_c_symbol_collection.py`（分期用例删）、`tools/check_gate_efficacy.py`
  相关变异、6 处 docs、两包 README、`docs/MODEL_INDEX.md` 行。

### 4. 落地分片（每片独立绿、可回滚）

- **S1 配置面（纯加法）**：C 包 `[linter]` 段新增 `type_name_form` 与 `raw_exclude_rules`
  声明键（消费方仍读旧源，双写期零行为变化）。
- **S2 符号无关 M1**：双读试解析替换 name/kind 判据；internal warning 字段改为
  `candidate_names`（删 `symbol_dependent`/`symbol_names`）；M2/raw 承载配方不变；
  补 C 用例矩阵：合法 typedef 强转（lint 无 blocking、check 通过、提升为 `CastExpr`）、
  非 typedef 名（check 报 E002）、遮蔽/声明序（E002）、`(t){1}` 未覆盖边界（静默）。
- **S3 lint/check 分工**：deferred 候选面 + `--json` 字段 + CLI 文档 + e2e expected 更新。
- **S4 删除机制**：按上面清单删；门禁见下"验证"。
- **S5 文档收口**：本 ADR 删除条件 = 两阶段口径已进机制文档（linter/parser README + gap 档）且
  gap-c-semantic-base 预扫描期条目删除。

### 5. 不改

analyze 安全网（E002/E003）语义、raw 渲染权威（`_verbatim_text`）、候选 raw 的 region 等式
重定位与同源条件。verilog 无 `type_name` 声明 ⇒ 删除其 pre_scan **零行为变化**（A/B 0/144 实测）。

## 权衡

**得到**：符号判定收敛到 analyze 一处（单一真相）；linter 不再做文本级符号猜测；删除一个
引擎机制 + 两包配置（全仓 37 文件/236 行提及面）；`(myint)x` 类合法代码的接受/拒绝由**精确
作用域/声明序**裁决（E002 语义诊断优于语法报错）。

**付出 / 风险**：

1. **lint-only 语义变化**（最大）：`tpc lint` 从"能替符号相关合法代码遮噪"变为"纯语法检查 +
   deferred 候选"；非 typedef 的强转形态（`x=(y)z;`，y 非 typedef）不再在 lint 阶段 blocking，
   改由 `check` 的 E002 报。CLI 分工变化必须进 README/CHANGELOG。
2. **候选面扩大**：符号无关双读会把"常规读失败且替换读通过"的所有位点当候选（此前仅预扫描
   名命中）⇒ raw 承载/analyze 校验量上升。需在 C 语料实测 lint 时延与提升率；若某形态 raw 率
   异常上升，收窄双读条件（限定语句/子句边界、括号内 id 后必须接非运算符 token 等）并回写本档。
3. **诊断码迁移**：`(y)z;` 类从 linter 语法诊断变为 E002（码/位置/消息变化），e2e expected
   一次性更新并登记。
4. **试解析成本**：未收敛位点逐候选名试解析（此前只试预扫描名），最坏 O(位点 × 括号内 id 数)；
   以 C 语料/大文件实测设阈值（沿用 `pre_scan` 面曾护的性能指标：`tpc lint` 不劣化）。
5. S4 是**删除**提交：一旦删除不可局部回滚（回滚 = revert 该提交）；S1–S3 双写期可逐片回滚。

**被否备选**：

- **保留最小 pre_scan（只服务 linter）**：作者否——lexer 层信息量不足；且与"符号判定单一真相"
  冲突。
- **全删 + 接受 C raw 能力回退**：9+33 测试回退、真实 C 语料误报增长（cJSON/zlib 大量 typedef
  强转）作废；否。
- **linter 直接读 analyzer 表**：管线顺序不允许（analyze 在 parse 之后），循环依赖；否。
- **只删 parser 提示 + 两期产物（部分清理）**：S1 价值保留，但不解决唯一承重消费点；只能作为
  过渡步骤，不作为终局。

## 验证（分片判据，全部要有"改前红/改后绿"）

- **S2**：C raw 用例矩阵（合法提升/非 typedef E002/遮蔽 E002/声明序 E002/复合字面量静默）；
  `tests/engine/linter`、`tests/engine/pipeline/test_lint_internal_warnings.py`、
  `tests/languages/c` 全绿；`tpc lint` 与 `tpc check` 两路径对同一输入给同类诊断（A2 口径）。
- **S3**：`python tests/e2e/eval_lint_accuracy.py`（verilog 语料）**err 33/33、valid fp 0**；
  e2e lint 期望表更新；`--json` deferred 字段有正/负例断言。
- **S4**：全量 `pytest tests/`（当前基线 4376 passed / 7 skipped）全绿；
  `python tools/ab_pipeline_compare.py --mode cli --products` **0/144**（S2、S4 各跑）；
  `python tools/c_acceptance.py` **49/0** 不变；C 真实语料探针（`%TEMP%` 未入库）诊断数
  不增加（当前 cJSON 56 / zutil 27 等，见 `docs/gaps/gap-c-real-corpus.md`）；
  引擎/语言包内 `grep -r "pre_scan"` = 0（docs 历史说明除外）；pyright strict 0；
  `render_coverage` 100% 不变；`tools/check_gate_efficacy.py` 变异表同步（删除/改写相关条）。
- **回滚**：S4 单提交整体 revert；S1–S3 不删旧机制，回滚单片即可。

> Impl（现状 + S2 改造点）：`linter/lookahead.py::_record_convergence`（M1①③④）、
> `linter/scanner.py::_apply_narrow_downgrade`（M2 摘诊断）、`parser/block_parser.py::build_raw_candidate`
> （raw 承载）、`analyzer/primitives/_raw_validate.py::validate_raw_statement`（E002 安全网）、
> `grammar/c/plugins/semantics/_raw_understand.py::run_raw_understanding`（E003）、
> `grammar/c/plugins/semantics/_raw_transform.py::process`（提升）
> Test：`tests/engine/linter/test_linter_raw_eligibility.py`、`tests/engine/linter/test_linter_symbol_hints.py`、
> `tests/engine/pipeline/test_lint_internal_warnings.py`、`tests/languages/c/test_c_raw_understanding.py`、
> `tests/e2e/eval_lint_accuracy.py`、`tests/engine/parser/test_parser_raw_site.py`

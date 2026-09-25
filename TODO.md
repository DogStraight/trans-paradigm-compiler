# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## 0.1.3 立项（2026-09-25）

> 两条工作线。**先立档后动手**；每阶段独立验证（部件测试 + 门禁 + 全量 + 真实语料）
> 并本地提交。
>
> **已定案（2026-09-25，作者）**：
> ① 载体 = **新建 `grammar/c/`**，`c4` 保持"从零搭语言模板 + 语言无关性验证"定位不动；
> ② 0.1.3 交付边界 = **阶段 0–3**（勘察定界 → 词法 → 表达式/语句 → 结构类型与作用域），
>    预处理器（阶段 4）**单独立项**评估；
> ③ 议题 2 **首步 = 度量先行**（不先拿数字定位最贵的登记点，后面的收敛就是猜）；
> ④ 议题 2 **最终形态 = 两者都做**：单一注册点清单（P-A）+ 能力清单协商（P-C）。
> 三步做完**建 ADR** 并把机制写进机制文档（步 4）。

### WS1 C 语言包：核心基线起步（形态已定调，见 `ROADMAP.md`「C 语言包」）

> **形态不需要再议**（2026-08-29 已定调）：`grammar/c/` 核心基线 ≈ c99 语法面，
> c11 / c17 / c23 各自是**增量插件**，`requires` 链表达标准包含关系——即
> "按版本号做增量插件"，与作者设想一致。ROADMAP 该条的触发条件（"核心基线立项"）
> 现已满足，故本体移回本节；`c11`/`c17`/`c23` 与注入机制前置仍留在 ROADMAP。

- [ ] **阶段 0 勘察与定界**：读 `grammar/c4`（从零搭语言的子集起步）+ `grammar/verilog`
      两套形态，产出 `grammar/c/` 的分层草案（哪些进核心基线、哪些进 c11+），
      并定"核心基线接受域"的可测清单（对标 C99 语法产生式，逐条标注做/不做/延后）
- [x] **阶段 1 c99 核心基线（词法 + 声明/声明符）——已完成**（`grammar/c/`：
      `tpc.toml` / `base/_token|_lexer|_number` / `token.toml`（C99 全 37 关键字）/
      `00_expressions.toml`（叶子 `Identifier`）/ `01_declarations.toml`（翻译单元 +
      声明 + 说明符序列 + 声明符：多级指针 / 数组 / 函数后缀 / 括号声明符 / 参数表）。
      验收 `tests/languages/c` **20 passed**（正样本 15 含函数指针递归、逗号列表、
      多词说明符、typedef；负样本 5）。
      ⚠ **根因教训（写包必看，已入缺口档「包作者须知」）**：`Identifier` 这类叶子规则
      **引擎不内置**，语言包必须自带（c4/yaml/verilog 各一份）。漏定义时症状是
      `match_length 0` / `expected ';' got 'id'`，**看起来像规则形态问题**——本轮为此
      证伪了五个形态假设才定位到"规则缺失"。
      **未落**：整数后缀与浮点字面量（阶段 1b）、字符/字符串转义表。
- [x] **阶段 2a 类型说明符——已完成**：`grammar/c/02_types.toml`（struct/union 带标签与
      匿名、enum 含带值枚举项、成员声明、typedef 名作类型）+ `tests/languages/c/test_c_types.py`
      12 例；`Declaration` 声明符列表改可选（C99 §6.7 语法如此——"至少声明一个声明符/
      标签/枚举项"是**语义约束** §6.7p2，归语义层）。顺带修两个真 bug（token 键重复
      导致 `symbol.base.equal` 静默失配、字面量正则过度转义导致数字从不被识别），
      两条坑记入缺口档「阶段 2a 的两条实测坑」。
- [ ] **跨语言检查规则泄漏（本轮真实语料工作发现，可复现）**：同一进程里**先跑过
      verilog linter**，再 `load_language("grammar/c")` 扫 C 源，结果多出 **1 条
      `ST003`**（verilog 检查规则残留；C 包自身无 `rules/`）。症状 = **检查结果依赖
      测试顺序**，与 `tests/README.md` 记录的"多语言同进程串味"同类，属 `core/global_state`
      / 语言作用域面。复现：先 `LinterScanner(rules_dir="grammar/verilog").scan("module m(); endmodule")`
      再切 C 扫 `tests/languages/c/samples/ring_buffer.c`。判据：同一份 C 源在"先跑过
      verilog"与"干净进程"下诊断集合相同。回归守：
      `tests/languages/c/test_c_corpus_impl.py::test_linter_gap_is_recorded`（非 phase 码
      白名单目前只允许 ST003，修复后应改为"无非 phase 码"）。
- [ ] **C 包 linter 误报修正（引擎侧归因先行）**：合法头文件
      `tests/languages/c/samples/ring_buffer.h` 上 linter 报 **17 条**误报，四类构造函数
      （带体类型说明符 / 成员数组后缀 / 带括号声明符 / 枚举体 `=`）——解析侧正常，
      故是 linter 跟不上 C 的声明形态。**归因已完成（2026-09-25，两个不同机制）**：
      ① 机制 A `linter/checkers/matcher.py::_match_token` 严格逐 token 匹配**不回溯**
      ——规则内部的可选分支（`StructSpecifier` 的 `@StructBody?`）不被尝试，覆盖
      `{`/`[`/`(` 三类 15 条；② 机制 B `lookahead.classify()` 对 `enum` 开头返回空候选
      → `discovery.py::_record_unrecognized`，覆盖 2 条（`struct` 同源却有候选，推导
      只覆盖一支）。修点/判据/包侧兜底见缺口档同节；
      现状与逐条构造记 `docs/gaps/gap-parser-linter-approximation.md`「C 语言包暴露的
      语句发现缺口」，回归由 `test_c_corpus.py::test_linter_gap_is_recorded_not_hidden`
      反向守（缺口修复后该用例会失败并提醒复核文档）。
- [ ] **阶段 2b/3**：位域、初始化器（含指示符）、数组长度常量表达式、函数体与语句、
      表达式族、整型后缀与浮点字面量、字符/字符串转义表
- [x] **阶段 3 Layer A+B——已完成**（自做，分层落地各带测试）：
      **Layer A** = 原子（Number/StringLiteral/Identifier/ParenthesizedExpr）+
      PrimaryExpr 选择器 + Expression 入口 + 最小语句（CompoundStmt/ExprStmt/
      EmptyStmt/ReturnStmt/Stmt 选择器）+ FuncDef（原型与定义靠 `{` vs `;` 区分）；
      **Layer B** = 运算符表 `base/_operator.toml`（40 项，C99 §6.5 优先级/结合性/
      一元位置；有意不含逗号运算符——它在实参表与枚举体里是分隔符）+ `operator_defs`
      + UnaryExpr（前缀 first set）。测试 `test_c_statements.py` 14 例 +
      `test_c_expressions.py` 22 例（断言**树形**：乘高于加、加减高于移位、相等高于
      按位与、&& 高于 ||、赋值右结合、减法左结合、6 前缀 + 2 后缀一元、三目嵌赋值…）。
      ✅ **关键形态约束（已记入 `grammar/c/00_expressions.toml` 头注）**：表达式环必须
      同时满足 ① 原子 `is_atom = true`；② `Expression`/`UnaryExpr` 标 `pratt = true`；
      ③ 选择器 `PrimaryExpr` 标 `inline = true` 且 production 为**单条交替**——缺任一项
      即 `setup_grammar` 报 `RecursionError`（FIRST/nullable 推导遇环溢出）。
      上一轮委派尝试（产物存 `_drafts/stage3_wip/`）正是缺这些标记而失败；
      照 c4 验证过的形态重做后**一次通过**。
- [x] **阶段 3 Layer B2+C——已完成**：
      **B2 后缀链** = `CallExpr`（`f(a, b)` / `f()`）/ `IndexExpr`（`a[i][j]`）/
      `MemberExpr`（`a.b` / `p->q`）/ `ArgumentList`——三个后缀形态均 `is_atom`
      （内部含 `@Expression`，环只能在原子规则里被 pratt 截断）；
      **C 控制流** = `IfStmt`（含 else）/ `WhileStmt` / `DoWhileStmt` / `ForStmt`
      （三段全可省，`for (;;)` 合法）/ `SwitchStmt` / `CaseLabel` / `DefaultLabel` /
      `BreakStmt` / `ContinueStmt` / `GotoStmt` / `LabelStmt`，`Stmt` 选择器扩到 15 分支。
      测试：`test_c_postfix.py` 13 例、`test_c_control_flow.py` 19 例（断言结构与**顺序**，
      不只"能解析"）。
      ⚠ **两条"未支持即报错"的边界由测试守住**（防"看起来支持"）：`f(a)[i]` 链式后缀、
      `for (int i = 0; …)` 声明式初值（后者需初始化器 → 阶段 2b）。
      ⚠ 踩坑（已记入测试注释）：inline 交替选择器与可选位命中规则分支时会套一层 `seq`，
      且 `seq` 子节点里既有 token 也有规则节点——解包要挑规则节点（`_unwrap` 助手）。
- [x] **阶段 3 全部层级完成**（Layer A 原子/入口/最小语句/函数定义 → B 运算符表与优先级
      → B2 后缀链 → C 控制流）。C 包核心基线现已可解析：声明 / 类型说明符（含
      struct/union/enum 与 typedef 名）/ 函数原型与定义 / 完整表达式优先级 /
      后缀链 / 控制流。
- [x] **真实语料扩容——已完成**：`samples/ring_buffer.h`（声明面，1 注释 + 11 声明）+
      `samples/ring_buffer.c`（实现面，2 注释 + 8 声明 + 8 函数，含控制流/表达式/调用/
      指示符初始化/`sizeof`），两个语料测试 + linter 缺口反向守（`_RECORDED_PHASE_GAP = 7`）。
- [ ] **阶段 2b 词法与类型剩余**：
      · **整型后缀（U/L/LL）**——`[[number.based]]` schema 无后缀字段，修法与判据见缺口档
        「C 包词法面暴露的配置表达力缺口」（倾向扩 schema，不新增阶段）；
      · 前导点浮点 `.5`、字符串内**转义引号**（delim 捕获不识别转义）——同上节记录；
      · 强制转换 `(T)x`（与 `(expr)` 的区分需类型名知识，归语义层同批）、复合字面量、
        链式后缀（`a.b.c` / `f(x)[i]`）、`_Alignof`、作用域与类型语义（语义层）。
      ⚠ **round 26 实测：按清单实施后档位未按预期切换**——同一进程内依次
      `enabled=["c11"]` → `enabled=[]` 时，第二档仍解析出 `StaticAssertDecl`
      （说明还有一处缓存或自动发现路径绕过了 `enabled`；`_ensure_entries_for` 的
      `_entries_source` 缓存键已按清单改为含 `enabled` 仍不生效）。
      已**回退引擎改动**（不留未经验证的改动），本项待重新归因：
      先确认 `load_all` 之外还有谁在提供 `[lexer] token_ext`（候选：`Lexer` 侧按
      `ext_dirs` 自行读插件、或 `_resolve_cached` 的 `_resolve_cache`）。
      **当前可用方案仍是 pack 副本**（`test_c_standard_tiers.py`，已通过）。
- [ ] **引擎级 `enabled` 覆盖参数**（把"档位对照需 pack 副本"变成一等参数）：
      目标 = `load_language(pack, plugins_dir=…, enabled=["c11"])` 显式指定启用组合。
      **逐处清单已核实（`core/config_registry.py`，一次可做完）**：
        1 `_plugin_declarations(…, enabled=None)`——`None` 时仍读 `meta["plugins"]["enabled"]`；
          显式给出时用它并校验为字符串列表（非法即 ConfigError）。
        2 `_load_meta_declarations(grammar_dir="", enabled=None)`——透传。
        3 `_ensure_entries_for(cls, rules_dir, enabled=None)`——透传；**缓存键
          `cls._entries_source` 须由 `candidate` 改为 `(candidate, tuple(enabled)…)`**，
          否则切档复用上一档声明（症状：改了 enabled 毫无变化 = 静默失效）。
        4 `load_language(…, enabled=None)`——透传给 `_ensure_entries_for` 与 `load_all`。
        5 `load_all(…, enabled=None, **base_dirs)`——体内 `_ensure_entries_for(rules_dir)`
          要带 `enabled`；`_resolve` 的 `cache_key`（约 681 行）**也要加** `tuple(enabled)…`
          ——同一类缓存陷阱，两处都得改。
      ⚠ 签名锚点：`load_all` 是 `**base_dirs: str,\n    ) -> None:`（不是 `):`）。
      改完必须用 `test_c_standard_tiers.py` 的**三档断言**验证（它按"解析成哪个节点"判据，
      能直接抓出缓存串档）。⚠ 本轮评估后**刻意不动手**：改动不大，但两处缓存键是静默失效点，
      当时剩余上下文不足以在出错后完成验证迭代——故先留这份"逐处已核实"清单。
- [ ] **阶段 3 结构类型与作用域语义**：struct/union/enum（含位域）、标签命名空间、
      作用域与链接（static/extern）、函数原型与定义
- [ ] **阶段 4 预处理器（独立评估，最大难点）**：`#if` 表达式求值、参数化宏、
      `#`/`##`、变参宏 + 条件编译反向映射精度（darkriscv 嵌套位置精度教训在 C 上更严）
- [ ] **阶段 5 标准等效验证**：`[plugins] enabled` 组合 → 语法接受域断言（对标各标准
      语法规范），并接真实 C 语料（先小样本，规模与来源在阶段 0 定）

### WS2 功能散点治理：一处功能、N 处登记 + 上游契约耦合

> 缺口现状与实测证据见 `docs/gaps/gap-feature-scatter.md`（三个痛点 P-A 登记散点 /
> P-B 上游契约耦合 / P-C 兼容只剩粗粒度开关 + 5 条成熟解法路线）。**分步执行**：

- [x] **步 1 度量（不发明机制）——已完成**：`tools/feature_sites.py`（`list` / `--save`
      / `--compare`，判保持登记 `feature_sites_kept.json`，门禁
      `tests/policy/test_feature_sites.py` 守登记可审计）。四族基线：
      `check` 24 实例 / 散点 **56**（中位 2、最大 5）｜`syntax` 7 / **0**（无跨文件登记点，
      只在跨阶段 2–11 文件）｜`capability` 3 / **30**（中位 9、最大 15 = `formatter`）｜
      `config` 14 / **26**。**结论直接定出步 2 目标**：check 族的散点是同一批 6 个文件
      （`core/check_registry.py` + 3 个 e2e 脚本/基线 + `expected.json` + `diag_baseline.json`
      + `semantic_checks.md`）被每条规则反复登记 → 由 `check_registry` 单一来源派生或校验。
      实测与口径见 `docs/gaps/gap-feature-scatter.md`「步 1 实测结果」
- [x] **步 2 试点收敛（机器可读登记点已收敛；散文类为有意接受的边界）**：
      单一来源提取抽成 `tests/_rule_codes.py`（两门禁共用一份实现），新增
      `tests/policy/test_code_registry_sync.py` 校验变异注入器 / 评测基准映射 /
      真实语料基线的码引用；收敛账 `tools/feature_sites_converged.json`（须 reason+source
      指向门禁）+ 反向防滥用门禁（路径真实存在、source 门禁存在、不得空转登记）。
      **预算 56 → 16**（中位 2→1、最大 5→3）。剩余 16 点与接受边界见缺口档「步 2 结果」。
      ⚠ **未做完的**：`eval_check_accuracy.py` docstring 枚举（可改为不枚举 = 真删除）、
      `_check_test.py`、`check_gate_efficacy.py` 接同一门禁、机制文档码表（有意不接校验）
- [x] **步 3 契约协商（P-C）——已完成**：`[engine].uses` 能力清单 +
      `core/engine_capabilities.py` 能力表 + 精确缺项报错；旧 `api` 线**已删**
      （残留由"未知键"拦下）。`uses` 由包清单机械推导，门禁
      `tests/policy/test_engine_capabilities.py` 查漏声明/残留；协商语义（含"未声明的
      能力变化不误伤"）在 `tests/engine/core/test_engine_compat.py`。
      三包清单：c4 5 / verilog 14 / yaml 2。实测与取舍见缺口档「步 3 结果」
- [x] **步 4 定案建 ADR——已完成**：`docs/decisions/0020-feature-scatter-governance.md`
      （D1 度量先行 / D2 单一来源 / D3 校验·派生·接受三分 / D4 契约版本化到能力粒度 /
      D5 不留兼容且收敛声明可审计 / D6 断言分工 + 被拒绝的 5 个备选 + 三步验证证据）。
      机制文档同步：`core/config_lifecycle.md`（包↔引擎契约节改写为能力清单）、
      `core/component_protocol.md`（§1b 精化器能力位，步 3 前已落）。
- [ ] **ADR-0019 退场**（"完成即删"判据已满足：机制已落 `core/component_protocol.md`
      §1b + `analyzer/elaboration/README.md`）。**前置 = 清引用**，已精确盘点（2026-09-25）：
      **54 处 / 28 文件**。构成：
      · **括号内溯源标签**（绝大多数，如 `（ADR-0019 P3-②c-3）` / `（ADR-0019 决策 4
        更正节）` / `（精化产物 `port_decls`，ADR-0019）`）——同一事实在正文里**已经
        内联解释**，标签可整段删除；注意三种写法：全角括号内、逗号后置、以及
        `# 1a) 精化（ADR-0019）：` 这类注释前缀。
      · **裸引用**（少数，如"本文件守 ADR-0019 **P2** 落地的…"、"已按 ADR-0019 迁入"、
        "ADR-0019 的代码落点"）——需改写成"精化协议"+ 机制文档指针，不能只删标签。
      · 分布：`analyzer/` 13、`grammar/verilog/` 18、`tests/engine/analyzer/` 9、
        `docs/`（含 ADR-0019 自身）4、`core/` 3、`tools/` 1。
      ⚠ 顺序：**先清引用 → 再删档**（否则文档里留悬空引用）；删档后跑
      `tests/policy`（文档引用门禁）与全量确认无悬空。
      ⚠ 同批发现并已修一处**陈述过期**：`analyzer/elaboration/README.md` 原写
      "未接线状态（P1）/只新增不接线"，实际 P2–P4 早已接线——已改为「接线（已完成）」。
      ⚠ 本轮（round 7）评估后**刻意不动手**：机械批量改 54 处的句法风险（全角/半角
      括号、逗号后置、注释前缀三种写法混用）高于收益，留给一次专门的、逐类替换 +
      逐文件复核的改动。

> ⚠ 顺序纪律：**步 1 的度量先行**——不先用数字定位"哪一族的哪几个登记点最贵"，
> 后面的收敛就是猜（本仓已有"配置面膨胀"的实证教训，见 `references.md` 数字形态节）。

## 架构：精化（elaboration）部件化 + 插件化（ADR-0019）——**已收口**

> P1–P4 全部完成，含 c-3 消费方去重（`width_check` 改读 `param_override` 产物）与
> **"引擎角色位"机制整体删除**（终态下引擎**一个插件产物都不消费**，机制已无合法值 →
> 按"不留向后兼容"连登记槽一起删）。引擎最小可视单位 = **文件**；引擎侧净减约
> **1000 行**语言知识。定案 / 分期 / 角色位契约表 / 实测踩坑见
> `docs/decisions/0019-elaboration-plugin-protocol.md`（本文件不再复述，完成历史看 git log）。
> 收口时从执行面**析出两项仍未完成**的独立改进（原判据失效，各自需要新判据）：

- **插件侧 AST-first 改写**：搬迁是**逐字**的，技法未变——`grammar/verilog/plugins/
  elaboration/_graph.py::_is_signal_expr`（正则判"简单信号名"）与 `render_subtree`
  渲染后**字符串比较**仍是文本模式。动机已从"消除引擎侧渗透"改为**插件代码质量**，
  故须**自带一套验证**（不再有渗透判据兜底）。
- **引擎侧未声明的取值形态假设**：`[structure.fields]` 只声明**字段名**，引擎仍假设取值在
  `Node.content`（`analyzer/structure.py` 单元名、`analyzer/elaboration/atoms.py`）——
  "形态从哪里取"没进声明面，多形态语言包会撞。归 L1（渗透复审）。


## 语言知识渗透复审与精化基座重设计（2026-09-20 立，长期）

> 作者定调：**近期主线 = Bifrost 审计修复**——**已收口**（2026-09-20 主体 +
> 2026-09-22 收尾：B-C 快照按 A–G 归位、`python-absent-member` 下边界判决、
> 能力族 ④ 变更差分接入流程、草稿区结论分流落正式位）。判据与门限见
> `policy/structural_budget.md`（口径/停止规则/基线）与 `policy/bifrost_audit.md`
> （判据集 + 已知边界 + 重构期用法）；当前基线 **S = 0**（每个命中都有结论；
> 原始量仍在，删 `structural_kept.json` 对应条目即可回滚），登记表完整性由
> `tests/policy/test_structural_kept.py` 守。
> ~~下一项 = 精化基座重构~~ ✅ **已完成**（ADR-0019，见本文件首节）；下方 L2 的**能力
> 边界设计原则**保留（管辖 ADR-0019 范围外的待议面）；L1 渗透复审仍是长期方向、
> 不在近期排期。

### L1 语言知识渗透复审（长期）

- **范围（作者 2026-09-20 指定）**：**重点 analyzer / preprocessor / linter**；
  parser 与 lexer 基本形式化、renderer 主要吃原语、transform 是插槽形式（可能性小）
  ——但**实测校正**：parser 仍有一处分量级渗透（位宽字面量，见下）。
- **判据三条（强弱递减；详见 `docs/gaps/gap-language-penetration.md`）**：
  ① **最小语言包探针**（主判据，行为面）——只加载最小骨架包跑全量测试，仍绿的引擎
     测试 = 普适面（**已做** 2026-09-24：`tools/min_pack_probe.py` + 基线；
     `tests/engine` 仍绿 **1186** 例——数字随测试增删漂移，基线须**串行**重录，
      工具头有纪律说明）；② **声明面缺失探针**（辅助，行为面）——临时删一段
     语言包声明跑测试，仍绿处 = 引擎替声明做事；③ **弱信号面** =
     `tools/lang_penetration.py`（引擎里出现语言包规则/节点名（硬信号）/
     语言对象词作标识符（弱信号，须人工判））。
  ⚠ 三条都只覆盖**被测路径** → 结论只能是"已知渗透面收敛"。
- **首轮实测（2026-09-20，词法/结构面；全表见 gap 档）**
  - **analyzer = 重灾区**（与作者判断一致）：`structure.py` 硬编码 5 个**规则名**
    （`"FuncDecl"/"FuncDeclOld"/"TaskDecl"`、`"ParamDeclStmt"`、`"Declarator"`）
    + 语义名词标识符 **183 处**（端口/实例/信号驱动）；`checker.py` 的 `_signal_graph`/
    `inst_sites`。**均归 L2（精化基座）**——✅ **已随 ADR-0019 P1–P4 迁移或删除**
    （见上节；那 5 个规则名与语义面现全在语言包插件侧）。
  - **parser**：11 处结构名命中全是**引擎表达式树/节点协议名**；原先当渗透的
    `_parse_bit_width_literal` 经**调用计数探针**实测在三语言包下**不可达**（lexer 按
    `[[number.based]]` 捕成单 token，规则的 `Number` 先手接住）→ 实为**冗余第二路径**，
    **已删**（钩子 + 槽位 + 登记条目）。
  - **pipeline**：`__init__.py` 曾按名调语言包的排版步骤（`split_port_close_lines` /
    `split_inst_tail_lines`）→ **已修**：能力面改声明 `pre_scan_passes`（前置文本遍列表）。
  - **linter / preprocessor / lexer / renderer / core / transform**：词法/结构面未发现活渗透
    （linter 的 21 处、renderer 的 18 处、lexer 的 7 处名词命中全是误报；
    `core/_protocol.py` 的 `ATTR_RESOLVED_PORTS` 等是**产物契约键名**，按既定决策留引擎 → 归 L2 重审）。
  - **同名陷阱**：`Root`/`Comment`/`UnaryOp`/`BinaryOp`/`TernaryOp`/`Number`/`Identifier`/
    `MacroCall` 是**引擎表达式树/节点协议**（语言包按此名声明 renderer），不是渗透。
  - ⚠⚠ **新判据（当场踩坑得出）**：弱信号命中要过四道——① 词法命中 → ② 看调用链定性
    → ③ **数调用次数（可达性）** → ④ 才分“渗透 / 死代码 / 契约”。
    只做到 ② 会把**不可达的冗余路径**当渗透，白花一道外置工序（本次实测）。
- **现有的两条门禁只覆盖词法面**（关键字字面量 / 配置键声明），为何抓不到语义渗透：
  用配置键或通用算法表达的 Verilog 语义里**一个 Verilog 词都没有** → 形式完全合规；
  配置点位法反而**奖励**这类渗透。两条门禁答的是"有没有**语言的关键字**"，
  而精化基座的问题是"有没有实现**语言的语义**"——前者是字符串问题，后者是判据问题。
- **下一步**：① 行为面基线（最小语言包探针）——**已做**（2026-09-24，判据 1）；
  ② L2（精化基座重设计）——✅ **已由 ADR-0019 完成**（analyzer 的 5 个规则名 +
  语义面 + 产物契约键名都在那一批里处理完）。**剩余面 = 精化基座之外的渗透复审**
  （判据 ② 声明面缺失探针 / ③ 弱信号面，按需在改动时顺带做），未见排期。
- **另："多加语言包"作为暴露法的代价（已知事实）**：c4/yaml 覆盖浅，暴露力有限；
  且多语言同进程已有真实串味史（`_PIPELINE_SHARED` 按 rules_dir 缓存、
  `global_state` 语言注册面只增不还原、`test_language_switch` 曾偶发失败）→ 该法
  只在隔离跑（每语言一进程）下可用，不作日常手段。
- **状态**：方向已定（作者 2026-09-20），方法待选；未见排期。

### L2 精化基座重设计（引擎 vs 插件的能力边界）

- **作者定调（2026-09-20）**：重设计一次基座，**引擎只留"普适的文件操作 + 树化行为"**；
  把**抽取能力**（从树上取语言结构）与**动态求解**（常量/宽度/端口方向等语义求值）
  移到插件侧。现状是基座把**很多 Verilog 独有的操作在引擎内侧实现了**——作者判定为
  "明显的语义渗透"。
- **设计原则细化（作者 2026-09-20，防止走成"普适化 → 配置面膨胀"）**：
  **自带配置的增量设计**——引擎侧留**占位 + 简单实现**（能跑通最普适形态），
  语言特有的完整实现**集中到语言适配层**；这样配置复杂度与语言知识都落在插件侧，
  插件又靠引擎的原语组合而不必重复造骨架。
  - **三选一别走错**：引擎硬编码（禁） / **引擎配置字段（慎）** / **插件实现（首选）**。
    "为让引擎普适而设计一套 schema"会把复杂度从代码搬到配置，并为新形态预留表达力
    缺口——这是本仓已经踩过的形态（见下面的数字实证）。
  - **两条判据**：① *普适性*：去掉所有语言包声明后，引擎的简单实现能否对任意输入
    给出**可解释**结果？能 → 引擎；不能 → 插件。② *配置 vs 代码*：**能被表单穷举、
    且不涉及算法/状态机/语义求值**的少量变体 → 留配置；需要算法/状态机/求解的 →
    移插件代码。③ *增量*：插件只写"与默认的差"（override / 扩展点），不复制骨架。
  - **取舍的定位（作者 2026-09-20）**：声明式表达一切 ⇒ 配置面无限；不可能。所以做法是
    **把"会变动的结构"做成配置，把"特异的部分"做成语言包代码**——不是消灭取舍，
    而是把取舍**局部化**（每个决定只影响一个组件、可回滚、可被测试锁住）。
  - **把"会变动 vs 特异"变成可判的第三判据（看它在语言间的分布）**：
    | 语言间分布 | 归宿 |
    |---|---|
    | 多语言共有、且形态稳定（只有值不同） | **配置**（值走声明） |
    | 多语言共有、且结构一致（形态相同） | **引擎骨架**（上提，避免各语言复制声明） |
    | 单语言特有，或各语言形态各异 | **插件代码**（下沉） |
  - **两个可机械测的失效信号（用来发现"放错了"）**：① *该上提却还在配置*：同一 schema 下
    多个语言包的声明高度相似（复制粘贴式）→ 说明这是共性结构，应上提为骨架/默认；
    ② *该上提却还重复*：同一段逻辑出现在 ≥2 个语言包，或插件与引擎默认逐字同体
    （Bifrost 重复工具 + 现有 A–C 类判据可测）→ 应上提。两条都是**往返通道**：
    只能单向移动（一味下沉或一味上提）会累积另一种债。
- **普适原语必须共享**（否则各插件重写"跳空白"之类会漂移）：既有 `core/token_protocol`、
    `lexer/lexer_utils`、`core.define.iter_nodes` 已是这类原语，重设计时明确清单。
- **命中点与实证（本仓事实）**：
  - `analyzer/structure.py`：~~引擎侧实现了 generate 条件求值（`_eval_const_expr`/
    `_ConstExprParser`）、端口/参数抽取（`_PortFields`/`ModuleExtractor`）、
    信号图（`SignalGraphBuilder`）~~ → ✅ **已全部随 ADR-0019 P3 迁入语言包**
    （`grammar/verilog/plugins/elaboration/`），`structure.py` 现只剩**文件层**
    （索引 / 发现 / 单文件装配）。
  - **数字形态（配置面膨胀的实证）**：旧 `NumberFSM` 硬编码单例**已不存在**
    （P2.1 配置化时移除，`lexer/main_lexer.py` 有记录）。现状是另一种形态——
    为让引擎普适，`grammar/verilog/base/_number.toml` 用 **7 个字段 × 4 个形态块**
    （`size.digits`/`base_prefix`/`signed`/`bases`/`value_digits`/`value_allow`/
    `value_allow_space`）声明形态，引擎侧 `number_gen._PatternBuilder`（通用 DFA
    构造）+ `number_runner` 把它编译成状态表。**加形态可能撞 schema 表达力边界**，
    这正是"普适化推高配置面"的样本。按新原则应改为：引擎留"十进制/浮点最简扫描"
    占位 + 数字扫描原语（字符类判定 / 最长匹配 / radix 取值），verilog 插件侧
    集中实现位宽·进制·x-z 形态。
  - 正面样板：`typed_ports`（抽取走插件 + TOML 声明，引擎零硬编码）。
- **诚实代价（已写进 ADR-0019 权衡）**：声明式 → 命令式后，**加语言不再是零代码**
  （c4/yaml 需写一小段插件或继承默认）；换来的是引擎 schema 与代码不随语言数增长。
- **已有约束须一并遵守**：语言知识零进代码（AGENTS 硬约束）、不留兼容垫片、
  删除先证后删（`policy/doc-alignment.md`）；配置加载 fail-fast。
- **定案与范围分界**：**精化基座**已由 ADR-0019 定案
  （`docs/decisions/0019-elaboration-plugin-protocol.md`）；**本节保留为通用设计原则**
  （三分法 / 两失效信号 / 普适原语清单 / 成熟解法参照），管辖 ADR-0019 范围外的待议面
  （数字形态 `_number.toml`、analyze→transform 映射通道契约键名）——那些**仍未立项**，
  动手前同样先立 ADR。
- **成熟解法参照（避免自造）**：
  - **GCC 的路线**：语言差异由**手写前端**接住（每个语言一个 front end），共享点在下游
    （GENERIC/GIMPLE IR + 后端 + 目标描述 `.md`）。它的"占位"不在前端骨架，而在
    `LANG_HOOKS`/`TARGET_HOOKS` 回调与机器描述文件——**取舍位置与我们相反**（它把共享点
    下移，我们把共享点上移到前端骨架）。另外 GCC 的机器描述是"配置面膨胀"的成熟解法样本：
    它给配置面配了**领域语言 + 代码生成器/校验器**（`.md` → `genrecog`/`genoutput`/
    `genattrtab`）——可见**配置面本身需要工具链管理**，否则就是纯负担。参照它设计我们的
    TOML→生成器/校验器（`number_gen` 这类"schema + 编译器"在**有生成器**时不算错）。
  - **LLVM**：IR 作为普适中间层的样本（前端/优化/后端三段解耦）。
  - **语言工作台（Xtext/Rascal/MPS）**：元语言 + 生成，与"配置表达式 + 插件补特异"同路线。
  - ⚠ 记录纪律：本仓文档不写"超过 X / 比 X 强"这类**不可验证的比较断言**（AGENTS
    「不拉踩开源作者」+ 对外话术纪律）；可比的是**取舍位置与可审计性**，且要同时写明
    自己的短板（无优化深度、语言规模墙、语义分析浅、单语言选择模型）。

## 语法覆盖：头部参数列表的"续项不带关键字"形态（实测缺口，待决策）

> 来源：ADR-0019 P2 写夹具时实测（2026-09-24）。`grammar/verilog` 当前**只接受每个
> 参数都重复 `parameter`** 的形式：

| 写法 | 实测 |
|---|---|
| `#(parameter W = 8, parameter D = W/2)` | ✅ 解析通过 |
| `#(parameter W = 8, D = 4)` | ❌ 被 linter 阻断（`incomplete structure, expected one of: symbol.base.pound` …） |
| `#(W = 8, D = 4)`（ANSI 风格） | ❌ 同上 |

- **为何值得看**：`#(parameter A = 1, B = 2)` 是真实语料里的常见写法（IEEE 1364-2005
  的 `parameter_port_list` 第一式 `list_of_param_assignments { , parameter_port_declaration }`
  允许多种解释，各工具普遍接受该形态）。0.1.1 目标是"Verilog2005 全量语法包"，
  此形态是否属缺口**需按真实语料定**（本次只在合成夹具上实测，未统计语料命中率）。
- **判据**：先扫真实语料（`tests/e2e/samples/real/`）统计该形态出现次数；有量则补
  语法（`parameter` 关键字可省略的续项），无则记为该目标下的已知取舍。
- 与精化搬迁无关（P2 只是撞上了它并被它挡住，故当时改用可解析形态写夹具）。

## 测试基础设施

- **并行度默认值**：`pyproject.toml` 的 `addopts = "-n auto"` **保持现状**（作者
  2026-09-19 定调“先这样”）。本机跑全量时自行显式传 `-n 4` 规避顶满核（做法与分档
  见 `tests/README.md`「改动节奏分档」）；不改仓库默认。

# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## C 语言包与散点治理：0.1.3 交付后的未完项（2026-11-25 发布）

> 主体已随 0.1.3 发布，完整条目见 `CHANGELOG.md` 的 `[0.1.3]` 段：**WS1** =
> `grammar/c/` 核心基线（≈C99 语法面，接受面 25/27）+ c11/c17/c23 标准增量插件族；
> **WS2** = 散点治理四步 + `docs/decisions/0020-feature-scatter-governance.md`。
> 分层草案、C99 接受域清单与渲染保真现状见
> `docs/gaps/gap-language-pack-scope.md`「C 语言包」节。
>
> **已定案（2026-09-25，作者）**：① 载体 = 新建 `grammar/c/`，`c4` 保持"从零搭语言
> 模板 + 语言无关性验证"定位不动；② 0.1.3 交付边界 = 阶段 0–3，预处理器（阶段 4）
> 单独立项；③ 议题 2 首步 = 度量先行；④ 议题 2 最终形态 = 单一注册点清单（P-A）+
> 能力清单协商（P-C）**两者都做**。
> 本文件只列**未完成**项：完成项的验证在测试套件，历史在 git log。

### WS1 C 语言包

- [ ] **跨语言检查规则泄漏（真实语料工作发现，可复现）**：同一进程里**先跑过
      verilog linter**，再 `load_language("grammar/c")` 扫 C 源，结果多出 **1 条
      `ST003`**（verilog 检查规则残留；C 包自身无 `rules/`）。症状 = **检查结果依赖
      测试顺序**，与 `tests/README.md` 记录的"多语言同进程串味"同类，属 `core/global_state`
      / 语言作用域面。复现：先 `LinterScanner(rules_dir="grammar/verilog").scan("module m(); endmodule")`
      再切 C 扫 `tests/languages/c/samples/ring_buffer.c`。判据：同一份 C 源在"先跑过
      verilog"与"干净进程"下诊断集合相同。回归守：
      `tests/languages/c/test_c_corpus_impl.py::test_linter_reports_no_false_positives`
      （非 phase 码白名单目前只允许 ST003，修复后应改为"无非 phase 码"）。
- [ ] **C 块内诊断粒度粗（每块只报一条，且报文指错位置）**：块内多个错误只报一条
      （实测 `void f(void) { a + ; b + ; }` → 1 条 `expected 'bracket.r_curly_bracket',
      got 'id'`——指向 `b`、说"期望 `}`"，**真错在 `a + ;`**；c4 同位样本 → 2 条精确
      诊断）。成因：`CompoundStmt` 的 `@Stmt*` 由父 checker 内联匹配，而
      `matcher._match_repeat` 遇重复项出错即 `break`（防级联），于是只留第一条且位置
      已被后续元素带偏；块体**没有独立语句节点**（`_discover_block` / `_block_body`
      只对块规则生效）。
      **两条候选修法，各有真实代价（本轮已实测，勿盲选）**：
      · **(A) 包侧：按 c4 `BlockStmt` 形态把 `CompoundStmt` 改成块规则**
        （`is_block = true` + production 只留 `{`/`}` + renderer `role = "flatten"`）——
        **代价已实测**：块体语句的选择随之从"包的 `Stmt` 有序交替"改走
        **引擎的规则选择器序**（`RuleSelector` 按 `statement_rule_names` 排序，C 包里
        `Declaration` 在 `ExprStmt` 之前）⇒ `void f(void) { x; }` 的体内语句从
        `ExprStmt` 变成 `Declaration`（实测三条：`x;` / `b;` → `Declaration`），
        **直接推翻本包刻意选定并写进注释、锁进测试的消歧**（见
        `grammar/c/03_statements.toml` 的 `@Declaration` 必须排在 `@ExprStmt` 之后，
        与 `tests/languages/c/test_c_statements.py::test_expression_statement_in_body`）。
        前置因此是**"包可声明块体语句的候选顺序"**：包侧无此表达面，引擎侧也没暴露
        该开关（`Stmt` 有序交替只作用于 `@Stmt` 引用，块体走 `parse_sentence`）。
      · **(B) 引擎侧：`_match_repeat` 对重复项出错做语句边界恢复**（记下诊断后跳到
        下一个 `_stmt_ends` 继续，而不是 `break`）——不动语法、不给包加约束，但会改变
        **所有语言**在坏输入上的诊断条数与位置，须用 `tests/e2e/eval_lint_accuracy.py`
        （recall 33/33、类别准确率）+ `eval_diag_baseline.py`（真实语料只许减）+
        三包 lint 测试锁住，并按 `policy/` 记录新的近似边界。
      判据（两条共用）：块内每条坏语句各报一条**位置正确**的诊断。
      现状：**刻意不改**——它不影响"合法代码零误报"（本轮已闭环），只是坏输入的诊断
      质量；(A) 会换来另一种已知回归，(B) 的影响面值得单独一轮。
- [ ] **C 包剩余能力面**（词法面已全部闭环；接受面 **32/34**，空洞 2 = 预处理两项）：
      · **预处理两项**（`#include` / `#define`）= 阶段 4——**这是接受面仅剩的空洞**；
      · **标准增量的剩余项**（各档已落地的 9 项见 `grammar/c/README.md`「标准增量插件」；
        ⚠ **共同前置不再是"注入机制"**——2026-09-26 实测更正：现役直接注入就是"往既有
        交替加一支"，c11/c23 已按它落地）：`_Alignas`/`_Atomic`（说明符位设计）、
        `[[属性]]`（声明/语句前缀位点）、c23 无下划线拼写（同构造异拼写，需先定包内
        约定）、`_BitInt`/`_Decimal*`（需定宽度参数与十进制浮点接受域）；
      · **typedef 名起头的强制转换**（`(myint)x`）= 语义层切片 1b（需符号表 / 作用域 /
        声明顺序），草案与判据见 `ROADMAP.md`「C 语义层切片 1b」；
      · 逐声明符位宽（`int a : 3, b : 4;`）——已知边界，标准里位宽属声明符（形态改动）；
      · 结构类型与作用域语义（标签命名空间、链接、声明顺序）。
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
      ⚠ **实测结果（0.1.3 收尾轮）**：按上述清单实施后**档位仍未按预期切换**——同一进程内
      依次 `enabled=["c11"]` → `enabled=[]` 时第二档仍解析出 `StaticAssertDecl`
      （说明还有一处缓存或自动发现路径绕过 `enabled`）。**改动已全部回退**（不留未经验证的
      改动），待重新归因：先确认 `load_all` 之外还有谁在提供 `[lexer] token_ext`
      （候选：`Lexer` 侧按 `ext_dirs` 自行读插件、或 `_resolve_cached` 的 `_resolve_cache`）。
      **当前可用方案仍是 pack 副本**（`test_c_standard_tiers.py`，已通过）；
      改完必须用它的**三档断言**验证（按"解析成哪个节点"判据，能直接抓出缓存串档）。
- [ ] **阶段 3 结构类型与作用域语义**：struct/union/enum（含位域）、标签命名空间、
      作用域与链接（static/extern）、函数原型与定义
- [ ] **阶段 4 预处理器（独立评估，最大难点）**：`#if` 表达式求值、参数化宏、
      `#`/`##`、变参宏 + 条件编译反向映射精度（darkriscv 嵌套位置精度教训在 C 上更严）
- [ ] **阶段 5 标准等效验证**：`[plugins] enabled` 组合 → 语法接受域断言（对标各标准
      语法规范），并接真实 C 语料（先小样本，规模与来源在阶段 0 定）
- [ ] **保真度渲染：分隔符后行尾注释随折行漂移**（引擎侧，可复现）：
      **最小复现（fuzz 链路自动收缩，2026-09-26）**：
      `intrst/* ` + `x`×60 + ` */,second;`（82 字节**单行**）——
      一遍渲染 `intrst, /* x… */\nsecond;`，二遍 `intrst, second /* x… */;`（第 3 遍起收敛
      ⇒ 判据 4 不幂等）。**注释长度 60 是折行阈值**：再短一行就放得下、漂移不出现
      （行内字符级最小化把注释从 60 缩到"恰好仍触发"的长度就是这条）。进入方式：
      `python tests/fuzz/run_fuzz.py --pack grammar/c`（变异很难撞上该形态——4000 轮
      0 findings；该样本是直接喂触发输入造的，见 `tests/fuzz/README.md`「回馈链路」）。
      成因：`parser/_production._attach_line_end` 把"注释后换行"的行尾注释挂
      `context.current_node`——分隔符后的注释在 repeat 组匹配中被吞，此刻是**列表容器**，
      容器 `trailing` 槽渲染在容器**末尾**（越过后续项）；而同一注释在分隔符**之前**时挂的是
      **项**节点 trailing（渲染在该行尾）。候选：① 紧前为符号 token 时改走
      `inline_after[sep]`（join 的分隔符行中通道，落位即源位）——⚠ 残留锚不渲染
      （leftover 回补通道已删），误路由＝丢注释，须逐形态验证；② 挂"刚结束的项节点"
      而非 `current_node`（需引入"最近完成节点"状态）。现状：`edge_comments.c` 用**不折行**的
      短注释绕开该形态（缺口记档，见 `docs/gaps/gap-language-pack-scope.md`
      「C 包渲染/保真面现状」表 #6）。⚠ 修好后跑
      `python tests/fuzz/shrink.py --all --pack grammar/c --sediment <edge 语料> --cause "…"`
      把这条最小复现沉淀成回归（链路已自动化，见 `tests/fuzz/README.md`）。

### WS2 功能散点治理

> 四步（度量 / 单一来源收敛 / 能力清单协商 / 定案建 ADR）已完成，机制见
> `docs/decisions/0020-feature-scatter-governance.md`；以下只留未做完的部分。

- [ ] **步 2 剩余四处（有意保留的边界，非欠账）**：`eval_check_accuracy.py` docstring
      枚举（可改为不枚举 = 真删除）、`_check_test.py`、`check_gate_efficacy.py` 接同一门禁、
      机制文档码表（有意不接校验）
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
      ⚠ 本轮评估后**刻意不动手**：机械批量改 54 处的句法风险（全角/半角括号、逗号后置、
      注释前缀三种写法混用）高于收益，留给一次专门的、逐类替换 + 逐文件复核的改动。

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

- [ ] **`test_check_test_isolation.py::test_compare_reports_isolated_only_failure` 在整仓
      并行满负载下偶发红**（2026-09-26 实测，本轮 3 次整仓 `pytest tests -q -n auto` 中出现
      1 次）：症状 = 工具内层 pytest 报 `Interrupted: 1 error during collection`，
      工具因此返回 **2**（期望 1）→ 断言失败。**单跑该文件、以及 `tests/policy` 整目录跑
      均连绿**（各 2 次），故判定为**负载相关**而非本次改动引入（同一提交前后各一次整仓
      跑：一次红一次绿）。待归因候选：满负载下内层 pytest 收集超时（子进程启动/导入竞争）、
      或临时探针目录与并发子进程的交互。判据：整仓并行跑 N=10 次零红（或给出真因）。
      ⚠ 别用"重跑绿了就没事"收尾——**门禁偶发红与门禁失效同样危险**（会训练出"重跑"习惯）。

> ⚠ **0.1.3 首次推送的阻塞项 + 完整 CI 排练结果**（作者 2026-09-26 定档：0.1.3 不单独
> 推送，计划 **11 月直接推送并打 `v0.1.3` 标**，**打标前必须 CI 全绿**）。`origin/dev`
> 至今停在 v0.1.1 ⇒ 本批 449 个提交 **CI 从未跑过**，故在本地把 `ci.yml` 的每一步
> 等价跑了一遍。**结论：4 类红**，全部来自这批"从未被门禁看过"的提交。
>
> | CI 步骤 | 本地等价做法 | 结果 |
> |---|---|---|
> | `pytest tests -q -n auto --cov` | 同命令 | ✅ 全绿（覆盖率 90.09%，≥80） |
> | shuffled-order smoke | `TPC_SHUFFLE_SEED=1 pytest -m smoke` | ✅ 451 passed |
> | policy `check_hardcode --strict-doc --strict-import` | 同命令 | ❌ **R3 2 处**（见下①） |
> | policy `check_doc_refs.py` | 同命令 | ✅ exit 0（D4 1 处 info：ADR-0020 孤儿，非 gate） |
> | **pyright strict** | `pyright --project pyrightconfig.strict.json` | ❌ **49 errors**（见下②） |
> | edge corpus gate | `python tests/edge/run_edge.py` | ✅ clean 6 / reject 7 / failures 0 |
> | fuzz smoke | `python tests/fuzz/run_fuzz.py --iters 500` | ✅ findings 0 |
> | CLI check | 仓库外 `tpc format` | ✅ exit 0 |
> | wheel-install job | build + 独立 venv 装 wheel + 仓库外 CLI | ✅（0.1.3 交付轮已验） |
>
> 待修**四类**：
> **① `check_hardcode --strict-doc` 缺 `Doc:` 头 2 处**（机械修）：
> `core/global_state.py:1`、`analyzer/elaboration/__init__.py:1`。
> **② pyright strict 49 errors**（v0.1.1 时是 **0**——`1448afc` 专门清零过；本批静默漂移）。
> 规则分布：`reportOptionalMemberAccess` 21 / `reportUnusedImport` 10 /
> `reportArgumentType` 6 / `reportUndefinedVariable` 4 / `reportUnusedVariable` 2 /
> `reportReturnType` 2 / `reportCallIssue` 2 / `reportAttributeAccessIssue` 2；
> 文件分布集中在 `tests/languages/c`（17）与引擎 `preprocessor`（6）/`analyzer`（3）/
> `lexer`（3）/`linter`（2）/`parser`（2）/`renderer`（2）/`pipeline`（1）。
> 按 `policy/pylance-cleanup.md` 分部件清零。⚠ 其中 4 条 `"Any" is not defined`
> （`parser/_production.py:788`、`preprocessor/_expand.py:713-715`）**当"真问题"看**：
> 名字用在值位置，只是靠 `from __future__ import annotations` 才没在运行期炸。
> **③ 单测依赖 gitignore 生成物**（下面第一条）。
> **④ 隔离工具 nodeid 归一同盘退化**（下面第二条）。
>
> **→ 现状（2026-09-26 收尾完成）**：①②③④ **四类红全部清零**，`v0.1.2` 上
> `python tools/ci_rehearsal.py` **9 步全 PASS**（含 fuzz smoke）：
> ① `Any` 未导入（Python ≤3.13 导入即崩，`489f1e9` + 新门禁）；
> ② pyright strict 53→0 与 R3 假红（`5cbf91e`），其中含一条真 bug（`Text.s`）；
> ③ 单测依赖 gitignore 生成物（`5cbf91e`，改指受控样本）；
> ④ nodeid 归一同盘退化 + `_abs_target` 共同祖先（`bf2d8e4`/`5cbf91e`）；
> 另修 fuzz 报的非幂等（`238234d`：直出切片与注释槽双吐行尾注释）。
>
> **对照：`v0.1.2` tag（`8dca789`）本身也过不了 CI**（同日同法排练，同一 worktree 手法）：
> pytest **4 failed / 2172 passed / 18 skipped**、shuffled smoke **1 failed**、
> `check_hardcode` **R3 同 2 处**、**pyright 27 errors**、fuzz smoke **FAIL**
> （`[NON-IDEMPOTENT] mut:ref_darkriscv.v: format(format(x)) != format(x)`，两次复跑均现）。
> 两个含义：① 0.1.2 批自己就带着这些红（因为从未推送过）；② 0.1.3 批**又新增 22 条
> pyright**（27 → 49），但**顺手修掉了那条非幂等**（HEAD 上 fuzz findings 0）
> ——即"渲染/解析注释落位四处缺陷"那轮的真实收益之一。
>
> 另注：`ci.yml` 的触发是 `push.branches` + `pull_request`，**推送 tag 不触发 CI**
> （`nightly.yml` 是 schedule + workflow_dispatch）——门禁只在推**分支**时对**分支 HEAD**
> 评估。故"tag 能否过 CI"是内容问题，不是流程问题。

- **并行度默认值**：`pyproject.toml` 的 `addopts = "-n auto"` **保持现状**（作者
  2026-09-19 定调“先这样”）。本机跑全量时自行显式传 `-n 4` 规避顶满核（做法与分档
  见 `tests/README.md`「改动节奏分档」）；不改仓库默认。

- [ ] **单测依赖 gitignore 的生成物 ⇒ 全新检出/CI 必红**（打 `v0.1.2` tag 时实测发现）：
      `tests/engine/analyzer/test_elaboration_{port_decls,signal_graph,gen_activity}.py`
      硬编码读 `tests/e2e/samples/normal/gen/gen_generate.v`，而该目录是
      `tests/e2e/run_all_tests.py` 的**产物**且在 `.gitignore`（`tests/e2e/samples/*/gen/`）。
      **实测**（临时 worktree 检出 `8dca789` = 全新检出态）：
        · 直接 `pytest tests` → **4 failed / 2172 passed / 18 skipped**（3 个是上述
          `FileNotFoundError`）；
        · 先跑 `run_all_tests.py` 生成产物 → **1 failed / 2175 passed / 18 skipped**
          （精化三项转绿；余下 1 项见下条）。
      影响：`ci.yml` 的 `pytest tests` 之前**没有生成步骤**，且 `origin/dev` 停在 v0.1.1
      ——本批 395 提交**从未推送**，CI 从未跑过它们 ⇒ 首次推送会红。
      修法候选：① 三项测试改用**已入库**的 ANSI 头部样本（`tests/e2e/samples/check_accuracy/
      cases/**` 或新增 `tests/engine/analyzer/fixtures/ansi_header.sv`）；② 测试内按需用
      `tmp_path` 自造样本（跑管线格式化 `ref/` 形态或直接写小样本再分析），**彻底去掉跨套件
      依赖**；③ 对 `normal/gen/gen_generate.v` 单独 `!` 反忽略入库（最省事，但与
      `.gitignore` 把 gen/ 当产物的意图冲突）。
      **判据**：全新克隆（或 `git worktree add` 到空目录）上直接 `pytest tests -q` 全绿，
      无需先跑 e2e harness。
- [ ] **隔离工具 nodeid 归一只在同盘成立（Linux/CI 会红，本机跨盘"假绿"）**：
      `tools/check_test_isolation.py::_normalize_id` 用 `os.path.relpath(path, _ROOT)`——
      仓库根与目标目录**同盘**时算出相对路径，**丢掉 `::用例名`**；**跨盘**时 `relpath`
      无法计算、退回原样（保留用例名）。**实测**（同一目标目录、同一脚本，只换仓位置）：
        · 主仓（仓在 `E:`、临时目录在 `C:`）→ 报 `::test_needs`（1 条差异）；
        · worktree（两者同在 `C:`）→ 报 `iso_probe/test_a_sets_state.py` 与
          `iso_probe/test_b_needs_state.py`（2 条差异，用例名丢失）。
      故自测 `tests/policy/test_check_test_isolation.py::test_compare_reports_isolated_only_failure`
      （断言含 `test_b_needs_state.py::test_needs`）**只在跨盘通过**；Linux/macOS 上仓库与
      `/tmp` 同属一个文件系统 ⇒ 与 worktree 同形 ⇒ **首次推送 CI 会红**。
      修法：`_normalize_id` 显式处理 `ValueError`（跨盘/仓外），并保证**用例名始终保留**、
      路径统一成 posix 相对形式；自测改为断言"文件名 + 用例名"两段，并补一条同盘/仓外路径
      的直接判据（否则本机永远只能验到跨盘那一半）。

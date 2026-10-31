# Changelog

All notable changes are listed in reverse chronological order.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **块 5 调查轮：unit graph 现状测绘（2026-10-31，仅文档）**：`docs/gaps/gap-unit-graph.md`——
  两套索引现状（V `ModuleIndexer` name→file 无导出；C `include.py` 解析出路径但不输出边）、
  方案 A（analyzer 内 `unit_graph` 组件 + 语言包 `[unit_graph]` 声明；C 边由 preprocessor
  现算现出）/ B（否：C 无单元声明规则）/ C（否：不改引擎则判据不可达）、7 条实现轮判据与
  预声明止损（若须重构 `scan_directives` ctx 契约 → 只落 V 侧、块 5 报 partial）。
  发现：`ProjectChecker.check()` 多入口已在库层支持（L105 / L148-159），CLI 仍单值
  （`main.py` L534-549）——多入参属 CLI 契约面，**待作者拍板**；C 未声明 `path_forms`
  （用引擎默认的 C 系约定，图化须复用同一解析口径）。
  · **外部调研**（`docs/references.md`「依赖/单元图工作链调研」）：Verilator `V3LinkCells`
  （编译器内 module 图：link pass 边产边、`rank()` → level/depth 排序、图环报递归多模块、
  `autoLoad` 缺定义占位延后报错）、slang `Compilation`（`topModules` 配置 roots、
  `getDefinition(name, scope)` 带作用域查找、`getUnreferencedDefinitions` 反推 top）、
  GCC/make `-M` depfile（预处理器产边、构建工具消费）、hdl_checker（项目级 LSP 依赖/编译序）。
  提炼 6 条共性 + 4 条明确不适用，落 gap 档「先例调研结论」三条加固。
  · **第二轮：语言无关抽象**（`docs/references.md`「通用工具链的图化抽象」）：Bazel
  （declared vs actual 两层图、actual ⊆ declared）、Ninja（depfile/deps/dyndep 运行期动态边、
  隐式边容错、路径须精确匹配）、SCons `Scanner`（**边生产者注册**：按文件类绑定、搜索路径注入、
  递归/检查策略、结果缓存）、Meson introspection（targets/depends/target_sources 的 JSON 出口）、
  BSP（`BuildTarget.uri/dependencies/dataKind`，语言无关骨架 + 语言 payload，`sources`/
  `inverseSources`）、Glean/Angle（node/edge 是 schema 声明的谓词）。提 **通用 7 条**，据此
  把 `[unit_graph]` 定为边生产者注册表、图 API 定为「三问」（roots / sources / inverse）、
  出口定为 `check --json`；增量层（Skyframe/DICE）明确留给块 7。
- **benchmark 共识下限门禁（块 11 ✅，2026-10-30）**：`tests/e2e/samples/real/benchmark_baseline.json`
  + `tests/policy/test_benchmark_baseline.py`——把 verilator 对拍能力卡成 CI 判据：
  **共识 53 下限**（只许增不许降；单次约 46s）与 **tpc 解析失败 = 0**；「仅 tpc 18 /
  仅 oracle 343」只作上下文记录、不锚（对语料与 oracle 版本敏感，锚死会假红）。
  oracle 缺失（无 MSYS2/verilator）即 skip，不假红；基线缺失/字段不全则失败，不假绿。
  · 区分力实测（PRE/POST）：基线抬到 54 ⇒ `test_consensus_not_below_floor` 红
  （`53 >= 54` 失败）；恢复 53 ⇒ 3 passed（42.5s）。`_verilator_ready` 对假 bash 路径
  返回 False（skip 路径可达）。
  · 阶段级 fuzz（lexer/parser-only 不变量，比全管线快 10–50x）仍留 `ROADMAP.md`
  P2.3 backlog——非发布阻塞，不进块 11 收口。
- **片段模式 P1：语法配置驱动的岛式分片（`tpc fragment`，块 4 ✅，2026-10-30）**
  · 新包 `islands/`：`model`（复用 linter 内部推导组件，零语言字面量）、`segment`
  （token 区间 → 字符区间 + water 判据 + 行首缩进）、`process`（岛文本 → 真实管线
  parse+render+formatter；后验 = 重解析 + 双跑逐字幂等）、`splice`（编辑集从右向左 +
  缩进基线回填）、`rewrite`（自顶向下编排：成功即整段替换、失败递归子节点、仍失败落
  water；无岛/零变化逐字节 identity）。
  · **零声明面**：不设 `[[island_rules]]` / `island_rewriter` / 记号 / 范围可选模式——
  片段模式下语法配置推导出的语法单元默认就是岛；要限定"只有某部分语法有效"单开语言包。
  · P0 原型 `tools/fragment_rewrite.py`（记号 + 手写 `always @(*)` 规则）与其测试删除，
  无兼容垫片；`tpc fragment` 改走 `islands/`（dry-run diff / `--write` 不变）。
  · 证据（按"改哪跑哪"纪律，未跑全量）：`tests/engine/test_islands.py` 10 passed
  （identity/BOM+CRLF/岛处理/water 保留/宏落水/双跑幂等/C 包同机制）；真实语料冒烟
  12 文件 0 crash / 0 non-idempotent；`eval_lint_accuracy` 33 hit / 0 miss / 0 fp；
  pyright strict 0 errors。`format`/`lint` 等既有命令行为不变（片段模式独立入口）。

### Changed
- **会话协作前置判据（2026-10-30）**：`policy/session-wire.md` 开头新增「先判：会话间对话 vs
  Teams」——按**上下文归属**判模式（对方上下文/目标 → 只能提问 + 给证据；我播种 → 交付物
  导向、可派活/终止），并写明混用代价；`AGENTS.md` 加一行指针，用户级
  `dsh-session-messaging` 技能首屏加同一判据（本机文件，不入库）。
- **技能面收敛：静态检查与补丁自查并入制度（2026-10-30）**：用户级技能 `pylance-cleanup`
  的现场坑（下划线改名不豁免 / fallback 参数名须一致 / 模块级 `type: ignore` 不生效）并入
  `policy/pylance-cleanup.md`；`enumeration-illusion-audit` 的判据（开放集 vs 封闭集三问 +
  补丁比）并入同文档「补丁 vs 机制」；`docs/audit_system.md` 分工表改指该节。
  三个用户级技能目录（`pylance-cleanup` / `enumeration-illusion-audit` /
  `project-abstraction`）已从本机技能库删除，仓库零引用；`docs/enumeration-ledger.jsonl`
  保留为历史扫描记录（冻结，不再追加）。
- **协作制度压缩：任务循环六步 → 四条硬规则（2026-10-30）**：`policy/collaboration.md`
  「任务循环」由六步改为四条承重规则（一轮一个可审交付物 / 契约与判据先于代码 / 分层验证
  改哪跑哪 / 收口四件）；取消"调查轮/实现轮"轮型标签——调查并入每轮前半段，只有需作者
  拍板时才单独成轮。六步里独有的计划要素（预算 / 止损点 / 计划级证伪 / 前后一致）迁入
  「循环执行细则·计划族」，其余细则族按规则号重编号。依据：复述约束的仪式未产生行为差
  （实测仍需作者重申"不硬编码"）、分层验证与收口本就靠执行面遵守，不是流程节点能兜住。
  同步 `AGENTS.md`、`policy/README.md`、`docs/audit_system.md`、`.agents/skills/task-cycle`
  （本机文件，不入库）；顺带修正 `policy/README.md` 里 `check_hardcode.py` 的陈旧规则数
  （1-4 → 1-6）。
- **结构推导层留在 linter 内部（片段模式 P1 前置，2026-10-30）**：`grammar_slicer /
  first_set / lookahead / discovery / discovery_shape` 作为 linter 的**内部组件**
  保留（不设独立顶层包）——只吃语言包 TOML（规则表 → 切片树 → FIRST → 前瞻 →
  发现树），零语言字面量、不产诊断。linter 的 `scanner` 消费它做检查器注册与
  `phase-unrecognized` 诊断；即将落地的 `islands/`（片段模式）直接消费同一套推导
  API（"先吃语法配置 → 得分片信息"）。
  · 过程：曾一次性抽离为顶层 `structure/` 包，按作者 2026-10-30 决定并回 linter
  内部（"就像 linter 内部的一个组件"）；文档/基线/门禁路径同步回 linter。
  · 随之定稿：片段模式 P1 不设 `[[island_rules]]`/`island_rewriter` 能力位，也不设
  记号/范围可选模式——片段模式下语法配置推导出的语法单元默认就是岛（若只想限定某
  部分语法有效 → 单开语法包）；处理 = 自顶向下过真实管线 + 合成，未处理区原样保留，
  后验默认开（岛级重解析 + 双跑幂等 + 字节 identity）。
  · 证据（组件面，按"改哪跑哪"纪律不跑全量）：linter 测试、受影响的 formatter/
  typed_ports 用例、policy 基线门禁与 pyright 全绿。

### Added
- **fuzz 并行评估 `--workers`（块 11）**：输入生成/变异仍在父进程按一个 rng 顺序
  展开（`_iter_inputs`），worker 只跑 `oracle.evaluate_format`；同一 `--seed` 的
  输入串与 worker 数无关（两次构造计划哈希相同），`imap` 保序 ⇒ findings /
  `index.jsonl` 与单进程一致。实测 500 iters（seed 42）：单进程 42.2s → 4 worker
  19.2s → 8 worker 15.8s，16 worker 不再涨（本机 16 逻辑核纯 CPU 实测并行上限
  ~4x）。`tests/fuzz/README.md` 补「吞吐与并行」节（口径/确定性判据/实测表）。

### Changed
- **块 11 吞吐：两处固定成本修复（fuzz 5 → 12 iter/s 单进程，300 iters 57.8s → 26.4s）**：
  · **配置声明装载晚于缓存命中**（`core/config_registry._resolve_cached`）：声明只由
  (包目录, 档位) 决定，而缓存键还含 ext/plugins/base——原实现先装载再查缓存，于是
  每次 resolve 重读重解析包内全部 tpc.toml（verilog 包 14 个插件，约 15 次 TOML
  解析 + 目录扫描）。fuzz 单迭代 ~20 次 resolve，这项占运行时间 75%（3 行种子探针
  10 → 40 iter/s）。配置文件在进程内不可变（`load_language` = 重新初始化），命中
  缓存不再触碰声明；`reset()` 清缓存。新增判据测试「同键 resolve 只装载一次声明」。
  · **parser 预编译表跨运行复用**（`pipeline._PIPELINE_SHARED`）：主解析 parser 给
  最外层管线复用（`Parser.parse()` 每次重置解析期状态）、formatter wrap parser 也按
  语言包缓存；幂等复跑的**嵌套**管线仍新建（`_IDEMPOTENT_REENTRY`），避免覆盖外层
  `result["parser"]` 的注释锚点。100 iters 的 parser init 2.90s → 0.18s（58 → 4 次）。
  · 新增 3 条判据测试；全量 4477 passed / 7 skipped；pyright strict 0 errors。

- **块 10 收口：`eval_benchmark` 对拍口径（parse 失败事实码 + 语法 lint 不误排除，`#79`）**：
  `_tpc_diags_all` 原以 `not parse_ok or f["syntax"]` 排除文件——把**语法阶段 lint**
  （ST001 行尾空白等）当成 parse 失败，7 个真实语料组里 6 个被判 `TPC-PARSE-FAIL`
  （实测全部 `parse_ok=True`、仅带 ST001-003 风格诊断），verilator 对拍只剩 real_uart
  （共识 0）。修法 = 排除面只认 `parse_ok=False`（真 parse 失败），语法 lint 不再影响
  语义对拍；parse 失败文件的 `ast_optional` 事实型码仍收集进 `row["facts"]` 与
  汇总 `tpc_facts`（只示明、不参与共识/FP 判定，避免 C 宏实参不足 MAC001 这类低报）。
  · 拆出 `_semantic_entries` / `_take_unseen`，两次补查循环共用（原两处 `continue` 是
    唯一丢弃点）；行/汇总新增 `tpc_parse_fail`、`tpc_facts` 英文键。
  · 证据（`eval_benchmark --oracle=verilator --json`，38s）：`tpc_parse_fail` 6 → **0**，
    共识 **0 → 53**（darkriscv 9/9、simcells 22/22、tv80 14/14、picorv32 8），仅tpc 18、
    仅oracle 343；verible 口径下 6 组恢复参与（其命名族 NC001/NC014 在默认规则集未启用
    ⇒ 仅oracle 661 的噪声属既有映射面，非本次口径）。slang 29.7s：仅tpc 71、仅o 0。
  · 新增 `tests/e2e/test_eval_benchmark_scope.py` 3 条（改前红：C `F(1)` ⇒ MAC001 被丢 /
    verilog ST001 组被排除；改后绿）。
  · TODO 删除该项；PROGRESS 块 10 ✅、当前 5/12，下一轮入口块 11 调查轮。

- **skill 形态演进（用户级，仓库外）**：新增 `invariant-falsifier`（只含协议层：
  输入契约 / 证伪过程 / 带证据的 verdict 契约 / 五条元不变量 M1–M5）；
  旧 `enumeration-illusion-audit` **降级为 L1 候选发生器**（首屏标注"只出候选、不裁决"）。
  分工：`scan_enumerations.py → 候选（形态） → invariant-falsifier → verdict`。
  反例硬门槛：`evidence_kind=executable` 才允许 `needs_redesign`，纯散文反例最高
  `needs_revision`——防止把开放集从"问题清单"挪到"反例断言"上。

- **审计工具自身的枚举幻觉（修 `~/.agents/skills/enumeration-illusion-audit`）**：
  用该 skill 的判据审它自己，修 7 处"自己也在枚举"的实现：
  · **命名参与打分 → 删除**：原 `OPEN_HINTS`/`CLOSED_HINTS` 给分数 ±0.25/−0.35，
    等于用词表判断"是否开放集"；实测**反向错判**——`DANGEROUS_CMDS`（危险命令
    denylist，开放集）因 `cmd` 命中 CLOSED_HINTS 被判 `0.00` + 理由"命名像协议枚举"。
    改为命名只作报告观察，不参与判定。
  · **AST 覆盖补三类**：`match/case`（Python 3.10+ 分派，此前整体漏检）、`Enum`
    /`StrEnum` 类（开放集枚举）、`x in {..}` 的成员判定改挂 `visit_Compare`
    （此前只在赋值右侧扫，`return`/`if` 位置漏检；owner 名字修正）。
  · **正则与 dict 去掉中文前置条件**：英文词表交替、英文键 allowlist/mapping
    此前整体漏检；改按内容形态判（`|` 切分后词形分支 ≥3 / 短字符串键 ≥8），
    中文比例只影响理由文案。
  · **`PUNCT_CHARS` 手抄 → `unicodedata` 类别谓词**：原表**漏了 ASCII `-`**，
    导致运算符交替 `<=|>=|==|!=|-|/|<|>` 被判成词表（假阳）；集合封闭 ≠ 手抄不会漏。
  · **文件发现改 `git ls-files`**：原按 14 个扩展名过滤，`.pyi`/`.vue`/`.svelte`/`.zig`
    等静默跳过；未知扩展名现在**打印提示**（可见而非静默）。
  · **回归**：6 形态混合探针 2/6（且两条判错）→ **6/6**；中文强项不变
    （`DANGLING_TAILS` HIGH 0.88 / 中文正则 HIGH 0.90）；运算符正则假阳 MEDIUM → LOW 0.05。
  · **局限已写回 skill 文档**（`SKILL.md`「自审记录与已知局限」）：英文开放集严重度
    偏保守、`branch_chain` 无法区分分派/堆规则、规模信号会抬高字符级封闭映射、
    未做使用面分析。
  · **账本**：`docs/enumeration-ledger.jsonl` 追加改造后基线
    （0 HIGH / 18 MEDIUM / 94 LOW / 条目 **514 → 942**）。⚠ 该跳变是**工具召回提升**
    所致（match/Enum/英文词表/dict 四类新可见），不是仓库一夜间变差；解读趋势时以
    同版本工具的前后对比为准。
  · 顺带自查结论：本仓 `lexer/number_gen._CHAR_CATEGORY`（42 个单字符→类别）判
    ✅ 封闭集；`tools/lang_penetration.TIER_A/TIER_B` 判 🟡（探测用弱信号词表，
    非正确性路径）。

### Added
- **不变量清单门禁 `policy/check_invariants.py` + `docs/invariants.toml`**（证伪器落地）：
  把"该证伪什么"从代码挪到**数据**（项目特定），协议只负责证伪——检测器要枚举问题
  （开放集），证伪器只需固定不变量（有限、可证伪）。
  · 清单 5 条：`INV-FAIL-CLOSED` / `INV-DERIVE-OVER-COPY` / `INV-DELETE-TEST` /
    `INV-OPEN-SET` / `INV-EVOLUTION`；字段含 `statement` / `violation` / `observable` /
    `verification` / `gate` / `violation_probe` / `known_pass`。
  · 门禁校验全可判定：字段齐全、id 唯一、statement≠violation、verification 枚举合法、
    **mechanized 必须有可解析的 gate + violation_probe**（锚点到 policy 规则 id /
    测试函数 / 变异序号），procedural 必须写清 manual_check。
    锚点失效即红——**防清单腐烂成新的封闭幻觉**。
  · **为何不是新增重复门禁**（INV-EVOLUTION 的证据）：`check_doc_refs` 的 D3
    明确"不做符号级存在性"（只文件级、glob 非空即过），而本门禁要解析的
    规则 id / 测试函数 / 变异序号**都是符号级**——旧规则覆盖不到。
    边界已双向写进两个脚本的文档，并由 `tests/policy/test_gate_boundary.py`
    机械锁定（doc gate 只认 .md、invariants gate 拒绝 .md 锚点、两者语法不相交）。
  · 接入 CI（`policy checks` 步骤）与 `tests/policy/test_invariants_manifest.py`（9 条：
    真实清单回归 + 7 条负例证明门禁会响——"门禁存在"≠"门禁会响"）。
  · 验证：tests/policy 581 passed；check_doc_refs D1–D4 全 0；
    structural S 1110 → 1018（新增 0 项）。

- **枚举幻觉审计（按 `enumeration-illusion-audit` skill 正式流程补做，含自纠）**：
  上一轮我只从 #78 提交信息反推判据、未走 skill 工作流（未用扫描器/账本/三分类）；
  本轮按 skill 补齐：扫描本次会话改动的 23 个 .py → 候选 2 条 / 清单条目 45。
  **按 `references/field-notes.md` 的标尺复核后，更正上一轮的过度声称**：
  · ✅ **`main_lexer._scan_one` 10 分支链**＝合法封闭集：按**词法类别**固定优先级
    分派（换行→空白→capture→plain→数字→符号→括号→转义标识符→标识符→兜底），
    类别由 lexer 自身设计封闭、分支顺序即语义（优先级）。field-notes 明确把
    "解析器/词法器的 if/elif 链（按 token 类型分派）"列为 ✅ 典型。
  · ✅→**单源化改进（非修幻觉）**：`PY_KEYWORDS`（35 项 Python 关键字）在
    field-notes 里本就属 ✅ 合法封闭集（语言定义）；但仍改为从 `keyword.kwlist`
    派生，理由是**防版本漂移**（新增硬关键字 → 静默漏剔除 → R1 假红），
    实测 35/35 与旧表一致、行为零变化。**不记为"修枚举幻觉"。**
  · **更正上一轮的 R6 判定**：`("bracket.","symbol.","keyword.")` 不是"开放集当
    封闭集"，而是**封闭集的陈旧副本**（协议族本就是 `core/token_protocol.py` 的
    7 个常量）——真实缺陷是**单一来源违反/漂移**，机制仍是派生，但标签应更正。
  · **本轮新增的 3 处显式清单判 🟡 配置型（可控）**：`LEXER_CATEGORY_PREFIXES`(2)、
    `LOCAL_CONFIG_SECTIONS`(2)、`R6_FILE_ALLOWLIST`(+1)——对应 field-notes 的
    `IGNORE_DIRS` 同类；触发条件 = 条目再增长或再次出事故时机制化
    （前两者可从 TOML 表名派生）。
  · **本轮真·枚举幻觉：0**（校准后）。全仓基线扫描（排除 vendored/构建产物）：
    **77 候选 / 0 HIGH / 7 MEDIUM / 70 LOW，清单条目总数 514**；7 个 MEDIUM 全为
    词法/插件分派链（✅ 类）——与 field-notes "解析器/编译器项目里 branch_chain
    大量误报"的结论一致。
  · **落账**：新增 `docs/enumeration-ledger.jsonl`（首条基线），供 `--trend`
    看"清单条目总数"是否只增不减（field-notes 警告：危险信号是"表在正确性路径上
    + 正在增长"，而非"有一张表"）。
  · 验证：check_doc_refs D1–D4 全 0；check_hardcode PASS；tests/policy 572 passed；
    structural S 1110 → 1018（新增 0 项）。

- **枚举幻觉审查（enumeration-illusion-audit）：清除本轮门禁/政策改动里的
  「封闭集拟合开放集」**——按 #78 先例复核本轮 6 个提交：
  · **R6 前缀族手写枚举 → 从 token 协议派生**：原 `("bracket.","symbol.","keyword.")`
    只覆盖协议族 **3/7**，`literal.number` / `space.indent` / `macro.call` 这类具体名
    会**整体逃过门禁**。改为读 `core/token_protocol.py` 的 `*_PREFIX` 常量派生前缀族、
    其余字符串常量派生协议词汇；协议文件缺失/坏 → **显式报错**（不静默降级为"零违规"）。
    注入自证：`literal.number` / `keyword.module` 现均被抓（前者旧实现漏检）。
  · **协议 token 名收口为常量**（单一来源）：`token_protocol.py` 新增
    `SPACE_*` / `LITERAL_*` 常量并在 `TRIVIA_TOKEN_TYPES` 复用；lexer/parser 的 6 处
    裸字符串（`"space.indent"`/`"literal.number"`/`"literal.string"` 等）改引用常量
    ——否则 R6 无法区分"协议词"与"语言 token 名"，只能退化成手写 allowlist。
  · **能力推导的段枚举补门禁**：`required_capabilities()` 按 `SECTION_CAPABILITY`
    封闭表推导，**新增清单段会静默漏掉**（`derived ⊆ uses` 恒真、协商标空转）。
    新增 `test_every_manifest_section_is_classified`（未分类段即红）；顺带发现并归类
    现存的 `[requires]`（组件依赖，行政段）与 `[formatter]`/`[macro_policy]`
    （组件本地配置，新增 `LOCAL_CONFIG_SECTIONS`）。
  · **`[discovery].prefix_pairs` 畸形不再静默丢弃**：改 fail-fast（ADR-0003）——
    少一对前缀对会让属性区边界判定悄悄退回错误形态且无可见症状。
  · **测试夹具同步**：`test_check_hardcode` 的最小树补 `core/token_protocol.py`
    （含 `Doc:` 头），并新增两条契约用例（派生覆盖全部协议族 / 缺协议文件必须报错）。
  · 验证：全量 **4417 passed / 7 skipped**；check_doc_refs D1–D4 全 0；
    check_hardcode PASS；structural S 1110 → 1018（**新增 0 项**）。

- **ADR-0025 实施（D1–D4）：语句发现改为声明式形态推导**——`linter/discovery.py`
  不再靠 production 结构"猜"语法形状，新增开闭原则修复：
  · **声明面**：语言包新增 `base/_discovery.toml`（`[discovery]` 段：`containers` /
    `continuations` / `prefix_pairs` / `clause_separators`）+ `tpc.toml`
    `[discovery] shape = {file, section}` + 能力 `discovery.shape.v1`
    （`core/engine_capabilities.py`）。verilog / c 各一份声明。
  · **引擎侧**：新增 `linter/discovery_shape.py`（`DiscoveryShape` + `load_shape` +
    统一判定 `is_stmt_container`）；删除 `_derive_attr_openers` /
    `_derive_continuation_openers` / `_is_bracket_stmt_container`（discovery）与
    `_is_pure_stmt_container`（scanner）——两处近乎逐行重复的容器启发式合并为单一口径。
  · **为什么改**（实测证据）：旧启发式在 116 个样本上的有效命中只有 `CompoundStmt`
    一处，但对 `PortParens`/`Range`/`InitList`/`StructBody` 等 12+ 条**非容器规则**同样
    返回 True ⇒ 它在猜；且 `[[nodiscard]] int f(void){...}` 与 `{...}` 结构同形，
    区分依据是语义意图，只能声明。
  · **行为零变化（硬判据）**：`eval_lint_accuracy` 33/33 召回 + FP 0；
    `eval_diag_baseline` 5548→5548 不增长；删除函数致变异载荷失配时
    `test_gate_efficacy_mutations` 当场变红（已同步载荷）。
  · **量化收敛**：structural S **1110 → 1018（Δ −92，新增 0 项）**；
    `structural_kept.json` 退场 4 条同理由豁免（`_is_bracket_stmt_container` /
    `_discover_statement` CC+COG / `Discovery` 类），仅 `LookaheadTable` 仍超标保留。
  · **R6 门禁债清零**：`check_hardcode.py` 移除 3 条 allowlist（discovery 属性对 2 条 +
    scanner 子句分隔符 1 条）——引擎侧已无具体语言 token 名。
  · **开闭自证**：临时假语言包仅声明 `[discovery]`（容器/延续/属性对/子句分隔符），
    **不改任何引擎文件**即全部生效。
  · 验证：全量 **4411 passed / 7 skipped**；check_doc_refs D1–D4 全 0；
    check_hardcode PASS；tests/policy 566 passed。

- **审查任务 4：gap 档案冗余审查（合并 1 对 + 修 D4 孤儿）**：对 `docs/gaps/` 18 档做
  内容级相似度扫描（词元集合 Jaccard + 包含度），结论：**不存在"同一件事的不同侧面"
  式的实质重复**——最高相似度仅 J=0.131（主题相邻但材料各自独立），故不做成批合并。
  · **合并 1 对（真同根因）**：`gap-lexer-capture-boundaries.md` +
    `gap-preprocessor-comment-scan.md` → `gap-comment-string-span-consistency.md`。
    理由：两者是"注释/字符串跨度判定"的两套实现（词法捕获器 A 侧边界 / 预处理器
    行级状态机 B 侧近似），且 B 侧的闭环方案恰好是"向 A 侧要跨度"——分开建档会让
    真正的决策点被拆散。合并前确认两档除 README 表外**零外部引用**（安全）。
  · **修 D4 孤儿**：`gap-parser-backtracking.md` 长期未被 README 档案表登记
    （`check_doc_refs` D4 唯一告警项）→ 补登。文档门禁 **D3/D4 首次全 0**。
  · **顺带修 ADR-0025 的失效 Impl 锚**：`Impl:` 续行里提到尚不存在的声明段文件，
    被 D3 判为反向引用失效 → 该说明移出 Impl 块。
  · **保留判断（有证据，非遗漏）**：7 个已收口/已实施档案不删——它们被代码
    `Doc:` 大量反向引用（`grammar/c/*.toml`、`core/define.py`、多个测试与 README，
    共 30+ 处），删则制造大面积判据 B3 悬空引用。其过程叙述占比仅 4–18%，且多为
    代码引用的设计依据。**但 3 档已顶到 200 行预算上限**（`gap-c-semantic-base` 200、
    `gap-c-preprocessor-scope` 197、`gap-c-real-corpus` 196），后续动这几档时优先
    把"交付叙述/实测过程"搬回 git log 换回余量。
  · 验证：`check_doc_refs` D1–D4 全 0；`tests/policy` 566 passed。

- **审查任务 3：测试用例正交性（同构冗余参数化）**：新增
  `tools/scan_test_redundancy.py`——按 AST 骨架抹掉字面量/名字后比对，
  找出**同一文件/类内、仅数据不同**的测试函数组（参数化候选，不是"可删覆盖"）；
  并标注是否被 `min_pack_baseline.json` 锚定（锚定者的 node id 会随参数化改变，
  须串行重录基线）。
  · 首批参数化 3 个文件，测试函数 67 → 47，**pytest 收集数不变**（覆盖不丢）：
    `test_2005_batch9.py`（9 个层次化引用交错形态 → 1，13→5 函数）、
    `test_2005_batch6.py`（11 个「解析+渲染保真+幂等」→ 1，21→11 函数）、
    `test_pratt_comment_keep.py`（6 个各位置注释保留 → 1，14 收集数不变）。
  · 过程教训（已固化进工具文档）：按"首末函数行区间"删除会连带删掉区间内
    的**非目标**测试（batch6 初版收集数 21→13）——必须逐函数精确删除，并把
    "收集数前后相等"作为硬断言。
  · 余量（工具现报告）：13 组 / 57 个可减，其中 3 组被 min_pack 基线锚定。
  · 验证：全量 **4411 passed / 7 skipped**；check_doc_refs / check_hardcode PASS。

- **审查任务 2：预处理器 / linter / 解析器 / 精化基座 正交性审查 + 第一批清理**：
  逐子系统查"双实现 / 补丁叠加 / 硬编码语言知识 / 死代码"，
  结论：**预处理器与精化基座结构干净（无改动）**；linter/parser 各有死代码与幽灵引用。
  · **预处理器**：`_expand.py` 已完全委托 `macro_expand` 的 hideset 引擎（旧"文本替换不动点"
    算法已删，无残留）；`IDENT_RE` 单一来源；`condition._masks` 是 `mask_spans` 的薄封装；
    零未调用私有函数；零反向依赖 parser/linter ⇒ **无改动**。
  · **精化基座**：`structure.py`（通用设施）与 `elaboration/*`（引擎最小视图 + 插件求解）
    分层清楚，`ElaborationService` 只转交 `StructureCtx` 能力不重新实现，全包单一解析点
    ⇒ **无改动**。
  · **linter 清理**：删 `discovery._discover_range` 的 `record` 形参链（P3c 前置切片遗留，
    ADR-0024 已退役该能力，全仓无 `record=False` 调用方）；删 `RuleMatcher.memo_suspended()`
    （零调用，且 `@contextmanager` 装饰器早已丢失 ⇒ 永不执行 `yield` 的损坏方法）；
    删 `lookahead._elem_called_rules()`（零外部调用）；清 `_allowed_in_context` /
    `internal_warnings()` / `_substitution_trial` 幽灵引用；删整体 skip 且引用已删 API 的
    `tests/engine/linter/test_raw_corpus.py`（`corpus_raw/` 保留——仍被 3 个 C 检查测试
    当误报语料）。
  · **`linter/AGENTS.md` 纠错**：三条纪律指向已删能力；其中"资格判定四条缺陷态已进门禁抽查"
    经核实 **_MUTATIONS 中根本不存在**，改为通用门禁纪律。
  · **parser 清理**：删 `repeat_loop = _repeat_loop` 别名（零引用，只为自循环存在）；
    `extract_from_spec` 去掉 `self` 占位参 + `del self  # 仅为兼容旧调用`。
  · **门禁自证**：删 `record` 形参导致第 9 条变异载荷失配 →
    `test_gate_efficacy_mutations` 当场变红（守卫有效），载荷已同步。
  · structural S：1110 → 1018（Δ **-92**，新增 0 项、变大 0 项）。
  · 验证：全量 **4406 passed / 7 skipped**；`eval_lint_accuracy` 33/33 召回、FP 0；
    `eval_diag_baseline` 5548→5548 无增长；check_doc_refs / check_hardcode PASS。

- **审查任务 1：草稿暂存区 `_drafts/` 清空 + 冗余扫描工具**：`_drafts/`
  （5,481 文件 / 119.9 MB，gitignored 讨论草稿区）按删除判据逐类清理：
  vendored 外部语料副本（veryl_ref/gcc/pre_p3/pre_p3b，97.6 MB）、运行产物与
  `__pycache__`、commit_msg/cases JSON/diff/ast 转储等编辑残留、过期的
  `HEAD-*` 快照。
  · **删除前先迁走活引用**（否则立即制造悬空引用，判据 B3）：5 个测试原以
    `_drafts/taskNN_defect.py` 作"缺陷态变红"证据 → 改指 `tools/check_gate_efficacy.py`
    的 `_MUTATIONS` 表（正式门禁 + policy 静态守卫）；其中 task-22 的 4 条符号表
    变异此前**未被覆盖**，本轮迁入（119 条），`--only` 逐条抽查均如期变红。
  · 片段模式（未立项，P1 待批）的设计输入原只存在于草稿 → P1/P2 契约与退出
    判据内联进 `docs/gaps/gap-fragment-mode.md`，`ROADMAP.md` 指针同步改指该档
    （`policy/collaboration.md` 要求设计输入/反例必须落版本库，不能只留草稿）。
  · 新增 `tools/scan_redundant.py`：冗余残留扫描脚手架（默认 dry-run 只报告；
    `--live-refs` 列出"仍被引用的草稿"，即删除前的放行闸；`--clean <kind> --yes`
    才真删）。
  · 残留引用仅 `CHANGELOG.md` 的历史条目（按反判据，CHANGELOG 历史不是删除对象）。
  · 验证：全量 **4406 passed / 14 skipped**；check_doc_refs / check_hardcode PASS；
    tests/policy 561 passed。

- **块 10：CI 排练对齐 cp1252 控制台（#77）**：
  · `tools/ci_rehearsal.py::_run` 对 Python 子进程注入 `PYTHONIOENCODING=cp1252`
    （模拟无 `PYTHONUTF8` 的远端 Windows runner），wheel 外跑 CLI 同口径；
  · `tpc fragment`（main.py + tools 入口）输出流 `errors=backslashreplace`，避免中文
    diff/摘要在 cp1252 下 UnicodeEncodeError（cp1252 排练实测暴露的唯一失败）。
  · 证据：cp1252 下 pytest 主回归 PASS、smoke/hardcode/docrefs/pyright/edge/fuzz/cli/wheel
    逐项 PASS（修复前主回归 1 failed = fragment CLI）。
  · TODO 删除该项；PROGRESS 块10 更新（只剩 eval_benchmark 口径）。

- **块 10：yaml 真实 workflow 两遍渲染幂等（#76）**：parser `_consume_block_end`
  对零宽块结束符（yaml `space.dedent`）不再消费紧随的独占行注释——其 `line` 指向
  下一行内容，注释不在结束符物理行上；留给父容器按 Comment 项处理。修复 ci.yml
  第一遍把块末注释并到 `shell: pwsh` 行、第二遍再并下一行的 `format(format(x)) != format(x)`。
  · 新增 `TestRealWorkflowFiles::test_real_workflow_files_idempotent`；
    ci.yml/nightly.yml 两遍逐字相同；yaml 110 测试全绿。
  · 全量 4392 passed/14 skipped；A/B 0/144；pyright 0；S Δ-92。
  · TODO 删除 yaml 项；PROGRESS 块 10 更新（剩 cp1252 / eval_benchmark）。

- **块 10：跨语言同进程 C→verilog→C postpass 不丢失（#74）**：
  `SharedComponents` 缓存命中时按当前全局 `_active_components` 与缓存语言组件名比较，
  不一致则重建配置与组件注册表（postpass/原语/capability）再复用对象。
  修复库入口 `ProjectChecker` 第二轮 C 的 CSC/LAB/MAC 静默丢失（单语言 CLI 不复现）。
  · 回归：`tests/engine/analyzer/test_checker_cross_language.py`（LAB001 两轮一致）；
  · 同语言重复 check 走快速路径（不重复 load）。
  · TODO 删除该项；PROGRESS 块 10 进度更新。

- **块 10 工程化：A/B 对拍 inproc 档可用（#73）**：`tools/ab_pipeline_compare.py`
  `--plugins` 默认改为 `<pack>/plugins`（换语言包不再手改）；采样输出增加"取最后一个 JSON
  对象"兜底与带 stdout/stderr 的诊断错误（旧行为裸 `JSONDecodeError`）。
  · 证据：`--mode inproc --pack grammar/verilog`（不带 `--plugins`）与 C 包均 `0/1`，不再
    C 插件注入 verilog 的 `GrammarError`。
  · TODO 删除该项；PROGRESS 块 10 标记部分完成（其余 4 项待）。

- **块 8 块内诊断粒度（#71）**：C `CompoundStmt` 的 `{ ... }` 作为括号定界语句容器递归发现子语句；
  容器 body 内 Level 2 试解析无候选时按首 token 回退注册；父容器检查器在子节点存在时让位。
  `void f(void) { a + ; b + ; }` 现报 **2 条位置正确**的 `phase-statement`（char 17/23），不再只报
  1 条指向块起点；合法块 0 诊断。非容器上下文保持原未识别语义。
  · 新增 `tests/languages/c/test_c_block_diagnostics.py`；linter/C/Verilog/e2e 全绿；A/B 0/144。
  · 结构分：`COG/CC`/类规模增长按块 8 行为理由登记 kept；PROGRESS 块 8 ✅（4/12）；TODO 删除该项。

- **块 3 片段模式 P0（#70）**：独立 CLI `tpc fragment` + `tools/fragment_rewrite.py`：
  显式行注释记号（`// tpc:fragment id=<id> begin` … `// tpc:fragment end`，单层/显式 id）圈定区域，
  纯语法规则 `always @(*)` → `always @*`；默认 dry-run diff、`--write` 落盘。
  · bytes identity 四例（LF/CRLF/BOM/无尾）逐字节不变；字符串/块注释假记号忽略；条件编译死分支
    记号按 condition_blocks 排除；未闭合/嵌套/错配 fail-closed。
  · 10 单测；真实文件 1 命中 0 误改；真实语料 259 个 .v/.sv 无记号 **0 文件变化**（9.1s）。
  · **不新增 TOML 段/能力位**（P1 需作者批准后再做）；文档 `docs/gaps/gap-fragment-mode.md`；
    PROGRESS 块 3 ✅（3/12）。

- **块 2 收口：parser 回溯优化——atom memo + 规则级 FIRST 早拒（#68/#69）**：
  · atom 位置 memo（`(token 位置, 作用域版本)`；`_ScopeStack.version` 仅在真实状态变化时递增；
    `restore` 无变化快速路径）消除嵌套括号下重复解析的 2^k。
  · `follow.compute_first_map`（FIRST+nullable 完整不动点）+ `build_rule_first_map`
    （排除块/pratt/nullable/空 FIRST）驱动 `try_plain_rule` 规则级早拒；token 不在 FIRST 且
    非 trivia/宏/占位 ⇒ 直接失败，不建节点/日志/帧。
  · 结果：cJSON 解析 **57.6s → 2.98s（median，19.3x）**；C 语料门禁 **20–23s**（目标 ≤30s）；
    A/B **0/144**；全量 **4377/14**；corpus 7/7 0 诊断；pyright 0；S Δ0（AST 节点名序列一致）。
  · 文档：`gap-parser-backtracking.md` 收口；PROGRESS 块 2 ✅（2/12）；TODO 性能项删除。

- **块 2：parser atom 位置 memo（#68，partial）**：`_atom_parser_impl` 按
  `(token 位置, 作用域版本)` 缓存 atom 结果；`_ScopeStack` 版本号仅在真实状态变化时递增；
  `Parser.parse` 每次清空 memo；`restore` 增加无变化快速路径。消除嵌套括号下
  `ParenthesizedExpr`/`PostfixExpr`/`CastExpr` 重复解析导致的 2^k 回溯。
  · 同机对照：pre-memo **57.6s → 8.75s**（median，**6.6x**）；AST 节点名序列一致（25,230）；
    全量 **4377/14**、A/B **0/144**、语料 7/7 0 诊断；pyright 0。
  · 目标 cJSON ≤5s 未达、门禁 borderline（31.5s median，min 31.3s）；下一轮继续候选去重/
    热路径优化；`COG|_atom_parser_impl` 以性能分支理由登记 kept。
  · 文档：`gap-parser-backtracking.md` 实施记录；PROGRESS 块 2 状态；TODO 同步。

- **主线 2 刻度立档（12 块：工具化 + 高性能 0.1.4）**：`PROGRESS.md` 改写为新主线刻度
  （块 1 基线清算 → 2 parser 性能 → 3/4 片段模式 P0/P1 → 5 unit graph → 6 精化基座 graph 化 →
  7 增量/编辑器 → 8 诊断粒度 → 9 渲染注释 → 10 工程化缺口 → 11 吞吐基准 → 12 收口）；
  `ROADMAP.md` 当前主线改写、删除已完成 P2.9；`TODO.md` 清理三条过期项（结构欠账/散点新增/
  性能前提措辞）。片段模式设计输入 = `_drafts/marker-mode-evaluation.md`（未入库；P1 声明面/
  能力位属框架级，待作者批准）。

- **T3 部件⑥：pipeline/config 审查 + C uses 漂移修复（#66；T3 收口 #59–#66）**：
  · L1：C `[engine].uses` 删除 T2c 遗留的 `transform.slots.v1`（C 已无任何 transform 声明；
    `grep grammar/c transform` = 0；policy + C 套件 1238 passed 绿）。
  · 判据②：删 C `analyzer.primitives.v1` → `test_engine_capabilities` 1 failed（声明门禁）；
    删 Verilog pipeline unit `slots` → pipeline/e2e 20 failed（声明承重）。
  · 弱信号：`lang_penetration --dirs pipeline core` 结构名 2 处 `"L"` 为诊断格式化误报；
    `core/_protocol` 端口常量命名（L2）登记接受。`config_sites check` PASS；
    `feature_sites`/`structural_score` Δ0；A/B 0/144。
  · **T3 矩阵六部件全审**：①②③④⑥ 无行为 leak（接受/已修方言复制、uses 漂移），
    ⑤ L1 已修；接受项 = `inst_sites` 命名、`core/_protocol` 端口常量名（触发条件 = 第二门
    语言用 structure/typed_ports 面时复议）。T3 收口、T1–T3 路线图完成。

- **T3 部件⑤实现：transform 成品行属性声明化（#65，L1 修复）**：
  · `transform/_semantic_mapping.py` 去掉 `attr == "ports"` / `sym.attrs["resolved_ports"]`
    硬编码，改读 mapping entry 的声明键 `source.resolved_attr`；helper 更名
    `_has_declared_flat_rows`；Verilog `typed_ports/_mapping.py` 声明
    `"resolved_attr": "resolved_ports"`。引擎 `grep` 的 `ports`/`resolved_ports` 字面量 **0**。
  · 判据：去掉 Verilog 声明键 → `test_typed_ports` **4 failed**（声明承重）；变异表新增该条
    （114→115）；全量 **4377 passed/14 skipped**；A/B **0/144**；`structural_score` Δ0。
  · 余：部件⑥（pipeline/config）→ T3 收口。

- **T3 部件①实现：Verilog 注释单一声明面 + 工具基线刷新（#60）**：
  · L1：删 `grammar/verilog/token.toml` 中重复的 `[comment].pairs`（保留
    `base/_lexer.toml`，与 C 对齐）；修复后删剩余一份 ⇒ `lexer.tokenize("// c")` 无
    comment token、`tests/engine/lexer` **10 failed**（单一来源承重）。
  · L2：`tools/structural_score.py --save`（S=1110，Δ+0）与 `tools/feature_sites.py --save`
    （`check` 预算 16；理由 = C11/C23/CSC/TAG/ENUM/LAB/MAC 检查组件入库 + T1/T2 真实改动）；
    两者 `--compare` 现 0 增长。
  · 验证：`tests/engine/lexer|preprocessor|e2e` 751 passed/7 skipped；A/B **0/144**；
    render **124/124**；doc refs/预算 PASS。

- **T2d：pre_scan/raw 文档收口（#58，ADR-0024 done）**：
  · 改写 `linter/linter_architecture.md`（收敛 warning/raw 资格 → 退役说明）、
    `grammar/c/README.md`（期别/两期 API/P4 章节）、`gap-c-semantic-base.md`/
    `gap-parser-linter-approximation.md`（历史方案 + 收口状态）、`gap-engine-abstraction-audit.md`
    （矩阵 #3 收口）、`MODEL_INDEX.md`/`docs/README.md`/`lexer/README.md`/`parser/AGENTS.md`/
    `gap-c-typedef-cast.md` 幽灵引用清理。
  · 验证：全量 **4374 passed/14 skipped**；A/B **0/144**；render **124/124**；
    `c_acceptance` **49/0**；doc refs/预算 PASS。**T2 全部收口**，进入 T3。

- **T2c 切片③：删除 linter M2 与候选收敛内部 warning 旁路（#57，ADR-0024）**：
  · 删 `scanner` 的 M2 摘诊断（`_DOWNGRADABLE_CODES`/`_apply_narrow_downgrade`）、
    `internal_warnings` 状态/取用；删 lookahead 收敛判定面（`_record_convergence`/
    `_member_only`/`_allowed_in_context`/内部 warning 列表）、discovery 转发与容器位点扫描、
    pipeline `ctx.internal_warnings`。
  · 删 `test_lint_internal_warnings.py`/`test_linter_symbol_hints.py`/lookahead 收敛用例；
    变异 -1。**T2c 完成**：raw 管线（P4/引擎契约/parser 承载/linter 资格与摘诊断）全部删除。
  · 验证：linter+pipeline+C 1585 passed/7 skipped；全量 **4374 passed/14 skipped**；
    pyright 0；变异目标校验通过；`core/global_state` 清 raw 契约登记 2 条。
  · 余：T2d 文档收口 + 全量冻结树 → T3。

- **T2c 切片②：删除 parser raw 承载（#56，ADR-0024）**：
  · 删 `block_parser` 的 `RawStatement` 机制（`match_raw_site`/`try_raw_sentence`/
    `build_raw_candidate`/`_raw_trial_*`/`_verbatim_slice`）、`parser_core` 的 `raw_sites`/
    `raw_source`/试建台账、`_production` 的 raw 接入点、`analyzer/structure` 位点注入、
    pipeline 的位点注入/未重定位日志/幂等 raw 特例。
  · 删 `test_parser_raw_site.py`/`test_raw_corpus.py`；变异 -1（parser raw 兜底条目）。
  · 验证：parser+preprocessor+C+pipeline 1968 passed/1 skipped；analyzer+C+pipeline
    1739 passed/1 skipped；pyright 0；变异目标校验通过。
  · 余：切片③（linter M2/内部 warning 旁路）→ T2d 文档收口 + 全量冻结树。

- **T2b：删除 lexer 预扫描（pre_scan）机制（#54，ADR-0024）**：
  · 删 `lexer/pre_scan.py` 与导出、两包 `[lexer] pre_scan` 配置与 `base/_pre_scan.toml`、
    `core/global_state` 缓存键与 `core/engine_capabilities` 能力注释。
  · 删 linter 接线：`scanner` 的 `load_pre_scan_config`/`_pre_scan_symbols`/`_raw_exclude_rules`、
    `discovery.set_symbol_hints`、`lookahead` 的符号字段与 `set_symbol_hints`/`_type_name_hits`/
    `_depth_before`/`_substitution_trial`（M1 资格面整体退役；内部 warning 只留收敛证据，
    raw 位点不再产生）。
  · 删 C 两期产物 `two_phase_product`/`pre_scan_records`/`merge_phases`/`phases_for`/
    `PHASE_PRE_SCAN`；`test_c_symbol_collection` 改 analyze-only；删
    `test_pre_scan_fallback.py`、`test_linter_raw_eligibility.py`；变异表 123→118。
  · 验证：C+linter+pipeline 1617 passed/21 skipped；全量 **4454 passed / 38 skipped**；
    e2e 129/7；C 真实语料 7/7 零诊断；verilog 基线无增长；A/B 0/144；pyright 0；
    `check_doc_refs` PASS；生产代码 pre_scan grep 0。
  · 余：T2c 删 raw 管线（M2/parser raw/P4/E002·E003 + 剩余 skip）；T2d 文档收口。

- **T2a：typedef 名复合字面量直接建树（#53，ADR-0024 复裁）**：
  · `CompoundLiteral` 类型名收 `@CastTypeName|@CastTypedefName`（复用 #49 门控）⇒
    `(t){1}` / `(S){ .a = 1 }` 解析期直接建 `CompoundLiteral`，不再走 raw 兜底；
    P4 的"复合字面量 raw 边界"测试改为直接结构断言；变异新增（去分支 ⇒ 用例红，清单 123）。
  · **ADR-0024 复裁**：G4（#49）后 typedef 强转已由 parser 符号表解析，T2a 补齐复合字面量；
    实测**临时禁用两包 `[lexer] pre_scan`** ⇒ C/linter/pipeline 套件 1617 passed（唯一失败
    = 断言 pre_scan 期记录的死测试）、C 真实语料 7/7 零诊断 ⇒ **pre_scan 零承重**，
    依赖它的 raw 管线在 C 上也已无生产消费者。T2 由"两阶段改造"改为**删除两条死机制**：
    T2b 删 pre_scan 本体/配置/两期产物/符号提示接线；T2c 删 raw 管线（含 67 skip，先证后删）；
    T2d 文档收口。判据/止损/否掉备选见 ADR-0024（重写）。
  · 验证：C/linter/pipeline 1618 passed/58 skipped；复合字面量直解结构断言；A/B 0/144；
    pyright 0（全量门禁在 T2b/T2c 各片收口时重跑）。

- **真实 C 语料门禁落地（退出判据 5 收口；循环 #52，T1 收尾）**：
  · 语料入库 `tests/e2e/samples/real_c_ref/`：cJSON 1.7.19（MIT）两文件 + zlib 1.3.2
    （zlib license）六 C + 四头 + 14 个最小系统头 stub；`CREDITS.md` 记来源/版本/许可
    （源文件保留完整版权头；`crc32.h` 生成大表不入库）。
  · 采集器 `tests/e2e/eval_diag_baseline_c.py`（`collect/collect_report` + `--json/--update`，
    口径同 verilog 先例"只许减不许增"）；基线 `diag_baseline.json`（**total=0**）；
    门禁 `tests/policy/test_diag_baseline_c.py`（清单齐全 + 每文件 parse_ok + 增长即失败 +
    total 自洽）。
  · 前置修复：include 子扫描**继承包含点宏环境**（`predefined=_active_defs`）⇒ include
    guard 跨 include 可见，zlib `z_stream_s`/`gz_header_s` TAG001 二次定义清零（语料
    7/7 parse_ok + **0 诊断**）。
  · 修复：linter 表达式**注释回退**——pratt 不跳注释（宏体尾注释被铺进流，crc32
    `POLY` 进三元 `?:` 命中）；表达式在 comment 处停住/抛错时用缓存滤注释视图重试，
    成功且消费更多才采用（不影响原本成功解析面；全量/verilog 基线 5548 不变）。
  · 性能：cJSON 解析回溯成本仍 ~50–90s（#49 前已有，TODO 三），门禁单次 ≈90–110s。
  · 变异：新增 include 环境继承 + linter 注释回退两条（各自实测变红），清单 122 条。
  · 结果：判据 1–5 全过、主线 1 刻度 **9/9**；三任务路线图 T1 收口，进入 T2（pre_scan 专项）。

- **T1 预处理器宏展开时序收口（#51）**：定义时间线 + include 内预展开，真实语料
  **7/7 `parse_ok=True` syntax=0**（G4 #49 后唯一余量清零）。
  · A1：`_macro_events` 扩为 `{line,name,params,op,body}`；`expand_tokens(events=,
    clean_to_raw=, base_macros=, base_funcs=)` 逐行按"定义/取消事件"重建可见宏集
    （`#undef` 失效/重定义换体）；宏名正则 = 最终表 ∪ 事件名；`events=None` 保留旧调用面。
  · A2：include 在包含点用「扫描期 active 表 + 子文件事件」预展开子内容；宿主展开按
    `clean_to_raw is None` 跳过（不二次展开）；`parse_raw` 经 `preexpand_includes=False` 关闭。
  · 连带修复（真实语料暴露，缺一不可）：语句前同行注释（宏体尾注释被铺进流）致截断
    → `block_parser._skip_leading_inline_comments`；函数指针 typedef 名未注册
    （`direct.head.inner.direct.head` 括号声明符路径）→ `[Rule.parser] register.name_paths`
    补一层/两层；三元 `?:` 前夹注释致 linter pratt 误报 → 表达式检查器滤注释视图。
  · 验证：新增 `tests/engine/preprocessor/test_expand_timeline.py` 6 例；语料 7/7；
    C/e2e/policy 全绿；A/B 0/144；lint accuracy 33/33 fp0；render 124/124；pyright 0；
    变异新增 2 条（关时间线/关预展开均实测变红，清单 120 条）。
  · 残余登记：zutil `TAG001×2`（include-guard 跨 include 可见性边界）+ C 误报基线门禁
    （判据 5 收口，下一轮 #52）。

- **剩余三任务路线图 + T1 预处理器宏展开时序调查**（2026-10-23，循环 #50，docs-only）：
  作者把剩余工作定为 T1 宏展开时序 → T2 `pre_scan` 专项清理 → T3 C/Verilog 双包抽象对照
  按部件审查，路线落 `ROADMAP.md`「当前主线」（含顺序理由、每项判据指针、T3 部件序）。
  · T1 调查（新档 `docs/gaps/gap-preprocessor-macro-timeline.md`）：展开器逐行用**最终宏表**
    （host + 全部 include 终态），未建模 C 的可见性顺序（`#define` 起效/`#undef`/include 内
    定义序）。实测两形态（本文件原型后置定义、头文件原型后置 `gzgetc` 型）check 均
    `parse_ok=False` syntax 3；真实语料 5 文件即此。已列 A1 host 时序 + A2 include 内预展开、
    判据（最小 2 形态 + 7/7 语料 + 门禁 + 保真/幂等/A/B 0/144）与止损（A2 一轮不成就登记
    触发式边界、门禁按 2/7 partial）。
  · T2 立项（TODO 三）指向 ADR-0024 分片 + 67 条 skip 测试处置；T3 执行路线落
    `docs/gaps/gap-engine-abstraction-audit.md`（六部件序、每轮输出 leak 清单/判据②探针/
    第二语言复用实验/止损）。

- **G4 typedef 名强转收口：parser 内符号表 + 规则符号门控**（2026-10-22，循环 #49，
  方案 B，作者拍板）：
  · **引擎**：`parser/parser_core.py::_ScopeStack` 接线 `_symbol_gate`
    （`[Rule.parser] requires_symbol = {namespace, skip}`）与 `_register_symbols`
    （`[Rule.parser] register = [{name_path|name_paths, kind, when_marker?}]`）；
    `[parser] symbol_namespaces` 包声明面；`grammar_rule_fields.md` 同步登记。
  · **C 包**：`CastTypedefName` 新规则（typedef 名/限定符 + 指针；`CastExpr` 类型名
    两支 `@CastTypeName|@CastTypedefName`）；Declaration/ParamDecl/FuncDef 注册站点 +
    函数/块作用域帧。`else` 前独占行注释改独立 `ElseClause` 规则（内联组挡注释致
    cJSON 函数体截断）。
  · **退役**：parser 侧预扫描消费面删除（`pre_symbols`/`pre_hints`/`[pre_scan]
    rule_hints`；零消费，A/B 0/144）——ADR-0024 专项的 parser 前置切片。
  · **结果**：G4 最小矩阵 8/8、新增 22 例；真实语料 cJSON/gzread `parse_ok=True`
    syntax=0（余 5 zlib 文件 = 预处理宏展开时序，另案 TODO 1.3）；
    C 套件 1238 passed；A/B verilog 0/144；lint accuracy 33/33 fp0；render_coverage
    124/124；`c_acceptance` 49/0；变异 118 条（新增 register/门控两条，实测变红）。
    旧 M1/raw 资格测试 67 条 skip 登记（该面退役，随 ADR-0024 专项处理）。

- **G4 typedef 名强转调查/方案（「解析前符号判定」专项立项材料）**（2026-10-22，循环 #48，
  **docs-only**，未动生产代码）：真实语料门禁唯一前置。实测（check 路径）：
  · 最小矩阵 8 条中 5 条 `parse_ok=False`（函数内指针强转初值/return/if/for/文件域声明），
    另 3 条靠语句级 raw 已承载；**7/7 真实文件 parse_ok=False**，cJSON 56 条 syntax 主体即此；
  · 三类缺口：M1 形态只认 `(id)`（`(T*)` 不命中）、站点只覆盖 id 触发未收敛语句（关键字语句
    无内部 warning）、符号门依赖 pre_scan 且多行 typedef 只捕成 tag_struct（cJSON）；
  · monkeypatch 原型：放宽形态+去符号门可修最小用例与 cJSON 风格函数，但关键字语句/文件域
    仍缺站点；pipeline 展开路径 raw 不同源（check 路径同源可用）。
  方案：**B 推荐** = parser 内符号表 + 规则符号门控（单遍；复用既有 `_ScopeStack`/`[Rule.parser]
  scope` 帧/`scope_lookup_fn` 预留钩子；新增 `[Rule.parser] register`、`requires_symbol`、
  `[parser] symbol_namespaces`）——AST 正确、check/pipeline 同解、无需扩大 raw；
  A = 扩展 raw/两阶段（过渡备选）；C/D 否。判据草案（8 条最小矩阵 + 反例 `(a)*b`/遮蔽/
  后置使用 + 7 文件 parse_ok + 双路径 + A/B 0/144 + 变异）与止损见新档。
  决策点 = **引擎契约扩展属框架级，待作者拍板**；批准后可与 pre_scan 退役（ADR-0024）同批。
  文档：`docs/gaps/gap-c-typedef-cast.md`（新档，gaps README 登记）；`gap-c-real-corpus.md`
  G4 行、`ROADMAP.md` 阶段 5、`PROGRESS.md` 判据 5 与下一轮入口同步。

- **退出判据 3 收口 + 刻度块 7 收口**（2026-10-22，循环 #47，test-only）：新增
  `tests/languages/c/test_c_exit_criteria_negative.py`——四族代表负样本各被拒 + 正样本不误报：
  ① 作用域 = raw 安全网 **E002**（遮蔽例 `typedef int t; void f(){ int t; x=(t)y; }` ⇒ 管线失败 +
  E002；无遮蔽正样本闭环）；② 链接 = 存储类约束族 **CSC001–CSC012** 近似面（`typedef static` /
  `static extern` / `_Thread_local` 用于函数；正样本 `static inline` 不误报）——C 链接性完整规则
  （§6.2.2 跨声明，阶段 3 **S2**）按既有拍板**不采**；③ 标签 = **LAB001–LAB003**（重复 label /
  未定义 goto / case 无 switch）；④ 函数原型 = 语法非法原型被拒（`int f(...);` 无参数变参；
  正样本含 `int f(void)` / 变参 `int g(int, ...)` / 无原型 `int h()` / 新收口的抽象指针形参）。
  **S3 原型一致性（跨声明类型一致、`void` 参数约束）需类型模型 = 触发式搁置**：本文件反向锁定
  "当前不检查"（不一致原型/void 约束样本断言不报），防"看起来已覆盖"的误传。
  刻度：块 7 由 🟡 → ✅（S2 不采 + S3 触发式搁置均为登记边界，不属活跃缺口）；已完成 **8/9**
  块、加权约 **65–70%**；退出判据 1–4 全过，**判据 5 唯一前置 = G4（typedef 名强转 / 切片 1b
  = 解析前符号判定）**。

- **退出判据 4 收口：构造 × 标准档位断言面**（2026-10-22，循环 #46，test-only）：
  新增 `tests/languages/c/test_c_construct_standard_matrix.py`，把 `tools/c_acceptance.py::CASES`
  的 **49 条接受面构造**逐条挂上标准归属（C99 / C11 / C23；C17 为缺陷修正版、**无新语法**，
  插件目录只有 `tpc.toml` 已由测试锁定），并断言：① 清单与归属表一一对应（meta，防清单漂移）；
  ② 每条构造在**其标准档**解析完整且出现该构造的增量节点（C99 在 baseline 档）；
  ③ C11/C23 构造在**下档不可见**——下档解析截断或不含增量节点（宽进口径：未声明关键字被当
  普通调用静默接受是允许的，与 `test_c_standard_tiers.py` 头注同口径）。
  覆盖：47 条解析层构造上/下档 + 2 条预处理（归属 C99，接受面由 A2 `#include` e2e 覆盖）。
  判据 `pytest tests/languages/c/test_c_construct_standard_matrix.py`（70 例全绿）。

- **C 无名抽象指针形参（真实语料 G3 收口）**（2026-10-22，循环 #45，C 语法面）：
  C99 §6.7.6 允许 `parameter-declaration` 省略 declarator——`void f(void *, size_t);` /
  `int g(const char *, const char *);` 这类「只有 `*` 链（可带限定符）、无名字」的原型是
  真实头文件高频形态（zlib `void zmemcpy(void *, void *, z_size_t);` 等）。本包 ParamDecl
  只收具体声明符 ⇒ 整条不可解析（真实语料 zlib 族剩余误报主体之一）。
  修法：ParamDecl 声明符位增加两支**抽象**形态——`@Pointer`（`*` 链 + 限定符）与新增
  `TypedefAbstractDeclarator`（`@TypedefName @Pointer`，接 `const T *`）；具体声明符两支
  仍在最前（既有形态逐字不变，具名形参照常进符号表、无名形参不产生符号）。
  括号型抽象声明符（`int (*)(void)` / `int []`）**暂不收**（完整抽象声明符文法另一档，
  按真实语料触发再扩），判据锁定"仍被拒"。
  真实语料探针：zlib 族误报进一步下降——zutil 27→**7**、crc32 14→**4**、adler32 13→**3**、
  gzread 10→**0**、compress 12→**6**、uncompr 11→**5**、cJSON 56→**56**（余量全部 = G4
  typedef 强转/切片 1b）；7 文件仍截断（G4 致）。
  判据：`tests/languages/c/test_c_abstract_declarators.py`（16 例：5 目标形态 + 符号面 +
  具名/普通形参回归 + 边界拒绝）+ 档位基线档 1 例；`c_acceptance` 48 → **49** 条 / 空洞 0；
  门禁变异 **115 → 116**（`--only 116` 实测变红）；`tests/languages/c` 全量零回归。

- **C 声明说明符顺序自由 + 指针限定符**（2026-10-21，循环 #44，C 语法面；作者拍板走 B）：
  C 的 `declaration-specifiers` 顺序自由——typedef 名可出现在存储类/限定符之后
  （`extern size_t n;` / `const T *p`），而本包此前只允许 typedef 名在首说明符位
  （`SpecRest` 是贪婪重复、不能含 `@TypedefName`，否则 `int x;` 的 `x` 会被当类型名）。
  ⇒ 真实 C 语料 zlib（`ZEXTERN`）、cJSON（55 处 `const cJSON * const`）大面积截断/误报。
  修法（**纯语言包**，无引擎改动）：宿主声明符位做「**声明符优先**」交替——先按既有
  `@DeclaratorList` / `@Declarator` / `@InitDeclarator` 读（既有形态逐字不变），失败再读
  「`@TypedefName` + 声明符」，由三个包装规则（`TypedefDeclarators` / `TypedefDeclarator` /
  `TypedefInitDeclarator`）承载；节点绑定仿被包装规则的消费面（`items` / `declarator` /
  `direct`），使 `declarators.items`、`declarator.direct.head.content` 路径对两种包装一致。
  六个宿主：Declaration / FuncDef / StructMember / ParamDecl / ForInitDecl / TypeName。
  **指针限定符**（C99 §6.7.6 `pointer: * type-qualifier-list_opt pointer_opt`）：
  `@Pointer` 加 `@TypeQualifier*` ⇒ `int * const q;` / `const char * const s`。
  **方案选择**：曾评估引擎侧 `pre_scan` 驱动的 token 重定型（A）——否：只解 G1、与将来
  切片 1b 的符号感知机制重复投入、且引擎契约面新增；B 由原型 + 全量验证选定。
  **行为变化**：上述形态由「截断/误报」→ 解析完整 + linter 零诊断 + 渲染 token 逐项相同 +
  幂等；普通声明仍走第一支（`int x;` 等逐字不变；`_Atomic(int) x;` 因第一支已成功而不误读；
  块内 `myint *b;` 仍按表达式优先——既有口径不变）。
  真实语料探针（未入库）：cJSON 124→**56**、zutil 86→**27**、crc32 45→14、adler32 43→13、
  gzread 40→10、compress 36→12、uncompr 35→11（余量由 G3 未命名抽象指针形参 /
  G4 typedef 强转=切片 1b 解释，见 `docs/gaps/gap-c-real-corpus.md`）。
  判据：`tests/languages/c/test_c_declaration_spec_order.py`（**30 例**：6 宿主 + 指针限定符 +
  普通声明回归 + 符号收集 + 过接受边界）+ 档位基线档 1 例 +
  `c_acceptance` 47 → **48** 条 / 空洞 0；`tests/languages/c` 全量零回归；
  门禁变异 **113 → 115**（`--only 114/115` 实测变红）。
  **对抗审计（提交后独立复核）3 项成立，2 修 1 登记**：
  · A 修：包装规则曾用 `direct = "$2.direct"` 共绑同一子树 ⇒ `iter_children` 走两遍
    （重复符号记录 + TAG001 假阳性）；改只绑 `declarator`，`FuncDef`/`ParamDecl` 的
    `name_path` 用**候选路径列表**（语言包声明面）；
  · B **登记未修**：声明符优先交替回滚时不回收注释簿记 ⇒ typedef 名后的注释
    （行尾 / 独占行）可能被去重吞掉。试修（把行尾台账/锚点集纳入快照事务回滚）在
    C 形态可保注释，但**触发 verilog 注释恢复回归**（`test_comment_restore`
    幂等失败：端口注释位置漂移；锚点通道与既有领取/渲染协同复杂）⇒ 回退并登记
    （修法 = 事务化注释簿记 + 原子节点领取/渲染面协同，TODO 1.2；触发 = 真实语料
    出现该形态）。判据不锁"新形态注释保留"；行尾注释在交替中的丢失已用最小复现
    记录；
  · C 登记：交替第二支无符号表 ⇒ 过接受 `int a b;` / `unsigned T x;` / `sizeof(int T)`
    （宽进口径；linter 失去"漏逗号"检出，升级触发=真实语料/切片 1b）；
  · 另登记**既有**渲染边界：展平行内行尾注释的 LineSuffix 可能吞后续 token
    （`struct S { int // c\nx; };` 旧语法同坏；渲染修复另立项）。
  文档：`grammar/c/README.md`、`01_declarations.toml` 头注（SpecRest/过接受说明更正）、
  `docs/gaps/gap-c-real-corpus.md`（G1/G2 收口、审计 A/B/C、已知边界、G3/G4 余量）、
  TODO（G3 + 渲染边界）/ROADMAP/PROGRESS。

- **C23 枚举固定底层类型 `enum e : int`（标准等效缺口 1 → 0）**（2026-10-21，循环 #42，
  C 标准面 + 语义检查面）：C23 §6.7.2.2 `enum-type-specifier: : specifier-qualifier-list`
  此前未实现 ⇒ 合法标准代码被拒（oracle：gcc 16.1.0 `-std=c23 -pedantic-errors`；同批实测
  带体 / 不透明声明 `enum e : int;` / 限定符 / typedef 名 / 匿名体五种合法形态与两种拒绝形态）。
  修法：
  · **C 包语法面**：核心 `EnumSpecifier` / `AnonEnumSpecifier` 在"标签后 / 枚举体前"加
    **空槽位 `@EnumSpecExtra?`**（命名体与匿名体共用，一处注入两处生效；空槽位 = 不可匹配，
    ADR-0023）；c23 插件 `23_enum_underlying.toml` 注入 `: @MemberSpec`
    （`specifier-qualifier-list` 无指针，与标准同形）。档位门控 ⇒ 下档 `enum e : int …` 整体拒，
    既有 `enum e { A };` 基线行为逐字不变。
  · **语义检查面**（ADR-0021 行 6 的触发条件）：`tag_capture` 加 `complete_path`
    （`_api.py::_named_attrs` → 符号 attr `has_complete_type`）；ENUM003 按 C23 豁免——
    **带固定底层类型的枚举总是完整**，`enum E : int;` 不再误报（`_visible_complete_enum` 的
    "完整"判据同步为"带体或带底层类型"）。
  **行为变化**：c23 档 `enum e : int { A };` / `enum e : int;` / `enum : int { A };` 等接受、
  linter 零诊断、渲染 token 逐项相同 + 幂等；c11/c17 仍拒（空 AST + 诊断）。
  **登记边界**（gcc 拒 / 未实现，落 gap 档「仍存的接受边界」+ 用例锁现状）：
  ① 过接受 `enum e : int x;`（固定底层类型 + 声明符；语法层宽进，
  `test_known_over_acceptance_boundary` 锁现状）；② 枚举 tag 的"带 / 不带固定底层类型"
  混用约束（§6.7.2.2 约束句；语义检查未实现，触发 = 真实语料 / 检查需求）。
  验证：conformance 新增 `TestC23EnumUnderlying`（5 接受 + 绑定形状 + 非法形态拒绝 +
  过接受边界）+ 下档三态 1 条；c23 插件 `_CASES` 5 行 + 注入点表；档位矩阵 34 → 37 构造；
  类型语义正样本 13 → 16（ENUM003 豁免含 attrs 断言）；`c_acceptance` 46 → 47 条 / 空洞 0；
  缺口清单 1 → 0（`test_c_standard_conformance.py` 已无 `xfail` 用例）；全量
  **4339 passed / 7 skipped / 0 xfailed**；lint hit_code 33 / fp 0 / valid 7；
  A/B `--mode cli --products` verilog 0/144；pyright strict 0；`check_doc_refs` PASS；
  门禁变异 **110 → 113**（丢核心槽位 / 丢规则注入 / 去 ENUM003 豁免，
  `--only 111/112/113` 实测变红）。文档：`grammar/c/README.md`、`02_types.toml` 注释、
  c23 `tpc.toml` 头注、`checks/type_semantics/rules/{types.toml,_tag_check.py}` 头注、
  gap 两档、ADR-0021 行 6（已取回实现、按纪律从策略表删除 ENUM003 项）、
  `docs/MODEL_INDEX.md`、TODO/ROADMAP/PROGRESS。

- **C23 单参下划线拼写 `_Static_assert(1)`（标准等效缺口 2 → 1）**（2026-10-21，循环 #41，
  C 标准面 + 引擎档位面）：C23 §6.7.10 的消息可省对**两种拼写**都成立，但 c11 的
  `_Static_assert` 规则固定两参 ⇒ 合法标准代码被拒（oracle：gcc 16.1.0 `-std=c23
  -pedantic-errors` 接受；C11/C17 应拒）。修法：
  · **C 包**：c23 插件新增 `22_static_assert_no_msg.toml`（`keyword._Static_assert
    ( @Expression ) ;`，注入 `@Stmt` + `@StructMemberExtra` ⇒ 文件 / 块 / struct·union
    成员表三处作用域；渲染保留拼写）。与 c11 两参 `StaticAssertDecl` **同首 token 并存**，
    靠试解析区分（两参在 `,` 处让新规则失败、单参在 `)` 处让 c11 规则失败）；ADR-0023
    档位门控保证 c23 规则只在 c23 档加载 ⇒ c11/c17 的"两参必选"拒绝面不变。
  · **引擎**（同批修，缺陷由本轮判据暴露；前置提交 `ade7390`）：`LinterScanner` 构造时
    `load_all(enabled=None)` 把登记档位重置成包内 `[plugins] enabled` ⇒ 引擎级切档只对
    parse 生效、linter 静默回默认档（c11 档的 C23 形态被 c23 规则放行）。修法 = 构造时按
    `tier_state(rules_dir)` 显式传入当前档位（非语言包目录退化为空元组，行为同旧）。
  **行为变化**：c23 档 `_Static_assert(1);` 在文件 / 块 / struct·union 成员表三处接受、
  linter 零诊断、渲染 token 逐项相同 + 幂等；c11/c17 仍拒（空 AST + linter 诊断）。
  **测试口径修正**：`test_c_standard_conformance.py` 的 helper 去掉 `ext_dirs=[plugins]`——
  该参数按 ADR-0023「边界」不受门控，等于在测试里无条件上膛 c23 规则（旧捷径；生产
  CLI 的 `ext_dirs` 为空），去掉后判据与生产同路。
  验证：conformance 新增 `TestC23UnderscoreNoMsg`（3 作用域 + 两参不被抢）+ 成员位 1 行 +
  拒绝面 c17 1 条；c23 插件 `_CASES` 4 行；档位矩阵 31 → 34 构造；`c_acceptance`
  45 → 46 条 / 空洞 0；缺口清单 2 → 1 条（余 `enum e : int`）；全量 **4299 passed /
  7 skipped / 1 xfailed**；`tests/policy` 524 passed；lint hit_code 33 / fp 0 / valid 7；
  A/B `--mode cli --products` verilog **0/144**；pyright strict 0；`check_doc_refs` PASS
  （D1–D4 = 0）；门禁变异 **108 → 110**（丢成员位注入 / 丢插件清单登记，
  `--only 109/110` 实测变红）。文档：`grammar/c/README.md`、c23 `tpc.toml` 与
  `10_static_assert_alias.toml` 头注、gap「C 标准等效缺口」/「运行时档位」、
  `core/config_lifecycle.md` §7、`docs/MODEL_INDEX.md`、TODO/ROADMAP/PROGRESS。

- **C23 数字分隔符：引擎 `[[number.based]] digit_separator` 声明面**（2026-10-21，循环 #38，
  引擎词法面 + C 标准面）：`1'000'000` 此前被切成 `1` + 字符常量 ⇒ 合法 C23 代码整条解析失败
  （oracle：gcc 16.1.0 `-std=c23 -pedantic-errors` 接受）。修法：
  · **引擎**（`lexer/number_gen.py`）：`[[number.based]]` 可选单字符键 `digit_separator`——
    编译期在每个"数字自环态"旁挂分隔态（`S --sep--> S'` **非接受**、`S' --digit--> S`），
    故分隔符必须夹在数字之间：尾随 `1'` 的分隔符留给下一个 token、连续 `1''0` 在第二个处断开；
    分隔符按**字符类别**接入转移表，未知字符 / 与目标态已有出边撞键 → `ConfigError`
    （fail-fast，不静默丢声明）；未声明该键的形态逐字零变化（verilog / yaml / c4 不受影响）。
  · **C 包**（档位 = 声明面组合）：c23 插件**按名合并**给 `c_dec` / `c_prefix` 两形态补
    `digit_separator = "'"`（八进制 digit 序列也落在 `c_dec` 的 `digits = "any"` 里、扫描取
    最长 token，故 `c_octal` **不另声明**——原稿多写一条，实测是重复知识后删掉，见门禁变异
    106 的反向教训）；基线/c11 档不声明 ⇒ 仍切两个 token，引擎零语言判断。
  **行为变化**：c23 档 `1'000'000` / `0x1'F` / `0'7` / `0b1'0` / `1.5'0` / `1.0e1'0` /
  `1'000u` 各成单 token 并进 AST；位置非法形态（`0x'1` / `1.'5`）按**宽进口径**也不拒绝
  （同 `1ff`：词法只判"是不是一个数字 token"，拼写合法性归约束层）——干净对照 = 同引擎
  去掉声明后在第一处 `'` 断开（`test_wide_in_positions_not_validated`）。
  **同轮否掉的结论（落档）**：原计划同轮做的 **`enum e : int` 固定底层类型未做**——其形态只由
  核心 token（`:` + 类型词）组成，c23 规则文件注入会漏进基线/c11 档（`enabled` 只门控声明面），
  与 `_Static_assert(1)` **同因**；"绕得开（数字分隔符，收敛到声明层）/绕不开（这两条）"两个实例
  写进 gap「运行时档位」与审查台账 #1 行，本轮不动档位语义（ADR 0021 记"暂缓"）。
  验证：`test_number_digit_separator.py` 新增 17 例（声明面 fail-fast 5 + 扫描面 12，含无声明对照）；
  `test_c_lexer.py` 新增 `TestDigitSeparator`（7 形态单 token + 尾随/连续）与
  `TestDigitSeparatorTiers`（6 条逐档切分）；`test_c_standard_conformance.py::TestLiteralForms`
  增 7 条接受 + 2 条下档拒绝，缺口清单 **3 → 2 条**；`c_acceptance` **42 → 45 条 / 空洞 0**
  （顺带补上 #37 漏登记的字面量前缀族 / 二进制常量两条，恢复"工具清单与缺口档逐行对照"）；
  全量 **4249 passed / 7 skipped / 2 xfailed**；lint hit_code 33 / fp 0；A/B `--products`
  verilog **0/144**；pyright strict 0；`check_doc_refs` PASS（D1–D4 = 0）；门禁变异
  **104 → 106**（关掉分隔符展开 / 丢掉 `c_dec` 的分隔符声明，`--only 105/106` 实测变红）。
  文档：`lexer/README.md`、`docs/language_walkthrough.md`、`MODEL_INDEX.md`、
  `grammar/c/README.md`、`plugins/c23/{tpc,_number_c23}.toml`、gap 两档、TODO/ROADMAP/PROGRESS。

- **字面量前缀族 + C23 二进制常量：引擎 `[string] prefixes` 声明面**（2026-10-21，循环 #37，
  引擎词法面 + C 标准面）：C 的 `L"…"` / `L'…'`（C99）、`u`/`U`/`u8` 字符串与 `u`/`U` 字符
  （C11）、`u8` 字符与 `0b…`（C23）此前一律切成 `id` + `literal.string` 两个 token ⇒ 合法代码
  整条解析失败。修法：
  · **引擎**：`[string] prefixes = { 前缀 = [允许的定界符…] }` 声明面（`lexer/capture_runner.py`
    `_string_delim_rules`）——每个「前缀 × 定界符」一条捕获规则（start = 前缀+定界符），前缀进
    token **正文**、渲染原样输出；前缀与定界符必须紧邻；**不声明 = 无前缀语义**（其余语言包零影响），
    非法条目 fail-fast（前缀非空串 / 定界符须在 `delimiters` 中）。
  · **C 包**（档位 = 声明面组合）：核心基线声明 `L`（C99）；c11 插件补 `u`/`U`（两种字面量）与
    `u8`（字符串）；c23 插件把 `u8` 覆盖为两种定界符（C23 字符常量）。二进制走**按名合并**给核心
    `c_prefix` 形态加 `0b` 分支 + `b → bin`（`plugins/c23/_number_c23.toml`），基线/c11 档仍切两个 token。
  **行为变化**：上述字面量现在是单个 `literal.string` token 并进 AST（`char *s = u8"x";` 等）；
  未达档位的形态保持两 token（自然不进树）——档位判别由声明面决定，引擎无语言判断。
  验证：`test_c_lexer.py` 新增 `TestLiteralPrefixes`（8 形态单 token / 4 形态正文含前缀 / 紧邻性）
  与 `TestLiteralPrefixTiers`（12 条逐档切分）；`test_c_standard_conformance.py` 新增
  `TestLiteralForms`（10 接受端到端 + 4 逐档拒绝），缺口清单 6 → 3 条（余 `_Static_assert(1)`
  单参 / 数字分隔符 / enum 固定底层类型）；全量 **4201 passed / 7 skipped / 3 xfailed**；
  `eval_lint_accuracy` hit_code 33 / detached 0 / fp 0；`c_acceptance` 42 / 空洞 0；
  A/B `--products` verilog **0/144**；pyright strict 0；门禁变异 **102 → 104**
  （忽略前缀声明 / 丢掉 `0b` 分支）。文档：`lexer/README.md`（`[string]` 声明表）、
  `docs/language_walkthrough.md`、`grammar/c/README.md`、gap「C 标准等效缺口」、TODO/PROGRESS/ROADMAP。

- **引擎能力面全项审查：方法 + 台账建档**（2026-10-21，循环 #36，作者定方向）：C 包被重新定位为
  引擎抽象的**压力测试**（"每多一门语言多一套特殊处理 = 一个未审查的抽象"），刻度 7→9 完成后、
  P3/性能类改动之前做一次全项审查。本轮只落方法与台账、不改生产代码：
  · 判据 = **「能力 × 语言」矩阵 + 第二语言复用实验**（四态：原样 / 新声明键 / 新引擎代码 /
    逃生门；另有"方言复制"记录类）；"新引擎代码只服务一门语言" = leak 候选，"逃生门" = 必须
    消灭或降级；复用实验不做不算数。
  · 台账 = `docs/gaps/gap-engine-abstraction-audit.md`：首版 6 行（档位门控 / 同构造异拼写 /
    精化基座 / 文件链接与入口点 / 容器成员位（已过）/ 注释归属（已过）），每行带四态、证据与
    内置化方向；日常循环顺带补行（调查轮性质，不单独汇报）。
  · 决策记录 = `docs/decisions/0022-engine-capability-audit.md`（时机/判据/台账/维护纪律）。
  同步：`ROADMAP.md`「当前主线」加"刻度完成后的全项审查"入口；`docs/gaps/README.md` 登记新档；
  `docs/MODEL_INDEX.md` 跨子系统加一行。判据（纯文档改动，按分层验证的文档档）：`tests/policy`
  全绿（文档预算 / 引用一致性 / 变异锚点静态守）。

- **A/B 对拍工具产物摘要档（`--products`）**（2026-10-19，循环 #29）：CLI 档此前只对拍
  `tpc lint --json` 的 rc/stdout，声明"零可见变化"时仍要另写脚本比渲染产物。修法：
  `_cli_snapshot` 在 `--products` 下对每个输入再跑 `tpc format`，把 `{rc, stdout, stderr}`
  纳入 PRE/POST 快照；`tools/README.md` 同步一行。验证：`--mode cli --products
  --expect-changed 0` 实跑 **0/144**，JSON 中每文件含 `format` 键（错误样本 rc=1 也被记录）。

- **`check_doc_refs` D3 支持 blockquote 续行**（2026-10-19，循环 #27）：docs 里
  `> Impl: a.py` / `> Test: ...` 后的 `>` 续行此前不在 D3 视野（已删档 ADR-0017 引
  `test_macro_call_node.py` 而 D3 = 0）⇒ 续行里的悬空文件引用漏报。修法：
  `_rule_d3_impl_test_files` 按字段聚合 blockquote 续行（遇到新的 `Impl:`/`Test:` 字段或
  空 `>` 行终止），候选按**所在续行行号**报；裸文件名目录继承用整字段候选。验证：
  `test_check_doc_refs.py` 22→25（续行缺文件改前红；续行存在 / 新字段终止守卫）；policy
  全绿；门禁变异 **94→95**；全量/静态见收口记录（D3 为 docs 门禁，不触管线）。

- **跨盘路径显示回退**（2026-10-19，循环 #26）：Windows 跨盘输入（`C:` ↔ `E:`）时，
  `tpc check` 文本报告 `_print_file_diags` 与 HTML 报告 `_card_html` 直接调 `os.path.relpath`
  抛 `ValueError` ⇒ CLI traceback / HTML 报告崩溃。修法：`core.utils.safe_relpath` 捕获
  `ValueError` 回退原路径（显示用途，不改变诊断/退出码）；两处消费共用。验证：
  `test_safe_relpath.py` 2 条（改前红：函数缺失 / `_print_file_diags` 抛错）+ report_html
  1 条；门禁变异 **93→94**；core+analyzer 549；全量/静态/A-B 见收口记录。

- **A2 末片：include 顺序**（2026-10-19，循环 #25）：include 内容行此前写在指令行 marker **之前**
  （`handle_include` 先 `_inject_lines.extend`，`_handle_directive` 后注入 marker）⇒ clean 行序/行映射/
  渲染回插顺序错位；条件分支内的 include 内容还落到分支外。修法：`_emit_output_line` 统一输出归属，
  `_handle_directive` **先写 marker 再执行副作用 handler**（define/undef 无内容行，顺序无害），
  include handler 按当前条件栈把内容行写到 marker 之后（分支内同归属）。**行为**：`#include` 行在前、
  被包含内容随后；`clean_to_raw` 中 marker 映射宿主 include 行、内容行仍 None。验证：
  `test_include_order.py` 2 条（改前红：顶层 + 条件分支）；`test_scan_line_map.py` 期望同步更新；
  preprocessor 367、全量 4026/7、`c_acceptance` 42/0、lint 33/33·fp0、check 58/0/0/0、verilog A/B
  **0/144**（语料无 include，非预测的 2/144；以构造用例锁）、pyright 0；门禁变异 **92→93**
  （handler/marker 顺序回退）。**边界**：行数不变（1:1 marker + 内容拼接行），内容行仍不可映射。

- **A2 ① 续：跨行宏调用（实参跨行 / 名字-括号跨行）**（2026-10-18，循环 #24）：预处理 token 不区分
  换行（换行只是预处理空白）⇒ 函数宏的实参列表、名字与开括号都可跨物理行。此前逐行展开 ⇒
  `#define F(a,b) a+b` + `int r = F(1,` + 下一行 `2);` 原样保留（GCC `1 +2`）、`F` + 换行 + `(2)`
  不展开。修法：`_collect_call_args` **单行优先、未闭合逐行拼接**（`mask_spans` 对含换行文本本就
  正确；首个显著 token 非 `(` 立即止损；上限 **256 行 / 8192 字符**，超限不展开、不部分消费）；
  `_apply_cross_line` **保持行数不变**：首行 = 行首~调用列 + 宏体、中间被吞行置空、尾行留闭括号后
  原文 ⇒ `out_to_src` 仍按"clean 源行 → 输出行"对齐，宏体含 `\n`（如实参里的跨行块注释）时新增行
  映射调用起始行；区域 `source_text` = 完整跨行原文、新增 `src_end_line`（闭括号行）。仅 **splice**
  处置支持（line/inline 如 verilog 空体宏保持旧行为）；接缝重扫不跨行；同行普通宏与跨行调用可共存
  （区域条目统一 8 元组——审计 C1 的混合行崩溃已修）。**行为变化**：C 与 verilog **splice** 宏的
  跨行形态现展开（verilog 语料 A/B **0/144**；line/inline 形态不变）。**性能**（审计 C2）：前瞻
  早退 + 字符上限 ⇒ 200 行"函数宏名裸用"文件 ~24ms（修前实现 9.1s / 60.9s 量级）。验证：新增
  `test_macro_multiline_call.py` 22 条（4 类改前红：两行/三行实参、名字-括号跨行、`#__VA_ARGS__`；
  混合行、前瞻上限、性能守卫、渲染 token 保真、行映射不变式；line/inline 守卫）；
  `test_c_macro_end_to_end.py` P0-9 转 GREEN；`test_c_macro_args_checks.py` 19→25（跨行 arity +
  尾行位置映射）；门禁变异 **90 → 92**（禁跨行收集 / 混合行区域元组缺项）；全量/精度/A-B 见收口记录。
  **边界**（登记）：line/inline 跨行不展开、接缝不跨行、前瞻上限外不展开、渲染面行结构可重排
  （token 序列保真）、沿用最终宏表。

- **A2 ① 续：接缝重扫（token 级重扫边界①）**（2026-10-18，循环 #23）：C99 §6.10.3.4"替换列表连同
  其余源码一起重扫描"——此前文本层逐调用替换后不再与源码合流：`#define g f` + `g(2)` 得 `f(2)`
  （GCC `2+1`）、`f(2)(9)` 得 `2*g(9)`（GCC `2*9*g`）。修法：`_expand.py::_rescan_junction` 在"宏体 +
  源码后续"接缝处，若宏体最后一个函数宏名（前缀语言还要求其前是声明的前缀 token）后跟 `(...)`，则
  合成新调用继续展开；消费的源码字符并入该调用区间（**区域/锚/行映射复用既有机制**，输出行数不变）；
  循环预算 `max_iterations` 兜底。**接缝调用的 hideset 按 Prosser 交集口径**（名字 token ∩
  实参/闭括号 token；源码实参 hide 为空 ⇒ 接缝处通常为 ∅；替换文本 hide = 交集 ∪ {宏名}）
  ——`f(2)(9)` 得 `2*9*g` 的必要条件（不取交集会停在 `2*f(9)`，GCC 实测）；`macro_expand` 增
  token 返回变体（`expand_text_tokens` / `substitute_call_tokens_tokens`）供接缝保留 hideset。**顺带修**：名字与 `(` 之间注释按翻译阶段 3
  当空白跳过（`f /*c*/ (2)` 此前不展开；GCC 一致）。**接入事实面**：接缝展开出的函数宏调用照记调用点
  事实（MAC001 覆盖；外层/内层同一文本点各一条，不合并）。**行为变化（C 与 verilog 前缀语言输入）**：
  上述形态由"原样保留/展开不足"变为继续展开；verilog 语料 **A/B 0/144**（含后缀链）——语料无接缝触发，
  正确性靠构造用例守卫。验证：新增 `test_macro_rescan.py` 14 条（4 条 PRE 红判据：`f(2)` / `2*g(9)` /
  `f(2)` / `` `f(2) `` → POST `2+1` / `2*9*g` / `2*f` / `2+1`；自引用、过度接缝、递归、无括号 4 条守卫
  显式标注"改前绿"）；e2e 守卫 P0-8/P0-10 改期望；`test_c_macro_args_checks.py` 19→22（接缝 arity /
  同点双事实 / 定义前边界）；门禁变异 **88 → 90**（禁接缝重扫 / 接缝 hideset 不取交集）；全量/精度/A-B
  见本轮收口记录。**边界**（登记）：实参跨行、名字-括号跨行（逐行展开不接）、接缝沿用最终宏表
  （定义前调用也重扫；检查侧按定义时间线过滤不误报）。

- **A2 ①：宏实参个数检查（插件侧 check 族，MAC001）**（2026-10-18，循环 #21）：作者定"语义级走插件侧
  check 族"的首个预处理器语义检查。**引擎侧只给事实**：`expand_tokens(out_invocations=...)` 记录函数宏
  调用点 `{name, slots, single_empty, params, line, column}`（行/列为 clean 源坐标）；`map_invocations_to_source`
  一次完成回源 + 过滤（被包含内容行 / 行拼接段首行 / 当时不是函数宏的点）+ **宏定义时间线**
  （`scan_directives(out_macro_events=...)` 事件表 → `macro_timeline.params_at`）把 `params` 修正为**调用点
  时点**值——展开器仍用最终宏表（历史近似），检查侧顺序语义不跟着错（后置定义 / 重定义 / `#undef` 前后
  不误判；审计反例实测修复）。`[[analyzer.postpasses]]` 增同族键 **`ast_optional`**（解析失败文件也执行
  ——实参不足常使展开结果语法非法，正是该报的那批）＋ `AnalysisTraversal.analyze_file_facts` ＋
  `core._protocol` 新键 `CTX_MACRO_INVOCATIONS` ＋ 合成节点 `_pos_original`（位置已是原始源坐标 ⇒
  序列化不再经行表回源）。**C 包** `plugins/checks/macro_args/`：`MAC001`（A 档：C99+TC N1124 §6.10.3
  段 1903/1904/1918 原文；gcc 16.1 四档 `-pedantic-errors` 对拍）——非变参宏 `slots == 形参数`（0 形参
  的唯一合法形态 `Z()`，`Z(/*c*/)` 注释算空）、变参宏 `slots >= 具名数`。**行为变化（C 输入、`tpc check`）**：
  多给实参（`F(1,2,3)`，展开后语法合法、此前静默 rc=0）现报 `[warning](MAC001)`；零形参宏传参 `Z(2)`、
  变参缺具名 `W(1)` 现报；**少给**（`F(1)` → `1+` 使 parse 失败）在语法诊断之外**新增** MAC001，位置指
  **原始源行**（条件块压缩后仍对）。severity=warning（不阻断管线；`checks.overrides` 可提级为 error）。
  **配套修正**：`main._apply_check_suppressions` 对 parse 失败文件只跳过**语法**豁免——语义诊断
  （本检查的 too-few 场景）仍可 `tpc-check: disable-line` 豁免；`pyrightconfig.strict.json` 补
  `grammar/c/plugins`（先前 C 包插件不在 strict 检查面）。**边界**（规则表登记不实现）：变参"恰好具名"
  （C99–C17 pedantic 级、C23 起接受）、宏体替换产生的嵌套调用、`#if` 表达式内调用、实参跨行调用、
  被包含文件内调用点（头文件定义按 include 行快照）、行拼接段内调用点、`#undef` 之前的调用点
  （展开器最终宏表 ⇒ 根本不展开）。验证：新增 `test_macro_call_sites.py` 17 / `test_macro_timeline.py` 13 /
  `test_c_macro_args_checks.py` 19 / `test_postpass_ast_optional.py` 5 / 合成坐标用例 2；门禁变异
  **82 → 87**（调用点事实 / `ast_optional` 执行 / 零参判定 / 原始坐标跳过回源 / 定义时间线过滤）；
  PRE（HEAD 代码）新判据 **30 failed + 1 error / 16 passed** → POST 全绿；全量 **3952 passed / 7 skipped**；
  policy **458 passed**；pyright strict **0**（本包插件已纳入 strict 面）；A/B verilog **0/144**。

- **`pre_scan` 退役改为「暂缓专项整治」**（2026-10-22，作者拍板；docs-only）：作者判断
  "让 lexer 做预扫描是耦合设计，不太好"，但处理应**专项整治**而非日常刻度逐片推进——
  **先完成刻度主线，之后再集中力量去掉该机制**。处理：ADR-0024 状态改 `deferred`
  （设计、消费面实测、分片 S1–S5 与判据保留，取回即执行）；`ROADMAP.md` 新增 P2.9
  （触发 = 刻度主线完成；含实测现状：唯一承重 = C linter raw 资格、parser 提示面零消费
  A/B 0/144、两期产物无消费者、机制提及 37 文件/236 行）；`TODO.md` §3.1 执行项移除
  （暂缓项不进 TODO）；`docs/README.md`、`MODEL_INDEX.md`、两份 gap 档同步改"暂缓"口径。
  `PROGRESS.md` 下一轮入口回到刻度主线：G3 未命名抽象指针形参。

- **决策：退役 lexer 预扫描，改两阶段 lint（ADR-0024）**（2026-10-22，#45 调查/设计轮；
  **docs-only**，未动生产代码）：作者判断 `pre_scan`（lexer 后、parser 前的文本级正则扫描）
  信息量不足以支撑符号判定，要求"延后到分析阶段"。本轮实测消费面后立项：
  · **唯一承重消费** = C linter 的 raw 资格（`typedef` 名集合 + kind 过滤 → 换型试解析 →
    `symbol_dependent/eligible` → M2 摘诊断 + parser raw 承载）；禁用后合法 `x=(myint)y;`
    由 0 诊断变 1 误报 + parse 截断，C 语言套件 9 红、linter 定向套件 33 红；
  · parser 候选重排（verilog `rule_hints`）**实测零消费**（去掉后 A/B 0/144、无测试引用）；
  · C 产物"两期"（`two_phase_product`/`PHASE_PRE_SCAN`）管线无消费者（仅测试/文档引用）；
  · `raw_exclude_rules` 只是借配置段读取（语义与符号无关，可迁 linter 自有面）。
  决策 = **两阶段裁决**：lint 符号无关（双读试解析定候选 raw；替换 token 型由包声明）→
  parse raw 承载（不变）→ **analyze 权威裁决**（既有 E002/E003 安全网），随后删除
  `pre_scan` 机制本体；`tpc lint` 明确为"纯语法检查 + deferred 候选"，最终裁决在 `tpc check`。
  分片 S1–S5（每片独立绿、S4 前可逐片回滚）与判据（A/B 0/144、lint accuracy 33/33 fp 0、
  全量套件、C 语料诊断不增、`c_acceptance` 48/0）见 ADR 验证节。
  文档：新增 `docs/decisions/0024-two-phase-lint-prescan-retirement.md`（导航登记于
  `docs/README.md`）；`gap-c-semantic-base.md` 决策 ③⑧ 与预扫描期条目注方向变更；
  `gap-parser-linter-approximation.md` M1 段注符号无关化；`ROADMAP.md` 切片 1b 段、
  `TODO.md` §3.1（S1–S5 执行项）、`PROGRESS.md` 下一轮入口、`MODEL_INDEX.md` 行注"退役中"。

- **C 真实语料调查第二轮：根因更正 + 语法面方案（决策材料）**（2026-10-21，循环 #44，
  **决策轮**；未动生产代码）：#43 把两类缺口判成"linter 单侧误报"**不成立**——实测
  `parser._parse_truncated=True`（部分 AST），根因在**语法面**：「typedef 名」只在首个说明符位
  可用，`SpecRest` 刻意不含它（贪婪重复会吃掉声明符名），于是 `extern T *p;` /
  `const T *p`（含成员位 / 参数位 / `sizeof` 类型名位 / 函数定义位）共 **6 个宿主形态**
  整条无产生式可匹配；真实语料 zlib（`ZEXTERN`→`extern`）与 cJSON（55 处
  `const cJSON * const`）命中。另更正：`ProjectChecker` 结果 dict 的 `parse_ok` 字段
  **不反映解析截断**（部分 AST 也 True），判完整须用 `parser._parse_truncated`。
  方案 A（引擎 `pre_scan` 驱动的 typedef 名 token 重定型，与语言包既有
  `type_name`/`trial_as` 声明同族）**命中「引擎↔插件边界」⇒ 需作者拍板**；
  方案 B（纯语言包 6 宿主"声明符优先"交替）可细节级自决但影响面大
  （`_Atomic(int) x` 这类"限定符即类型"是已知陷阱）；C 否。
  文档：`docs/gaps/gap-c-real-corpus.md`（现状表更正 + 6 宿主最小复现矩阵 + 两方案 +
  判据草案 sanity 改为 `_parse_truncated`）+ `PROGRESS.md` 下一轮入口。

- **C 真实语料接入调查：方案与判据草案 + 两类 linter FP 最小复现**（2026-10-21，循环 #43，
  调查轮；**docs-only**，不动生产代码）：退出判据 5（真实 C 语料误报基线进门禁）此前空白，
  本轮实测确认**当前不可直接落地**：
  · **语料 / harness**：候选 = cJSON（MIT，2 文件 97KB）+ zlib 子集（zlib license，6 文件
    ~130KB + 头）；前置 = 库头文件 + **12 个最小系统头 stub** + `include_dirs`（C 包
    `include.on_missing = "error"`，缺 include 是硬错误）。7 文件实测 **parser 全接受**。
  · **误报面**：linter 在**合法代码**上报 35–124 条/文件（`cJSON.c` 124、`zutil.c` 86、
    `crc32.c` 45、`adler32.c` 43、`gzread.c` 40、`compress.c` 36、`uncompr.c` 35）——与
    verilog 先例"已裁决真诊断基线"性质不同，直接固化会把误报制度化。
  · **两类已定位根因**（parser 接受 / linter `phase-statement`，最小复现见档内）：
    `typedef int T; extern T *p;`（zlib `ZEXTERN` 形态）与
    `typedef struct S S; int f(const S * const p);`（cJSON 55 处 `* const`）。
  方案 A（推荐：先修 FP #44 → 再门禁 #45）/ B（过渡基线、须标注待清偿）/ C（否：合成语料，
  不满足"真实"）；判据草案（语料目录 + `CREDITS.md` + `stubs/`、`eval_diag_baseline_c.py`、
  `tests/policy/test_diag_baseline_c.py`、`parse_ok` sanity、确定性、预算与止损点）全部落
  `docs/gaps/gap-c-real-corpus.md`。文档：新 gap 档 + `docs/gaps/README.md` 登记 +
  `ROADMAP.md` 阶段 5 指针 + `PROGRESS.md` 判据 5 / 下一轮入口。

- **档位门控：可选组件的 grammar 文件随 `enabled` 加载（ADR-0023）**（2026-10-21，循环 #40，
  引擎契约 + 行为变化；作者拍板"只能走 A"，并强调**提交节点要小心** ⇒ 本轮一个原子提交：
  语义、配套引擎修复、测试与文档同批）：`enabled` 此前只门控**声明面**，插件规则文件由
  `setup_grammar` 无条件加载 ⇒ "档位 = 接受域"对不依赖新关键字的增量不成立（`[[属性]]` 基线档
  也解析），并卡住两条 C23 合法标准代码（`_Static_assert(1)` / `enum e : int`，同因受阻、
  #38 已证无法收敛到声明层）。修法：
  · **语义**：**可选件**（包内 `[plugins] enabled` 清单里的组件名）的 `[grammar] files` 只在
    当前档位含它时加载；未列出的**常驻件**（C 的 `semantics`/`checks/*`）与**全部 Python 组件**
    恒加载（"怎么分析"不是"收哪些语法"）。档位来源沿用既有优先级。
  · **实现**：`ConfigRegistry.tier_state`（相对/绝对两种包路径风格都命中——只按一种风格查会
    静默退回包内清单）→ `load_all_components(declared_optional, active_tier)` →
    `get_component_grammar_files` 过滤；非语言包目录两者皆空 ⇒ 不过滤（旧行为）。
  · **配套引擎修复**（门控暴露的两个旧缺陷，缺一即挂）：① **空槽位不可匹配**——非块 +
    `production = []` 是"没有形态"而不是"匹配空"（门控后基线档首次出现未被注入的空槽位；
    旧语义下 `@Slot*` 迭代项零进展 ⇒ repeat 死循环 + 属性绑定告警风暴，实测挂起）；
    ② **repeat/plus 零进展守卫**——空匹配（零 token）不算一次迭代，`+` 达不到 min_count 即失败。
  **行为变化**：C 的基线/c11/c17 档不再加载 c23 规则 ⇒ **纯语法增量也受档位**（`[[属性]]` 从
  c23 档起，方向 = 接受域）；verilog / yaml / c4 **零行为变化**（verilog 9 个 grammar 组件全在
  `enabled` 清单里、yaml 无组件、c4 仅 transform 组件）。
  验证：`test_tier_gated_grammar.py`（11 例：规则表随档 / 常驻件不受影响 / 双路径 `tier_state` /
  非包目录退化）+ `test_production_engine.py::TestRepeatZeroProgress`（空匹配收敛 2 例）；
  tier 矩阵 **31 构造 × 4 档**（属性行改为 c23 起、空槽位基线档回归 3 例）；全量
  **4271 passed / 7 skipped / 2 xfailed**；
  lint hit_code 33 / fp 0；A/B `--products` verilog **0/144**；pyright strict 0；
  `check_doc_refs` PASS（D1–D4 = 0）；门禁变异 **106 → 108**（去掉 grammar 档位过滤 /
  空槽位当可匹配，`--only 107/108` 实测变红）。文档：`docs/decisions/0023-tier-gated-grammar.md`
  （新增；ADR-0021 原"暂缓"行取回并删除）、`core/config_lifecycle.md` §7、
  `core/component_protocol.md`、`grammar/grammar_rule_fields.md`、`grammar/c/README.md`、
  gap 两档、MODEL_INDEX、TODO/ROADMAP/PROGRESS。

- **档位门控决策材料落档（#39 调查轮，待作者拍板）**（2026-10-21，仅文档、无生产代码）：
  C 标准等效缺口最后 2 条（`_Static_assert(1)` / `enum e : int`）同因受阻于 `[plugins] enabled`
  只门控声明面（ADR 0021 现记"暂缓"）；#38 已证两条都**不能**收敛到声明层。本轮把候选材料
  写进 ADR 0021「候选材料」节：**A（推荐）**= 可选件（名字在包内 `enabled` 清单里）的
  `[grammar] files` 随档位加载（引擎 ≈50 行、语言包 0 行、Python 组件不动；并把 C 的
  keyword-free `[[属性]]` 一并纳入档位）；**B**= 维持现状、两条缺口继续 `xfail` 挂账。
  关键约束：**不能**按"名字 ∈ enabled"门控整棵组件树（C 的 `semantics`/`checks` 是常驻件、
  无 grammar）；两包现状与该判据吻合（verilog 9 个 grammar 组件全部在 enabled 清单里）。
  `PROGRESS.md`「下一轮入口」改为"#40 待拍板后做门控"。判据草案（若取 A）：
  `test_c_standard_tiers.py` 矩阵 2 行改档位 + `TestKeywordFreeIncrementsAreNotTierGated`
  改写为"基线档不认属性"（该测试头注已预告）+ 门控判据 3–4 例 + verilog/yaml/c4 全量零回归。

- **任务循环：调查/实现分轮 + 因果句对照纪律 + 分层验证 + 状态入口**（2026-10-21，循环 #34，
  协作制度）：作者确认的四项调整落进 `policy/collaboration.md`「任务循环」与执行细则：
  ① **轮型分耦**——调查轮交付"位置/方案/反例/判据草案"（落档到实现轮能检索即可，**不要求修好、
  结果不必向作者汇报**），实现轮才动生产代码；同一缺陷 1+n 轮属正常；
  ② **因果句必须带对照**——写进 CHANGELOG/头注/gap 的因果解释要附干净 A/B 对照或标「未对照」
  （先例即循环 #33 的错误归因：把"两条同首 token 规则导致 linter 二义"写进版本库，实测真凶是
  同时注入 `@StructMember` 污染 FIRST）；
  ③ **验证分层写实**——文档/语言包/引擎三类改动各自的测试范围，全量只在跨子系统轮与里程碑跑
  （此前"每轮全量"是测试目录整理前的保守做法）；
  ④ **状态入口**：`PROGRESS.md`「当前时刻」改「下一轮入口」三行（意图/待验证假设/要更正的结论），
  每轮替换不追加——压缩或换 session 后的恢复入口。
  同步：`PROGRESS.md` 数字口径改为"通过数不入档、未通过数必记"（复现用命令），`ROADMAP.md`
  阶段 5 入口去掉通过数硬编码。判据（纯文档改动）= `tests/policy`（文档预算 / 引用一致性 /
  变异锚点静态守）全绿。

### Fixed

- **静态断言补全三处作用域（struct/union 成员表）+ C23 改分派器两分支**（2026-10-21，循环 #35，
  C 标准面；含一条旧结论更正）：① C11 §6.7.2.1 的成员表位（`struct s { int a;
  _Static_assert(1, "x"); };`）此前整条解析失败——修法 = 容器级**空槽位**：核心
  `StructBody = { (@StructMember|@StructMemberExtra)* }` + 空规则 `@StructMemberExtra`
  （`inline` + 渲染兜底声明，同 `@AttributeSlot` 先例），c11/c23 插件把静态断言注入该槽位，
  **不碰 `StructMember` 自身**（注入它会让 FIRST 混入 `keyword._Static_assert`、顶层同类语句
  被分类成 `StructMember` 报 `phase-statement` 假红——旧 #33 笔记的"同首 token 二义"即此，
  干净对照已翻案，`policy/collaboration.md`「因果句必须带对照」以此为反例）。② C23 两形态
  改为 Verilog `FuncDecl` 同款的 **inline 分派器 + 两分支**：`StaticAssertC23Decl`（分派器，
  不进 AST）→ `StaticAssertC23MsgDecl` / `StaticAssertC23NoMsgDecl`（贴 §6.7.10 的两条
  产生式，免掉尾随可选组的嵌套绑定）。**行为变化**：成员表位现接受 `_Static_assert`（c11+）
  与 `static_assert`（c23+，含单参），渲染 token 逐项相同、幂等、成员顺序保持；C23 静态断言
  节点名由单一 `StaticAssertC23Decl` 变为两分支名（dump/分析侧需按新名匹配）。
  验证（分层按新制度：语言包改动 ⇒ 该包 + 相关引擎子系统 + policy + A/B + 变异）：
  `test_c_standard_conformance.py` 新增 `TestStaticAssertMemberPosition`（接受 5 形态 / 顺序 /
  拒绝 2 形态）+ 缺口清单 9 → 6 条；C 包 **955 passed / 6 xfailed**（成员位 3 条 xfail 转正）；
  `tests/engine/linter` 全绿（空槽位不触碰候选表模型）；policy 全绿；`eval_lint_accuracy`
  hit_code 33 / fp 0；`c_acceptance` 42/0；A/B `--products` verilog **0/144**；pyright strict 0；
  门禁变异替换 2 条陈旧项（#33 的可选组/绑定）为新设计的两条（成员位槽失效 / 分派器丢单参分支），
  总数仍 **102**，`--only 101/102` 待跑。

- **C23 单参静态断言（消息可省）被拒 + 标准等效断言面第一批**（2026-10-20，循环 #33，
  C 标准面）：C23 §6.7.10 起 `static_assert` 的消息可省（`static_assert(1);` 合法，两种拼写
  同语法），此前 c23 插件只认两参形态 ⇒ 合法 C23 代码整条解析失败。修法：`StaticAssertC23Decl`
  的产生式把 `(comma, literal.string)` 改为**尾随可选组**、`message` 绑组内第二元素
  （`$4.sub_node[0].sub_node[1]`），布局用 `{ opt = { group = [", ", { ref = "message" }] } }`
  ⇒ 一条规则覆盖两形态（**不能写两条规则**：同首 token 会让 linter 语句发现二义，实测
  `_, "x"` 被留成 `phase-statement: unexpected end of statement`）。**新增断言面**（阶段 5
  缺的那片）：拒绝面 6 条（缺消息 / 消息非字符串 / 多实参，c11 与 c23 各一组，断言
  "不误读 + 空 AST + linter 有诊断"）、下档三态 8 条（generic / rejected，"未声明关键字 ≠
  拒绝"）、标准缺口清单 9 条（`xfail(strict=True)`：修好一条红一条）。**同时用外部 oracle
  （gcc 16.1.0 `-std=c11|… -pedantic-errors`）照出 8 类合法但被拒的标准项**（静态断言的
  struct/union 成员位、`_Static_assert(1)` 单参、`u8` 字符串与字符字面量、二进制常量、
  数字分隔符、`enum` 固定底层类型），全部登记在
  `docs/gaps/gap-language-pack-scope.md`「C 标准等效缺口」+ `TODO.md`（两条最难项各有
  框架级前置：linter 候选表按"一条规则 = 一种形态"建模 / 规则文件不按 `enabled` 门控）。
  验证：`test_c_standard_conformance.py` 15 passed + 9 xfailed；`test_c23_increment_plugin.py`
  +4 用例；档位矩阵 26→27；门禁变异 **100→102**（可选组退回必选 / 消息绑定少一层）；
  全量 / pyright / A-B / lint 精度见收口记录。

- **初始化列表内注释：丢 / 双份 / 前移三症状**（2026-10-19，循环 #32，引擎注释归属面）：
  行中注释归属有三个引擎缺陷：① `inline` 通道按 `context.current_rule` 判——内层 inline
  规则（`Initializer`）返回或失败探索后 `current_rule` 残留，容器（`InitList`）内注释被挂成
  "节点前置"、并因回溯双收集渲两份（`{1, 2, /* c */ }` → `/* c */ /* c */ {1, 2,}`）；② 闭
  括号前的注释走行内锚，锚到原子节点（`Number` 是 `ref` 布局）定位不到 ⇒ **整条注释丢失**
  （`{1, 2 /* c */ }`）；③ 同一注释在失败迭代与成功上下文各归一次（端口表
  `input clk, /* c */` 曾渲两份）。修法：`Node._rule_name` 内部元数据（建节点的规则名，
  `Node.dump` 过滤下划线）→ 通道按**节点自己的规则**判 inline；闭括号前（引擎
  `BRACKET_R_PREFIX` 判定，非语言知识）走 `trailing`；同节点同位置按 (文本, 行, 列) 去重
  （不跨节点——跨节点残留由 join 消费）；**原子节点**（无子节点）未消费的 `inline_after`
  兜底为节点尾行尾注释（容器不兜底，防跨节点重复）。**行为变化**：`{1, /* c */ 2}`、
  `{1, 2 /* c */}` 注释留在原位；`{1, 2, /* c */}` 的注释移到 `}` 后（gap 登记 #11，单份 /
  幂等优先）；端口表内注释恢复单份。验证：`TestInitListInnerComment` 3 形态 ×2、
  `TestInitListInnerComments` 槽位契约 3、`TestLeftoverInlineAfter` 3；PRE（HEAD 引擎）
  **11 红** → POST **142 passed**；`test_comment_restore.py` / pratt 注释组全绿；引擎
  parser+renderer+languages **1852**；全量 **4103 passed / 7 skipped**；pyright strict 0；
  `eval_lint_accuracy` hit_code 33/33 / fp 0；A/B `--products` verilog **0/144**；门禁变异
  **97→100**。

- **初始化列表尾随逗号静默丢弃**（2026-10-19，循环 #31）：`InitList` 产生式的 `symbol.base.comma?`
  （`$3`，`}` 前的尾随逗号）是**独立可选元素**、此前未绑进 node ⇒ 渲染器对未绑定可选元素静默丢弃
  （实测 `int a[] = {1, 2,};` → `int a[] = {1, 2};`，丢一个非 trivia token、判据 7 红；产物仍合法）。
  修法同 `EnumBody` / c23 属性表：绑 `trailing_comma = "$3"` + 布局在 `}` 前
  `{ opt = { ref = "trailing_comma" } }`（**不得塞进 `items`**：join 的 `sep` 会叠加成 `, ,`）。
  **行为变化**：初始化列表尾随逗号原样保留（单元素 / 显式长度 / 嵌套 / 指示符 / 多行形态），无尾逗号
  形态不多印；verilog/yaml 无涉。验证：`test_c_render_fidelity.py` 新增 `TestInitListTrailingComma`
  （6 带尾逗号 + 5 无尾逗号形态 ×3 判据 = 27 条；改前 **6 红**——6 个带尾逗号形态的 token 序列，幂等与
  "不多印逗号"反向门改前绿 = 回归守卫）；全量 **4082 passed / 7 skipped**；`render_coverage.py grammar/c`
  仍 **112/112**；`config_sites.py check` PASS；pyright strict 0；门禁变异 **96→97**（去掉
  `trailing_comma` 绑定）。
  **顺带登记**：初始化列表**内注释**三症状（丢 / 双份 / 前移，`inline` / `inline_after` 槽面）属独立
  缺陷 ⇒ gap 新增 **#11** + TODO（未修，循环 #32 候选）；`grammar/c/README.md` 写包者须知第 8 条
  补"标点类尾段走单独绑定"的修法。

- **行终止注释不得就地落地：`Union` 回退分支（引擎面；C 包注释吞 `;` 四形态）**（2026-10-19，循环 #30）：
  `_resolve_suffix_union` 在两支挂起后缀（pending）不同时"各自就地落地"（`_append_suffix` 把 `//`
  注释写成 branch 末尾的 Text），父级同行后续 token（`;`/`,`/声明符）印在注释之后 ⇒ 二遍渲染时被并进
  注释、**产物非法**。四形态实测：`enum e {A, B, // note` + `};`、`struct s {…} // note` + `;`、
  `int a[] = {1, 2} // note` + `;`、`enum e {…} // note` + `} v;` → 首遍 `…} // note;`（终结符消失），
  二遍 `parse truncated`。**根因纠正**：旧缺口档记成"`EnumBody` 无 tail 段"，实测 struct / 初始化 /
  带声明符形态同样红 ⇒ 与语言包布局无关，是 2026-09-20「行尾注释跨层上提」修法留下的 `Union` 回退
  缺口。修法：两支 pending 不同时不再就地落地，**强制 broken 支并把其 pending 继续上提**（父层在下一个
  换行点前落地）；生产形态里 flat 是 broken 的 `flatten` 副本、同一 suffix 两支都有 ⇒ 选 broken 不丢
  注释。**行为变化**：四形态注释移到语句行尾（`enum e {A, B,}; // note`），二遍幂等、显著 token 序列
  不变；verilog/yaml/C 现有语料无可见变化（A/B `--products` verilog **0/144**；全套 **4048 passed /
  7 skipped**）。验证：`test_doc_line_suffix.py` 新增 `TestLineSuffixUnion` 3 条（纯 Doc 级；改前红：
  `a // note;` → POST `a // note\n;` / `a; // note`）、`test_c_render_fidelity.py` 新增
  `TestLineCommentBeforeTerminator` 4 形态 ×2（改前 8 红：PRE 四形态 token 不等且二遍解析截断）；
  门禁变异 **95→96**（回退就地落地）；pyright strict 0。**登记**：缺口档删 #8、新增 **#9**（`InitList`
  尾随逗号静默丢弃——同轮探针顺带发现、独立缺陷未修）与 **#10**（引擎潜伏残洞：flat / Fill 下注释仍
  可落行中，现有布局未用 `fill`/`line_suffix` ⇒ 未触发）；`renderer/renderer_architecture.md` 同步
  Union 规则与残洞注。

- **A2 ②：`tpc check` 语法阶段接 linter 语法诊断（原始源宏定义形式语法面）**（2026-10-18，循环 #22）：此前
  `tpc lint` 对畸形 `#define`（宏名缺失 / 形参表空项·未闭合 / 宏体 `#`·`##` 误用）报 blocking 诊断 rc=1，
  `tpc check` 却「No issues found」rc=0——check 的语法阶段 lint 的是**展开后**文本，而 `#define` 定义行在扫
  指令时已被消费。修法：`FilePipeline` 语法阶段在**原始源**上补跑 `linter/macro_syntax.py`
  （`analyzer/structure.py::raw_source_macro_diags`，与 `tpc lint` 同一函数）；宏形式错为 blocking ⇒ 早退
  （不解析、不跑展开文本 lint，避免次生噪声）。**行为变化（C 输入、`tpc check`）**：四类形式错由 rc=0 静默 →
  `[syntax]` 诊断 + rc=1，code/行/列与 `tpc lint` **逐项一致**；宏定义合法 + 代码有错的混合文件仍照常走展开
  文本 lint。**同批受控化**（未闭合形参表的 `ConfigError` 冒泡）：`preprocessor.scan_diagnostics` 转
  `directive` 诊断（两 CLI 路径同一 `[preprocessor]` 报文 rc=1，不再 traceback）、`LinterScanner.scan` 转
  blocking `preprocessor-error`（直接 API 不发异常）、管线 `_stage_macro_scan` 转受控 `error`
  （`tpc format`/`tpc expand` rc=1）。**verilog 零变化**（未声明 `[macro_syntax]` ⇒ 空；A/B 0/144）。
  验证：`test_c_macro_syntax_check_path.py` 9 条 + 受控错误 3 条；门禁变异 87→88；全量/精度/A-B 见下。

- **A2 两路径统一：预处理硬错误在 `tpc lint` / `tpc check` 下同类诊断、都不抛异常**（2026-10-17）：
  此前 `tpc lint` 直连 `LinterScanner`（**不过预处理**）、`tpc check` 走 `ProjectChecker`，同一 C 输入
  （缺头文件 / 循环 / 深度超限）两条 CLI 路径表现不同（check 静默 rc=0）。新增共用入口
  `preprocessor.scan_diagnostics(...)`（返回 `[{kind, message}]`，**不抛异常**）+ `main._preprocessor_gate`：
  两条命令在各自原有输出前打印 `[preprocessor] ...` 并 **rc=1**；**verilog 不受影响**（默认 warn ⇒
  返回空、打印原样，A/B 0/144）。验证：`tests/engine/preprocessor/test_scan_diagnostics.py` 3 条；CLI
  实测 lint/check 同报文同 rc=1、合法 include 仍 rc=0。**边界**：`tpc lint` 的语法扫描仍吃**未展开源码**
  （完整统一留后续），本次只统一"预处理硬错误"面。

- **阶段 4 A2 ①：`expand_macros` 默认口径统一为"开"**（2026-10-17，循环 #16 续）：此前 **CLI 默认 True**
  （`main.py:132` 按 `[commands]` 的 `preprocess`）而**库默认 False**（`pipeline/__init__.py` 兜底 +
  `config/tpc_config.json`）⇒ 同一输入两条路径 verdict 不同（gap ⑬）。**行为变化清单**：
  1. `run_pipeline_on_source(expand_macros=None)`（库默认）**False → True**；`config/tpc_config.json` 的
     `pipeline.expand_macros` 同步 **true**。**CLI 行为不变**（本已 True）。
  2. 含宏/指令的输入在**库默认路径**现在走预处理：宏调用被展开并渲染还原；`#define`/`#include` 行被消费
     （不再 `parse truncated`）。实测：`#define FOO 1` + `int x = FOO;` 由 `error='parse truncated'` →
     `success=True, error=''` 且输出含展开值；config 指向 C 时 `tpc check` rc=0「No issues found」。
  3. verilog：CLI A/B `--expect-changed 0` **0/144 ✓**；五套回归（preprocessor / pipeline / languages-c /
     languages-verilog / policy）**1976 passed**（改前改后同数 ⇒ 无既有测试依赖旧默认；显式传 `False` 的
     用例仍测"不展开"路径）。
  4. 退出判据 1 的实质障碍减少一项（仍差 `#include` 真实实现 / 两路径统一 / `#define` 诊断面 ⇒ A2 其余项）。
  ⚠ **工具缺口（本轮实测，未作证据）**：`ab_pipeline_compare.py --mode inproc` 在 verilog 上不可用——
  `--plugins` 默认 `grammar/c/plugins` ⇒ `GrammarError: 注入目标规则 PostfixExpr 不存在（EXT AlignofExpr）`；
  改指 `grammar/verilog/plugins` 后 JSON 采样报 `JSONDecodeError`。已记入 `TODO.md` 工具项。

- **阶段 4 A1 宏核心返工收口：审计 15 反例 → 3 偏差（= 2 条已声明边界）**（2026-10-17，循环 #16；
  `task-53`）：
  - **已修**（均以端到端用例锁住）：`#`/`##` 两侧空格；调用点实参切分改 **token 级**（字面量/注释内
    逗号与括号不再当分隔/收束符，删文本级 `MacroCallArgs.split` 的调用点）；裸调用**长名优先**；
    函数宏无 `(` 不展开（不回退对象宏）；`#undef` 清形参表；**去掉宏体预展开**（替换文本一律由
    hideset 现算）；跨行块注释**整段掩码**（P1-3）；`#__VA_ARGS__` **实参原文切片**（P1-1：
    `V(a ,  b)` → `"a , b"`，GCC 16.1 对拍）。
  - **两条已声明边界**（以守卫断言锁当前输出、不用 xfail，见 `preprocessor/README.md`「已知边界」）：
    ① 替换结果里再现的调用不重扫（`#define g f`+`g(2)`；`f(2)(9)`）——**案 (A)**（整行 token 展开 +
    回调保位置映射）在**实现前**判定撞 verilog 后缀链（`_extend_macro_chain`/`suffix_after_call` 在
    替换前扩调用区间，ADR-0017）⇒ 裁定 **(B)**：单趟保留，token 级重扫归 A2「两路径统一」，以
    **verilog A/B 0/144 + 后缀链**为独立检查点；② **实参跨行的调用不展开**（替换区间跨行会改输出
    行数/行映射 = 冻结契约面，A1 不动）。
  - **判据面重建**：`tests/engine/preprocessor/test_c_macro_end_to_end.py`（18 条，**生产同路**
    `scan_directives`→`expand_tokens`；来源 = 独立审计 14 反例 + 1 条真实语料）；门禁变异 **65 → 69**
    （4 条**端到端**：原文切片 / 整段掩码 / 掩码关闭 / 长名优先，逐条 `--only` 实测变红）。教训：
    上一轮 8 条 A1 变异**全打在内部函数**上，端到端 10 项错而门禁全绿 ⇒ 变异/用例必须打端到端。
  - **验证**（Lead 独立复跑）：审计脚本 **3 偏差**（= 两条边界）；`tests/engine/preprocessor`
    **186 passed**；受影响面（preprocessor+pipeline+languages-c+policy）**1561 passed**；
    A/B **0/144**；pyright strict **0**。**A1 分级 = `partial`**——原因 = 3 条**已声明边界**（非缺验证）。

- **长期/触发式项移出待办：策略入决策**（2026-10-17，作者定调"长期规划落入的也不算待办了，是一种策略，
  应该进决策"）：新建 `docs/decisions/0021-long-term-deferral-strategy.md`（**策略型 ADR**）——**9 个决策点**
  的「结论 / 为什么现在不做 / 触发条件 / 链」表：档位 `enabled` 语义**暂缓**（作者定调慢慢补）、
  `[macro_policy] when` 上提**暂缓**（要第二语言包同形）、S2 链接性**不采**（无真阳样本 / 4-19 误报 /
  UB 非约束）、符号基座两处错位**另立**（改 P1 公开产物 = 契约面，待作者拍板）、阶段 3 S3 **暂缓**（需类型
  模型）、CSC001/CSC B 档**暂缓**（需原文句或大语料）、语法缺口（逐声明符位宽 / 参数位 `register` /
  ENUM003 C23 豁免 / 复合字面量 raw 候选）**触发式**、L1 渗透剩余面**暂缓**、循环纪律机械化**暂缓**；
  并一并确立**证据档位策略**（A 原文句⇒默认开 / B 权威转述⇒opt-in / C 反证⇒不做；B 升档需原文句或更大
  语料零误报）。`TODO.md` 删「五、搁置」区（12 项）改为**策略层指针**：**117 → 82 行**；`docs/README.md`
  放置速查新增「长期暂缓项/触发条件 → 策略型 ADR，不进 TODO」。取回机制 = 触发出现时按体量立 TODO/ROADMAP
  项并删 ADR 对应行，表空即删该 ADR。门禁：`tests/policy` **404 passed**（ADR 行数/份数由
  `test_planning_doc_budget` 守）。

- **规划档容量清理：删已完成项 + 校陈数**（2026-10-17，作者点名"先缓解待做列表容量再推进"）：
  `ROADMAP` **319 → 294 行**、`TODO` **159 → 149 行**，全部为**删已完成 / 去重 / 校数字**，无内容新增：
  ① 「C 语义层切片 1b / 语义基座」整节 **26 → 5 行**——P1/P2a/P2b-1/P3b-M1 标 ✅ 未删，且 P2b-2/P3/P4 已于
  循环 #7/#9 交付（`PROGRESS` 块 3–6 全 ✅）⇒ 按"完成即删"收成交付索引 + gap 档指针；
  ② 阶段 4 的「A1 ✅ 已交付」**与事实相反**（返工中）⇒ 改写为返工中 + A2 清单压缩（-2 行）；
  ③ `TODO`「阶段 3 剩余片 S2/S3/S4/S5」——**S4 标签已交付循环 #12**（`checks/labels` + `test_c_label_checks.py`）、
  **S2 已有独立"不采"条目**（同一项在两处）⇒ 收成 S3/S5（-3 行）；
  ④ 陈数修正：门禁变异 **38 → 65**（`--list` 实测）、结构欠账 **S 287/16 项 → 1137/50 项**
  （`structural_score --compare` 实测）、基座档 **199 → 200 行（已满）**；
  ⑤ 新事实登记（非本轮引入）：`feature_sites compare` 实测 **3 处散点新增**（`check` 8→12、`config` 29→30、
  `config:lexer.pre_scan` 2→3）⇒ 进 `TODO` 待登记或合并；
  ⑥ 死链清理 3 处（`TODO` 2 + `policy/structural_budget.md` 1；README 侧 5 处留给 A2 文档批次，避免与并行
  写入撞车），`policy/structural_budget.md` 不再自违"不许写见某草稿"。
  验证：`tests/policy` **392 passed**（含 `test_planning_doc_budget`）；`git status` 仅 3 个文档文件。

- **阶段 4 首片 B：`#if` / `#elif` 整型常量表达式求值（声明驱动）**（2026-10-17，循环 #20）：
  `#if` 家族此前只有 `ifdef`/`elsif` 的**宏名**语义；本片按 C99 §6.10.1 实现表达式求值：
  `defined` 两种写法（操作数**不**宏展开）→ 宏展开其余 → 剩余标识符换 0 → 整型常量表达式
  求值（intmax/uintmax 64 位模型、`&&`/`||`/`?:` 短路、有符号溢出/除零/非法常量诊断）。
  `[condition]` 声明面（`grammar/c/base/_macro.toml`）：算子「符号 → 引擎动作」+ 优先级/结合性、
  整型常量形态/后缀、字符常量转义与符号扩展模型、`defined` 拼写——**引擎不含 C 知识**；
  语言包未声明 ⇒ 不接线（verilog 零变化）。`[directive_handlers]` 显式声明 `if`/`elif` 绑定
  `cond_if`/`cond_elif`（按 rules_dir 解析；verilog 不声明 ⇒ `#if` 不是指令）。
  - **条件块机制复用 `ifdef`**：跳过组 / 已选中分支的 `#elif` **不求值**（C99；gcc 实测静默）；
    配对错误（未闭合、多余/重复 `#else`、`#elif` 在 `#else` 之后、`#ifdef` 缺宏名）给
    `condition-balance` 诊断，表达式错误给 `condition` 诊断（带 `Lx:Cy`）；管线转受控
    `error`（非异常），`tpc lint` / `tpc check` 经 `scan_diagnostics` 同报文、同 rc=1。
  - **对拍口径**（本机 gcc 16.1.0 `-std=c99 -pedantic-errors`）：值型常量分类（`0xFFFFFFFF`
    按有符号、`0xFFFFFFFFFFFFFFFF` 无符号）、十进制超 intmax 报错、`'\377' == -1`（signed char
    符号扩展）、多字符 `'ab' == 0x6162`、`L'ab' == 98`、负移位计数反向（UB 面按 oracle）、
    `1<<63` 溢出、短路只抑制算术诊断。
  - **验证**：`tests/engine/preprocessor/test_c_conditionals.py` **96 条**（真 39 / 假 9 / 错误面 19 /
    惰性+跳过组+配对+声明面+端到端等 29）；
    预处理器 **294 passed**、linter/pipeline **730 passed**、A/B verilog **0/144**、pyright **0**；
    门禁变异 **77 → 82**（真值判据 / 跳过组不求值 / 已选中 elif 不求值 / 未闭合不报 / 宏表活值）。
  - **已声明边界**（见 `preprocessor/README.md`「已知边界」）：C23 项不实现（c23 的
    `true`/`false` 1/0、`u8` 字符常量、二进制常量、`#elifdef`/`#elifndef`）；跳过组的**词法**
    错误不诊断（gcc 会）；`#else`/`#endif`/`#ifdef` 后多余 token 不诊断；除零按硬错误停
    （gcc 取左操作数继续、仍出文本）。

- **A2 ④：宏定义的**形式化语法**检查落到 linter（AST 前）**（2026-10-17；作者对齐：形式化语法走 linter、
  语义级走 check 插件族）：新增 `linter/macro_syntax.py`（语言无关，知识全来自声明面）——只报 GCC 同样
  报 error 的**形式化**约束：宏名缺失/非法、形参表空项/非标识符/`...` 非末位或重复/重名、宏体 `#` 后非
  形参或变参、`##` 在首/尾；每类给**带位置**的 blocking 诊断。启用由语言包声明 **`[macro_syntax]` 段**
  （定义侧形式语法，如 `variadic_marker`；经 `preprocessor.macro_config` 读取；**仅 C 包声明**，verilog
  未声明 ⇒ 不跑，A/B 0/144）。
  - **配置面更正（作者提示"linter 补了宏语法检查文件，那么需要对应的宏语法配置"）**：启用不再是
    `[directive_handlers].define.check_syntax` 布尔开关（那样 C 的定义语法仍硬编码在引擎、别的语言无法声明
    自己的宏语法）。改为 `[macro_syntax]` **声明段**：启用判据 = 语言包声明该段；定义侧形态（变参占位）
    也来自声明，形参表/算子形态沿用 `[macro_recognition]` ⇒ **宏语法检查面引擎零 C 常量**；verilog 补自己的段即可启用
    （触发式项，ADR-0021）。**已知重复**：展开核心（`macro_expand`/`_expand`）仍以字面量 `"..."` 识别变参
    标记——今日只有 C 用变参、改后无法用行为判据区分（要第二门不同占位写法的语言包），按"先证后开"登记
    ADR-0021（行 11）。
  - 要点：指令行已被扫指令消费、不进 lint 流 ⇒ 检查对**原始源码**做；形参/算子形态全取
    `call_args` / `[macro_recognition]` 声明，引擎不硬编码 C。
  - **验证**：`tests/engine/linter/test_macro_syntax_checks.py` **21 条**（10 非法形态带位置 + 7 合法零误报 +
    声明驱动 2 条 + verilog 不启用 + scanner 集成）；`tpc lint` 对 `#define F(a,) a` → `Ln 1:13 形参表含空项`
    **rc=1**；linter **283 passed**、精度门禁 **hit_code 33/33 / fp 0**、A/B **0/144**、pyright **0**。
  - **剩余（已落 TODO）**：宏**语义**检查（实参个数等，需宏表 + 调用点）→ 作者定的**插件侧 check 族**；
    `tpc check` 尚未接 linter 语法诊断（同一 malformed define：lint rc=1 / check rc=0）。

- **阶段 4 A2 ②：`#include` 真实实现 + 渲染剪枝**（2026-10-17，循环 #17）：核心发现 = 内容**本来就在流里**
  （`include.py` 的 `_inject_lines.extend`），真缺口是"缺文件只 `print` / 无深度上限 / 渲染面会**内联**头文件内容"。
  - **诊断策略声明面**（引擎只执行策略，语言知识在语言包）：`[directive_handlers.include] on_missing =
    "warn"|"error"`（默认 warn）、`max_depth`（默认不限）。**verilog 不声明 ⇒ 打印原样、A/B 0/144**；
    **C 包声明 `on_missing="error"` + `max_depth=32`** ⇒ 缺文件/循环/深度超限记结构化
    `result["preprocessor_errors"]`（`kind=missing|cycle|depth`）+ 硬错误时 `result["error"]` 受控非空
    （**不抛异常**）。嵌套 include 的子诊断并入宿主；`silent` 语义保留。
  - **渲染前剪枝**（`_prune_include_regions`）：分析面（lint/analyze/transform）照常消费被包含内容；
    **analyze/transform 之后、render 之前**摘掉完整落在 include 内容区间内的 AST 节点 ⇒ 渲染/格式化
    只出 `#include` 原行、**不内联**头文件内容、两遍幂等。区间无法被完整顶层节点覆盖（如 `#include` 在
    函数体内）⇒ **退化整文件原文输出**（`_verbatim_text` 挂根，幂等、绝不内联）。
  - **顺带修**：`_stage_expand` 原先"宏表为空就不展开"⇒ 不含任何宏的 include 内容拿不到区间（会内联）；
    改为"有 include 内容也算"，`parse_raw` 分支保持不展开宏但仍算区间。
  - **验证**：新增 `tests/engine/preprocessor/test_c_include_e2e.py` **10 条**（`""` 相对本目录 / `<>` 只走
    `-I` / `relative_first` 优先级 / 嵌套两层 / 头文件 `#define` 生效 / 缺文件 / 循环 / 深度 / 渲染不内联 +
    幂等 / 函数体内退化）；`c_acceptance` **42/0**、A/B verilog CLI **0/144**、受影响面（preprocessor +
    pipeline + languages-c + languages-verilog）全绿、pyright **0**。
  - **边界**：**CLI 用户可见**尚未接（`tpc lint` 直连 scanner 不过预处理、`tpc check` 未读
    `preprocessor_errors`）⇒ 归 A2「两路径统一」；include 内容行排在 marker 前的顺序偏差未改（已 TODO）。

- **⚠ 更正：A1 交付结论撤回（2026-10-17 同日，独立对抗审计）**：下条"A1 已交付"的判据面**不成立**——独立审计对 A1
  判 **`failed`**，实测 **15 条合法 C99 反例**（GCC 16.1.0 对照），其中 **10 条 P0**：`#`/`##` **两侧有空格即失效**
  （`#define C(a,b) a ## b` + `C(x,y)` → `x  y`；`#define S(s) # s` + `S(hi)` → `# hi`）；调用点实参切分
  **不认字面量**（`F("x,y",3)` → `"x+y"`；`F(")",1)` 提前收束调用）；裸调用正则**短名吃长名前缀**
  （`#define A 1` / `#define AB 2` + `AB` → 不展开）；函数宏**无 `(` 时被当对象宏替换且替换后不重扫**
  （`F (2)` → `x+1 (2)`；`g(2)` → `f(2)`）。另有 4 项 P1（`#__VA_ARGS__` 未实现、`#undef` 不清形参表、
  **跨行块注释**掩码泄漏、字符串化实参内注释未折叠）与 4 项 P2（畸形 `#define` 静默、实参个数不校验等）。
  **根因 = 双路径**：端到端走"扫描期预展开宏体 + 正则插入"，而 `macro_expand.expand_text`（token/hideset
  重扫）是另一条；调用点实参解析同样有 token 级 `_collect_args` vs 文本级 `MacroCallArgs.split` 两套。
  **判据失效复盘（重要）**：本轮新增的 8 条门禁变异**全部打在内部函数**上，与端到端脱节；Lead 的 GCC 对拍
  只覆盖**无空格形态** ⇒ 两者全绿而端到端 10 项错。修复 = `task-53`（**先给"消除双路径"方案再实现**）；
  A1 状态改为**返工中**，`PROGRESS` 块 8 与 gap 档 ⑯ 已同步更正；退出判据不受影响（本就未达成）。

- **阶段 4 首片 A1：C 宏核心交付**（2026-10-17，循环 #15）：`#define`（对象/函数/变参宏）+ `#undef` +
  **C 裸标识符调用**（语言包 `call_shape="name"` **显式声明无前缀**，三态；verilog 语义不变）+
  `#` 字符串化（token 间空白折叠、字面量内部不动）+ `##` 粘贴（**未展开拼写**；试金石
  `CAT(EMPTY,x)`→`EMPTYx`）+ `__VA_ARGS__`（空时保留宏体逗号 `F(1)`→`f(1, )`）+ **hideset 重扫描**
  （替换原"宏体不动点文本替换"，删 `_expand_round`/`stalled`/体积截断）+ **掩码**（字符串/字符/
  行注释/块注释，**含替换进流的宏体**）+ 形参表未闭合 **fail-fast**。新增声明面：`call_shape`（三态）/
  `stringize_operator` / `paste_operator` / `variadic_name`；字符串定界符与转义**取自 token 表
  `[string]`**（单一来源），裸调用整词边界由 `core.token_protocol.IDENT_RE` 派生。
  **验证**：Lead 自建 GCC 16.1.0 对拍探针 8/8（`_drafts/lead_probe_e2e.py` 等）；`tests/engine/preprocessor`
  **168 passed**；六套回归（preprocessor/lexer/parser/languages-c/languages-verilog/policy）**2257 passed**；
  A/B `--expect-changed 0` **0/144**；e2e 宏面 **62**；pyright strict **0**；真实 C 语料空宏表下逐字节恒等 8/8。
  **门禁变异 57 → 65**（新增 8 条 A1 变异：hideset / 调用前缀 / `call_shape` 单元素 / `##` 未展开拼写 /
  `#` 空白折叠 / 变参绑定 / 调用点掩码 / 形参未闭合 fail-fast），逐条 `--only` 实测**全部如期变红**。
  **Lead 独立审计发现**：① **真 bug**——宏体再 tokenize 时未算掩码 ⇒ `#define B "A"` 被误展开成 `"1"`
  （GCC 为 `"A"`），已修（`_tokenize_masked` + `syntax` 贯穿 `_expand_one`/`_substitute`）；② 两条
  **测试空档**（hideset 只断言文本、预算截断恰好截回同值；宏体掩码路径未被覆盖）已补判别式用例；
  ③ 一条**等价变异**（token 级 `masked` 守卫在"掩码区间=单个不透明 token"后为空转）不可检出，
  已从门禁表删除。**边界**：`#include` 真实实现 / `#if` 家族 / C23 项留 **A2** ⇒ 退出判据 1 仍
  **"数字已达、实质未达"**。

- **循环模式本体优化（2026-10-17）**：`policy/collaboration.md` 六步与「循环执行细则」按**失效模式族**
  重组（判据 / 证据 / 归属 / 联动），并补五条**来自实测失效**的规则：判据族新增**「靠什么绿的」**
  （放宽接受条件会掩盖"未实现"）与**「有区分力 + 留产物」**（改前红改后绿要留 `PRE/POST` 产物；改前
  已绿的按回归守卫写明不变式；无可变色判据给该文件的门禁产物）；步 3 新增**调研预算 + 预声明止损点**
  （含落点锚）；证据族要求**审计反例入库可复跑**（不得只留 `_drafts/`）；联动族新增**机械触发清单**，
  豁免与「决策权归属」① 对齐（同族声明键按细节级自决）。步 2 改为**只复述本轮相关约束**。
  同步：`AGENTS.md` 纠偏（`全量框架测试` → `按影响范围测试`，与作者 2026-10-11 裁定一致；全量测试补
  口径限定）、`policy/README.md` 补制度描述、`docs/gaps/README.md` 档案模板补「不做 / 未做」槽
  （否则"反判据落档"无处落）。
  **验证**：`check_doc_refs` D1–D4 = 0；`pytest tests/policy` **368 passed**；7 个章节标题与改前同集合
  （跨文件锚点未破），**4 个未改章节逐字相同**（决策权归属 / 克制推送 / TODO 纪律 / 指令文件纪律，
  `-ceq` 对照）。
  **独立审计** task-52 构造 5 条反例（`_drafts/cycle-audit-52.md`），4 条已并入本轮、1 条（`policy/**`
  容量门禁）经实测修正后登记 TODO——审计建议的 `policy/*.md ≤ 90` 通配实测会红 5 个文件
  （223/181/153/115/100），须逐文件定值。行数 134 → **162**（+28：细则补 5 条规则 + 分族为主因，
  见贤思齐 / 实施节奏 各合并一条共 −2；**示例不移入 `.agents/skills/`**——该目录 gitignored，移过去
  等于证据随 clone 丢失）。⚠ 该文件**仍无容量门禁**，压缩账留给作者压缩轮：审计估可压至 ~120–125
  （每族压成"标签 + 规则"、示例降为单行引用）。

- **阶段 4 契约面裁定（2026-10-17）**：ⓑ **C 裸标识符宏调用 = 语言包显式声明「无前缀」**（**不是**引擎默认
  允许空前缀——否则 verilog 侧"任何标识符都成宏调用候选"，引入**全域误匹配面**）；守"**不留双路径**"
  （有无前缀走同一匹配路径）。同轮另定：**`__STDC_VERSION__` 值的声明位置与 `#if` 整型求值语义都放语言包
  声明面**（两者都是 C 特有语言知识，引擎不持有），**具体声明键形态随首片 B 设计定**。已写入
  `docs/gaps/gap-c-preprocessor-scope.md` 的「裁定」节（原"待作者确认"项归位，**该档现无待决项**）。

- **符号基座两处错位的「零契约面」处置：C 包「声明位置派生视图」**（2026-10-17，承 task-45/46）：
  task-45（S2 链接性方案）在评估时实测出**两处符号基座错位**，影响**任何"文件域 / 作用域"语义检查**：
  ① `void f(int x);` 的**原型形参落 `<global>`**（`decl_node=ParamDecl`）——与文件域对象声明**完全同形**；
  ② `void f(void){}` 的**函数定义符号落自己的作用域**（`scope_kind=function`）——与它的 `<global>` 声明
  **scope 不同**，且使 `void f(void); static void f(void){}` 这类真 UB **漏报**、"定义后 `extern`"继承链断。
  **根因**：`is_file` **不是存储字段**（P1 产物 7 字段与 `Symbol.attrs` 都没有）⇒ 消费者各自用
  `scope.parent is None` 推导，而 C 包**无任何文件域谓词**。
  - **处置（N1+N2，零契约面风险）**：`grammar/c/plugins/semantics/_api.py` 新增 **`decl_position(node, scope)`**
    （**单一判定点**：FuncDef 位取**父作用域**、ParamDecl 位标 `"param"`、其余沿用原 scope）+
    **`declaration_view(analyzer)`**（10 字段：`name/kind/decl_scope/is_file_decl/is_param/scope/scope_kind/
    decl_line/decl_order/phase`）；`_declare` 把三元组 `setdefault` 进 **attrs**（先例 = `phase`）。
  - **不改 P1 公开产物**：F1/F2（真改 `scope`/`scope_kind`）**命中升级判据 ①** ⇒ **另立**走作者流程。
    **硬证据**：`probe_n1n2_view.py --compare` ⇒ **源 11 个 / 逐字节相同 11 / 不同 0，记录总数 76**
    （同时比对 analyze 与 two_phase 两路）+ 测试冻结"产物记录恰好 7 字段"与快照 +
    `test_c_symbol_collection.py` **diff 0 行**。
  - **纪律**：**派生视图是"声明位置"唯一入口**（防"两套真相"漂移）；原 `scope` 语义不变（仍是分析作用域）。
    README 新增小节登记这两处**当前仍成立**的偏差（基座档 `gap-c-semantic-base.md` 已 **199/200 满** ⇒
    暂登记 README + `TODO.md`，**待该档裁剪时并入**）。
  - **实测**：视图语义正断言（`proto`/`defn`/`stat_def` ⇒ 文件域、`is_file_decl=True`；`px`/`arg` ⇒
    `"param"`/`is_param=True`/非文件域；`local` ⇒ 块）；**缺陷态变红 2 条**（去"FuncDef 归父" ⇒ 3 failed
    含 S2 场景漏报；去形参排除 ⇒ 3 failed 含误报）；`tests/languages/c` **834 passed**、
    `tests/engine/analyzer` **387**、`tests/policy` **362**；pyright strict **0**。
  - **门禁有效性 55 → 57 条**（两条守护：FuncDef 归父、形参排除）。

- **阶段 4 范围基线落档：`docs/gaps/gap-c-preprocessor-scope.md`（新建，93 行）**（2026-10-17）：
  按作者裁定（**只做 C 标准中的宏**、编译器专属扩展不做；预处理**只做文本级**；**先满足 C**）把调研落成
  正式档，并登记 `docs/gaps/README.md` 索引（D4 无孤儿）。
  - **范围三表**：指令 / 宏算子与语义 / 预定义宏——每条含名称 + 标准档（C99 原有 / C11 / C23 新增）+
    依据档位（A/B/C）+ 一句话判据。**关键归位**：`__has_include` / `#warning` / `#elifdef` / `#elifndef` /
    `#embed` / `__VA_OPT__` 属 **C23 标准项**（**不是**扩展）；GNU `, ## __VA_ARGS__` 与 C23 `__VA_OPT__`
    **是两件事**（语法糖 vs 标准算子，C23 对应写法 `__VA_OPT__(,)`）；`__STDC_VERSION__` 四档**实测值**
    （`199901L` / `201112L` / `201710L` / `202311L`）。
  - **扩展排除表**：`#pragma once` / `#include_next` / `__COUNTER__` / GNU 命名变参 `args...` /
    GNU `, ## __VA_ARGS__` + 逐条依据（哪档 GCC 报什么）。
  - **方法（可复跑，本轮的复用资产）**：GCC 逐档 `-std=<c99|c11|c17|c23> -pedantic-errors`——**GCC 会
    点名标准版本**，据此机械区分"标准项 vs 编译器扩展"（`__VA_OPT__`/`#warning`/`#embed` 被点名
    "until C23"；`, ##`/`#include_next` 被点名 "GCC extension"）。被测版本 **GCC 16.1.0**；档内含一行
    `python -c` 复跑样例。**局限**：编译器**不表态**的项（`__has_include`/`#elifdef`/`#pragma once`/
    `__COUNTER__`）此法**判不了**，只能靠标准正文 ⇒ 档内统一标"待抽检"。
  - **承载面与 4 处机制级缺口**：现有原语 8 个（`define`/`undef`/`include`/`ifdef`/`ifndef`/`else`/
    `elsif`/`endif`）；`grammar/c/` **无任何宏声明面**（全仓仅 verilog）；缺口 = ① C **裸标识符宏调用**
    （`shape` 要求"前缀 token + 名字位"**两位**、前缀位**不能空**）② `#`/`##` + **重扫描/自引用抑制**
    （现为文本替换 + `max_iterations=128`）③ `#if` 整型常量表达式求值 ④ 预定义宏注入。
    **根因**：`grammar/c/base/_token.toml` 的 `[symbol.base]`（16 项）**无 `#`**（`##` 亦无）⇒ 即
    `tools/c_acceptance.py` 报 `Unexpected token: #` 的原因。
  - **首片 A / B**：**A**（`#define` 对象+函数宏 + `#` + `##` + `__VA_ARGS__` + rescan、`#include`、
    `#undef`、裸标识符调用识别）⇒ **验收现成 = `tools/c_acceptance.py --only-gaps` 两条空洞归零**；
    **B** = `#if` 家族 + `#line`/`#error`。
  - **已定裁定**：C23 档 C 项不进首片（保留清单）；GNU `, ## __VA_ARGS__` 排除但**登记触发条件**；
    `preprocessor/primitives/define.py` 形参表未闭合**改 fail-fast**。**待作者确认**：`__STDC_VERSION__`
    声明位置与 `#if` 整型求值语义（**同一待决点**，涉新增声明键 ⇒ 升级判据 ①）；**另报**：C 裸标识符宏调用
    需扩 `[macro_recognition]` schema（允许空前缀）⇒ 同命中 ①。
  - **诚实边界**：ISO §6.10.x 条款号为**记忆级**、**C23 子条编号未核实**、编译器静默接受项属**引用级**
    ⇒ 档内统一标"待抽检"，**不得当实测结论用**。验收：`tests/policy/test_planning_doc_budget.py` +
    `test_check_doc_refs.py` **25 passed**、`check_doc_refs` **D1–D4 全 0**。

- **阶段 3 续 S4 落地：C 包第三个 check 组件 `checks/labels`（标签与 switch 标签语义）**（循环 #12）：
  形态与前两个组件不同——**走 `[[analyzer.postpasses]]` 遍历 AST**（实测：`[[checks]]` handler 不可行，
  因 label 不进符号表、无 `kind` 可承接；AST 入口是 **`analyzer._ast`**，`AnalysisContext` 并**无** `ast` 字段）。
  - **三条约束均 A 档原文 ⇒ `default=true`**：LAB001（同函数内 label 名唯一，§6.8.1「Label names shall be
    unique within a function.」；第 2..n 处**各一条**）、LAB002（`goto` 目标须在所属函数内，§6.8.6.1；
    **两遍扫描** ⇒ 前向 goto 合法）、**LAB003**（`case`/`default` 只能出现在 switch 内，§6.8.1；按"存在
    外层 `SwitchStmt` 体"判，Duff's device 合法）。severity 统一 `warning`；报告同时写
    `context.extra["c_labels"]`。
  - **硬要求（免误报）**：**只收 `LabelStmt`**——语料 `ring_buffer.c` 同文件里既有 `done:`（LabelStmt）
    又有 `default:`（DefaultLabel）⇒ 混收会立刻误报。
  - **实测**：正样本 11 例（含 Duff 形态）全 0 报；负样本 7 例逐条断码 + 位置（重复 label 三处 ⇒ **2 条**、
    跨函数 goto、case/default 无 switch）；**语料零误报**（`ring_buffer.c` 实测 FuncDef 9 / LabelStmt 1 /
    GotoStmt 1 / CaseLabel 2 / DefaultLabel 1 ⇒ default 与 all **两档 0 条**）；语法宽进不回归
    （`tests/languages/c` **827 passed**）；`tests/engine/analyzer` **387**、`tests/policy` **356**；
    pyright strict **0**；**无需改 `[engine] uses`/`[plugins] enabled`**（`test_engine_capabilities` 9 passed）。
  - **缺陷态变红**：把 `case`/`default` 当普通 label 收 ⇒ **8 failed** + 语料复现 LAB001 误报；
    不做两遍扫描 ⇒ **8 failed** + 语料复现 LAB002 误报。
  - **实现期实测三坑（已落文档）**：① `get_check_rules()` 的**默认目录不是本包目录**（返回空表）⇒
    postpass 必须显式用 `_plugins_dir_of(analyzer)`，否则**判定静默失效**（"看起来 0 报其实是没跑"）；
    ② `plugin_loader._loaded_components` 是**测试级全局态**（逐测试还原）⇒ 测试须逐测试装载；
    ③ `iter_children` 是 **Node 方法**而非 `core.define` 函数。
  - **门禁有效性 53 → 55 条**（两条守护：LAB003 的 switch 判据、LAB001 重复判定）。

- **阶段 4 档位已定 + 「跨语言文本能力原型」评估落档**（2026-10-17；作者指示"档位不要问他、改调研常见 C 工具精度"）：
  - **调研**（`_drafts/p4_preprocessor_survey.md`，8 类工具 × 7 维，证据分实测/引用/推断三级）结论：
    **分界不在宏算法**（各实现都收敛到 Prosser/hideset），而在**搜索路径模型 / C23 新面 / 输出保真策略**；
    三大件（`#include`/`#define`/`#if`）**缺一不可用**；**没有任何工具提供 `-E` 字节保真**（POSIX 只要求
    "表示预处理结果"）。
  - **档位裁定**：**档 2「标准完整」（ISO C11 §6.10 + POSIX `c99 -E`）为基线，另取三件** ——
    `#pragma once`、`__has_include`、**"保留宏引用"输出档**（对齐 `gcc -E -fdirectives-only`，对 tpc
    反向保真价值最高）；**不取** `#include_next`、`__COUNTER__`（顺序敏感全局态与幂等/复跑纪律冲突）、
    C23 新面。已写入 `ROADMAP.md`。
  - **原型设想评估**（`_drafts/preprocessor_prototype_assessment.md`）：作者"在预处理器里实现原型、语言
    接上去"**正是本仓已采纳的原则**（`core/component_protocol.md`「引擎 vs 插件的能力边界」的"占位 +
    简单实现"），**且三类文本能力已原型化**——原型注册面 `primitives/registry.py`（`register(name, kind)`）
    已注册 **替换** `define`/`undef`、**包含** `include`、**条件** `ifdef`；语言包经**声明**接入
    （`[macro_recognition]`、`[directive_handlers.include] path_forms`）。唯一仍在代码侧的"处置判定"
    （`macro_policy`）**今天不上提**：按上提判据实测只有 verilog 一个声明方；"**不用依赖插件**"的准确
    表述是"**加语言不写代码**"（6 项成本 5 项不免除，真收益 2 项）。已落 `preprocessor/README.md`
    「跨语言文本能力原型」节 + `TODO.md` 触发条件项（第二个语言包出现同形判定 ⇒ 以
    `[macro_policy] when` 小表上提，**替代而非并存**）。

- **阶段 3 续 S1-a 落地：C 包第二个 check 组件 `type_semantics`（tag 与枚举常量的同作用域语义）**（循环 #11）：
  新建 `grammar/c/plugins/checks/type_semantics/`，复用循环 #10 的组件形态。
  - **5 条约束（档位决定 default）**：**A 档原文 ⇒ `default=true`** —— TAG001（同一作用域同一 tag 的内容
    至多定义一次，§6.7.2.3「A specific type shall have its content defined at most once.」）、
    TAG002（同 tag 的多次声明须同用 struct/union/enum，同条后半句）、**ENUM003**（`enum E;` 无枚举列表
    只能出现在该类型完整之后，同条）；**脚注档 ⇒ `default=false`（opt-in）** —— ENUM001 / ENUM002
    （同作用域枚举常量互不相同 / 反向，依据是 §6.7.2.2 的**脚注 107**，而**脚注不是规范性内容**）。
  - **硬要求落实（免 24 条误报）**：TAG001 **只在冲突双方都带体**时才报（依据 §6.7.2.3「可见声明存在时
    该类型说明符**不重声明 tag**」）——实测语料 **9 条带体定义 vs 24 条无体引用**，naive"同作用域同 tag
    ≥2 次即报"会**一次误报 24 条**（`ring` 在 `ring_buffer.c` 出现 10 次、9 次是 `struct ring *` 引用）。
  - **输入面**：`grammar/c/02_types.toml:48/:145` 加 `tag_capture`（`kind_path`/`body_path`）⇒
    `plugins/semantics/_api.py:193-238` 的 `collect_named_site` 经 `_named_attrs` 挂 `tag_kind`/`has_body`/
    声明起点。**未改 `decl_node`**（与循环 #10 一致）。
  - **实测**：正样本 13 例全 0 报；负样本逐条断码 + warning + 位置（`_pos_line == 2`）+ **三次带体定义仍只
    报 1 条**；**真实语料零误报**（8 个 C 语料 default/all 两档均 0 条）；**TAG001 硬要求反例**
    `struct ring; struct ring *p; struct ring { int a; };` ⇒ **0 报**（attrs 取证 `has_body=[F,F,T]`）；
    语法宽进不回归（`tests/languages/c` **800 passed**、`tests/engine/analyzer` **387 passed**、
    `tests/policy` **350 passed**）；pyright strict **0**；`test_engine_capabilities` **9 passed** ⇒
    本片**无需**改 `[engine] uses`（与方案预测一致）。
  - **缺陷态变红**：去掉"双方带体" ⇒ **11 failed**（语料复现误报）；去掉作用域限定（改看父作用域）⇒ 2 failed。
  - **不实现（登记）**：**枚举值重复**（§6.7.2.2 的 note 明确允许枚举常量值重复 ⇒ **C 档反证，永不实现**）；
    S2 链接性 / S3 函数原型一致性（需类型模型）/ S4 标签（需 postpass 形态）/ S5；成员重名、不完整类型使用、
    位域宽度、跨 TU。
  - **边界（登记）**：`enum E : int;`（固定底层类型枚举）本包语法尚不支持 ⇒ ENUM003 的 C23 豁免暂不适用，
    将来支持时须加"带底层类型 ⇒ 恒完整"豁免（否则误报）；同作用域"普通标识符占位遮蔽 tag"
    （`int S; struct S { … };`）会**漏报不误报**（闭合需"一 id 多 kind"）。
  - **一处既有断言随新组件调整**：`test_c_storage_class_checks.py::test_rule_defaults` 原断言**全表**相等 ⇒
    被新规则打破，改为按 `CSC` 前缀过滤（该断言本意只覆盖 CSC001–CSC012）。
  - **门禁有效性 51 → 53 条**（两条守护：TAG001 双方带体、同作用域限定）。

- **阶段 3 首片落地：C 包首个 check 组件——存储类说明符语义约束**（循环 #10）：新建
  `grammar/c/plugins/checks/storage_class/`（规则-only 组件 + L2 handler），补上"**语法宽进、语义未判**"
  的存储类约束（此前实测 24 例电池**全部 0 诊断**，即 `typedef static int x;`、裸 `constexpr`、
  文件域 `auto` 等全被静默接受）。
  - **组件与输入面**：`rules/storage.toml`（规则表 + 头注条款引文/档位）+ `rules/_storage_check.py`
    （handler `fn(symbol, rule, context)`，读 attrs + 按声明去重）；输入面走**包侧 capture**
    （`01_declarations.toml` / `03_statements.toml` 的 `capture` 键 + `_api.py::spec_capture` 归一为
    `sc`/`fs`/`is_function`/`has_init`/声明起点）。**未改 `decl_node`**（保持 P1 产物语义）。
  - **条款分档（本轮纪律：无原文句 ⇒ 不得默认开）**：
    **A 档（取得原文 ⇒ `default=true`）** CSC001（至多一个存储类，C99+TC §6.7.1p2；例外对 =
    `_Thread_local` × {`static`,`extern`}，C11 §6.7.1p2）、CSC002（`typedef` 共现，p3）、
    CSC003（`_Thread_local` 不得与 auto/register 共现）；
    **B 档（仅权威转述 ⇒ `default=false` opt-in）** CSC004/007/008/009/010/011/012（7 条）；
    **C 档（有反证 ⇒ 不实现）** CSC005/006（"constexpr 须与 static/extern 共现"——cppreference 的
    constexpr 示例即**裸用**且自述 linkage 随声明 ⇒ 该约束不成立；已同步修正 `plugins/c23/15_constexpr.toml`
    里那条**错误自述**，避免将来按它实现）。
  - **CSC001 禁止朴素计数**（硬要求）：按节点名分类 `sc`/`fs` + **例外表** + **按声明去重** ⇒
    `static inline int f(void){}`（头文件高频**合法**形态）0 报；`static extern int a, b;` 只报 1 条。
    实现期被判据抓到的两个真缺陷已修（允许对写成"两种 thread_local 拼写并集" ⇒ `static _Thread_local`
    误报；`FuncDef` 位 `is_function` 恒 False ⇒ CSC007 漏报）。
  - **实测**：正/负样本 **35 passed**（12 组负样本断码 + warning + 位置；13 组正样本全规则启用下 0 报）；
    **真实语料零误报**（8 个 C 语料在 default 与 all 档均 0 条）；**语法宽进不回归**（`tests/languages/c`
    **768 passed**，负样本仍解析出 AST 且无 error 级）；`tests/engine/analyzer` **387 passed**；
    pyright strict **0**；缺陷态变红（去例外表 4 red、去去重 1 red）。
  - **门禁有效性 49 → 51 条**（两条守护：CSC001 例外表、按声明去重）。
  - **不实现（登记 `TODO.md`）**：跨 TU 链接性、重复 `inline` 定义、`register` 取址、`constexpr`
    常量求值、声明/定义一致性、**参数位 `register` 的语法缺口**（`void f(register int x);` 是合法 C
    却被 lint 拒——属语法面，另立）、成员位（语法层已拒）、**CSC001 函数位覆盖**（一条规则 id 只能绑
    一个 `kind` ⇒ `static extern int f(void);` 的函数位组合未覆盖；闭合需"一 id 多 kind"或组件 postpass，
    属引擎机制变更）。

- **P4 理解路径落地：analyzer「理解」+ transform「改树」两段协作**（循环 #9）：
  `typedef int myint;\nvoid f(void) { x = (myint)y; }` 的 raw 段现在有**确定结构**——
  `RawStatement > ExprStmt > BinaryOp(=) > CastExpr`（类型叶子文本 `myint`），而渲染仍由
  `_verbatim_text` 直出（保真不回归）。
  - **作者定调（本轮纠正了维护者的错判）**：理解路径**必做**——依据 = **C 的测试完备性**要求歧义路径
    有**确定解答**（否则该路径没有确定行为、测试无从固化）；**形态 = 两段协作**（理解 = analyzer 插件 /
    改树 = transform 插件，**两者能力都必须有**）；并澄清 **"架构基本定型"指部件结构稳定**（子系统划分
    与接口边界），**插件形态与插件能力是架构中持续增长的位置**（已写入 `ROADMAP.md`）。
  - **承载段**（`parser/block_parser.py::build_raw_candidate`）：按位点给的替换配方
    （`substitute_type`/`trial_rule`，两处注入点 **+2 键**——internal warning 本就有这两个字段）在
    **原始 token 对象**上试建候选，挂 **`raw_candidate`**（**已还原为源码原文**）+ **`raw_substituted`**
    （取证），**不改 children**（A3 在承载期仍成立）。**fail-closed 等价约束**：试建期开两张台账
    （`_trial_leaf_indices` / `_trial_pratt_sink`），**`missing ⊄ pratt` ⇒ 直接丢弃候选**——实测目标句
    `missing=[12]`（即 `=`）、`pratt=[12]`、叶子 `[11,13,14,15,16,17]`。
    另修两处实现期坑：**试建期递归自噬**（内层解析再命中 raw 钩子 ⇒ `_raw_trial_active` 抑制）、
    **Parser 级簿记不在 `ParseContext` 快照内**（`_comment_anchors`/`_line_comment_anchors`/
    `_trailing_seen`/`_fail_sites`/`_parse_truncated`/`_raw_sites_consumed` ⇒ 就地还原 + `finally` 统一回滚）。
  - **理解段**（`grammar/c/plugins/semantics/_raw_understand.py`，postpass，`requires=["c_symbols"]`）：
    语义二次确认（**不绕过**遍历期 P4 校验）+ 结构选定（白名单 = 包侧常量 `UNDERSTOOD_STRUCTURES`），
    结论挂 `raw_understand`、摘要进 `extra["c_raw_understanding"]`；不一致报 `E003`（**不与 E002 叠加**）；
    候选缺失/无确定结构只记 `not_understood`（用户面不变）。
  - **改树段**（`_raw_transform.py`，`@register_plugin("c.raw_promote")`）：`sub_node = [raw_candidate]`
    + **保留 `_verbatim_text` 与取证属性**；**幂等**（非空即跳过）；`iter_children()` 按 `id` 去重 ⇒
    候选**恰好遍历一次**。
  - **通道 = 节点属性**（analyze 与 transform 共享**同一个 `state.ast` 对象**；`context.extra` 不外传）
    ⇒ **无新能力名、无新引擎入口**（不触发升级判据 ①）。
  - **实测**：判据 1–7 全过——结构确定 / 渲染保真（显著 token 逐项相同 + `format` 幂等 + 对拍
    **0/144**（verilog）与 **0/8**（C））/ 负样本仍拒（遮蔽 `E002`、声明在后、tag；赋值链维持既有宽松）/
    **用户可见面零变化**（4 条 AST 提升只发生在内部）/ 性能 tv80_core `lint` 1.31→**1.24s（−5.3%）**
    且 verilog 语言域实测**不加载**该插件 / 缺陷态各自变红；
    `pytest tests/engine/analyzer tests/languages/c` **1120 passed**、`tests/engine/{parser,linter,pipeline}`
    **634 passed**、`tests/languages/c` **733 passed**；pyright strict **0**。
  - **契约 A3 有意升级**（不变式落 `grammar/c/README.md`）：**渲染权威 = `_verbatim_text`；子树只是分析的
    确定结构，其显著 token 序列须与 verbatim 等价**；renderer/pipeline/analyzer **无需改**（早返回直出、
    宏拼接按标记跳过、校验只看属性且幂等）。
  - **门禁有效性 47 → 49 条**：两段各一条守护（去 transform 提升 / 去 analyzer 结构选定）。
  - **收口修复**：C 包新增 transform handler 后**漏声明 `transform.slots.v1`**（`grammar/c/tpc.toml`），
    被 `tests/policy/test_engine_capabilities.py` 抓到（verilog/c4 早已声明）⇒ 已补，修复后该面 **742 passed**。
  - **已知边界（登记 `TODO.md`）**：① 复合字面量 `(t){1}` 承载期建候选失败 ⇒ 不提升、不报错
    （记 `not_understood: candidate_missing`）；② 赋值链 `x=(t)y+z=1;` 也被提升（成功面不变，
    与该形态的既有宽松一致）。

- **跨形态标记判据上移为引擎通用面**（循环 #8）：`transform/normalizer.py` 会把 `keyword.*` / `symbol.*` /
  `literal.*` 的 token 叶子抽成**字符串属性**（`StorageClass.base = "typedef"`）⇒ 任何"子树里含某
  token **节点**"的判据在**生产口径**下失效（P1 曾因此把 typedef 全收成 `variable`，P4 误拒合法输入）。
  - `core/define.py` 新增公开 `marker_matches(node, marker)`（与 `iter_nodes`/`collect_nodes` 同族；
    前缀取自 `core.token_protocol`，**无语言词法名**）：带 token 前缀的 marker ⇒ 同名节点 **∨** 标量
    属性值 == 去前缀短名（排除 `node_name`/`start`/`end`）；非 token 前缀 ⇒ **只**按节点名；另支持
    钉槽位（`"StorageClass.base=typedef"` / dict）。**通用面不留语言侧副本**：C 包 `_api._subtree_has`
    变薄封装（**+9/−90**，4 个 helper 与 2 个常量删除；marker 取值/kind 等语言知识仍在包侧）。
  - **判据**：引擎侧新增 `tests/engine/core/test_marker_matches.py`（**11 条**：三形态 + 安全反例——
    `node_name` 不参与值扫描、`literal.*` 保引号（`"typedef"` 字面量不命中）、注释不在声明子树内、
    真实 C AST 上 4 组注释/字面量反例零命中）；生产口径 `test_c_symbol_collection_production.py`
    **22 条全绿不改**（3 处改走公开面）。
  - **缺陷态变红**：把 `marker_matches` 退回"只按节点名" ⇒ **8 failed**（引擎侧 2 + 生产口径 6）；
    门禁有效性第 47 条变异**换家**到 `core/define.py`（旧锚随上移失效，已同步）。
  - **范围裁定（修正）**：本轮曾判"P4 理解路径转触发条件式、不做"，**经作者 2026-10-11 纠正为必做**——
    依据 = **C 的测试完备性需求**（歧义路径必须有**确定解答**，否则该路径没有确定行为、测试无从固化）；
    **形态 = 变换插件改树**。同时澄清一条架构认知：**"架构基本定型"指部件结构稳定**（子系统划分与
    接口边界），而**插件形态与插件能力是架构中持续增长的位置**（AST 后插件开放），新增插件形态
    **不属**"架构级重构"——已写入 `ROADMAP.md`「当前主线」。
  - **实测**：`pytest tests/engine tests/languages/c -q -n 4` **2446 passed**；pyright strict **0**；
    端到端探针 **0/13**。

- **P4 安全网 + raw 承载 + M2 窄档摘诊断（原子批次）**（循环 #7）：`typedef int myint;\nvoid f(void) { x = (myint)y; }`
  ⇒ **0 blocking + `success=True` + 输出保真**（此前 2 条 blocking、输出为空），且**不静默掩盖真错**。
  - **三件同批**（依据：两轮实现前对抗证明单独上 raw 会新增掩盖）：① **raw 承载**
    （`parser/block_parser.py` 的 `match_raw_site`/`try_raw_sentence`/`try_raw_at_statement_start`，
    8 条契约字段、**无子节点**、`_verbatim_text` 直出 ⇒ 渲染零改动）；② **M2 窄档摘诊断**
    （`linter/scanner.py::_apply_narrow_downgrade`：`{phase-statement, phase-unrecognized}` ∧
    `eligible` ∧ **诊断起点 ∈ site region**）；③ **P4 analyzer 校验**（`analyzer/raw_contract.py` +
    `analyzer/primitives/_raw_validate.py` + `analyzer/traversal.py:229` **内建回落** ⇒ 规则表查不到也跑，
    否则安全网静默失效；C 包 `_raw_bridge.py` 注册类型名查询，**kind 语义只在包侧**）。
  - **raw 与声明互斥**：新增包声明 `[pre_scan] raw_exclude_rules = ["Declaration", "FuncDef"]` ⇒
    声明句不得 raw（否则其声明不进符号表、遮蔽记录消失 ⇒ P4 会**误接受**非法代码，联合反例已实测）。
  - **顺带修掉一个既有生产缺陷（P1）**：`transform/normalizer.py` 会把 `keyword.*` token 叶子抽成
    **字符串属性**（`StorageClass.base = "typedef"`），而 `_api._subtree_has` 只按节点名判 ⇒
    **生产路径下 typedef 恒被收成 `variable`**（P4 因此误拒合法输入）。已改为**跨两形态判据**
    （带 token 前缀的 marker：同名节点 **∨** 标量属性值 == 去前缀短名；非 token marker 仍只按节点名），
    并补**生产口径判据** `test_c_symbol_collection_production.py`（22 条，含"两形态逐条等价"+ 安全反例）。
  - **`tpc check` 第二消费方接线**：`analyzer/structure.py` 取 `internal_warnings`（在 blocking 早退
    **之前**取走，避免丢位点）+ 注入 `raw_sites`/`raw_source` ⇒ 判据 4 的
    "`parse_ok=False` 却 `exit_code=0/syntax=[]`"自相矛盾消除（目标输入现 `parse_ok:true` 与
    `exit_code:0` 一致；反例仍报 syntax 且非 0）。
  - **实测**：全量 `pytest tests` **3446 passed / 7 skipped**；`eval_lint_accuracy` 33/33 fp 0；
    `eval_diag_baseline` **5548 → 5548**；回归档对拍（verilog）**0/144**；功能档 23 输入 **8 条变化**
    （6 条 `success=True` + 输出保真；**遮蔽例被 P4 拒绝：`E002`** ⇒ 安全网实证）；pyright strict **0**。
  - **缺陷态变红**：去 raw / 去互斥 / 去精确 (line,col) / 去 region 等式 / 去 `tpc check` 接线 /
    `node_name_only`（P1 原形态）/ 值比较去引号 —— 各自变红；**门禁有效性 45 → 47 条**（新增两条守护：
    raw 兜底接入点、`_subtree_has` 跨形态判据）。
  - **已知偏差（本批不做，登记）**：① `x = (t)y + z = 1;`（gcc 判 `lvalue required`）现与 `(int)` 版
    **对齐放行**（引擎既有宽松，非本批引入）；② `void f(int t);` 的原型参数泄漏到文件作用域
    （`t @ <global>` ⇒ "有全局 typedef 时的原型参数"会被 P4 误拒）。
  - **剩余**：P4 的**理解路径**（把 raw 段理解为 `CastExpr` 子树供后续分析消费）未做，已登记 `TODO.md`。

- **P3c 前置切片：位点发现面扩到 production 层语句位（linter 侧，零用户可见变化）**（循环 #6）。
  原计划形态（parser 侧 raw 承载 + `_repeat_loop` 接入点）经**实现前判据对抗**（task-27，只读实测）
  证伪 ⇒ 任务重定义，细节见 `docs/gaps/gap-parser-linter-approximation.md`。
  - **机制**：`linter/discovery.py::_discover_bracket` 语句分支新增 `_scan_container_sites`——
    分类命中"引用式容器"（`_is_nested_container`，配置驱动）且语句以括号开启符起始 ⇒ 括号配对取体
    区间，交给**同一套** `_discover_range(record=False)` 扫描：只记内部 warning，**不注册节点、不报
    未识别诊断**（"建节点"与"跑扫描"用 `record` 关键字解耦）。
  - **实测**：`typedef int myint;\nvoid f(void) { x = (myint)y; }` 位点 `[]` → **1 个
    `eligible=true`（line 2 / col 15）**、`symbol_names=['myint']`（Lead 独立复核一致）；`region`
    仍出自同一份 `_stmt_ends`（全仓无第二份语句结束推导）；扩容为逐语句推进、**无逐 token 重扫**。
  - **零用户可见变化（产物证据）**：`tools/ab_pipeline_compare.py --mode cli --expect-changed 0`
    → **0/144 差异**；`tpc lint --json` 144 文件逐文件 rc+stdout SHA256 与 HEAD 一致；
    `eval_lint_accuracy` 33/33 fp 0；`eval_diag_baseline` **5548 → 5548**；全量 `pytest tests`
    **3381 passed / 7 skipped**（基线 3359 + 22 条新判据）；pyright strict **0**；`c_acceptance`
    仍 40/42。
  - **性能**：tv80_core（4621 行）`tpc lint` 中位 **1098 → 1063 ms（−3.2%）**。
  - **边界诚实**：`TestShadowingBoundary` 原断言"函数体不产生位点"随覆盖扩展失效 ⇒ 改为**冻结新
    事实**（遮蔽例现产生 `eligible=True` 位点）并登记 **M1 在作用域遮蔽上不健全**：raw 承载必须与
    M2+P4 的 `analyze` 精确符号面校验**同批**。

- **agent 协作面（循环 #6）**：新增 `CLAUDE.md`（兼容指针 → `AGENTS.md`——后者由 Linux Foundation
  的 Agentic AI Foundation 托管、60k+ 项目在用，而 K framework 用的是私有的 `CLAUDE.md`）；新增
  `parser/AGENTS.md` / `linter/AGENTS.md`（目录级注意事项，遵循"最近的 AGENTS.md 优先"）；
  `policy/collaboration.md`「循环执行细则」新增**审计要给反例**（只报"已检查"的审计按 `partial` 计）。
  `.agents/skills/task-cycle/SKILL.md`（循环执行包）是**本地能力文件**——`.agents/` 在 `.gitignore`，
  与既有 3 个 skill 一致，不进版本库。

- **`tools/ab_pipeline_compare.py` 修输入种子缺陷**：HEAD 副本缺**未跟踪/生成**输入
  （`tests/e2e/samples/**/gen/*.v` **54 个**）时 PRE 一律 rc=1 ⇒ 报出 54 条**假差异**；现于对拍前把
  缺失输入从工作树补进副本（工具测"同一输入在两个引擎状态下的产物"，**输入必须两边一致**）。
  实证：修复后该档打印 `[pre] 补入 HEAD 副本缺失的输入 54 个`，差异 **0/144**。

- **门禁有效性 44 → 45 条**：新增"括号定界容器体位点发现被摘掉 ⇒ production 层位点消失"变异
  （守护 P3c 新能力）；同步一条既有变异的锚点（`discovery` 块分支调用改为多行后原 `old` 失配 ⇒
  该 payload 曾失效、门禁抽查变红）。

- **`PROGRESS.md`：到 0.1.4 的进度刻度**（作者 2026-10-11 立；根目录单一视图）。分母 = 主线 1
  「C 包框架缺口补齐」的 **9 个主块**（现 **4/9**，工作量加权约 40–45%），加 5 条**可核对退出判据**
  （全过 = 主线 1 完成、可进性能化组件）；只记刻度与判据状态，主线完成即整档删除或改写为下一
  主线刻度；上限 60 行，已纳入 `tests/policy/test_planning_doc_budget.py` 的根文件预算。同时
  登记了对照锚（C 包 48 commits/15 天、Verilog 包 224/45 天、语义基座 5 循环/26 小时）与唯一
  阻塞估算的待定项（阶段 4 档位：全精度 vs 最小可用，需作者拍板）。

- **协作流程：任务循环补两条门 + 4 条执行细则**（作者 2026-10-10 同意；`policy/collaboration.md`）。
  步 3 计划须含**预算**（性能/容量口径 + 超限处置）与**判据**（可执行形态）；**改判定行为 /
  碰契约面 / 影响面未知**的任务，**实现前**由独立方**只对判据**搜反例（计划级证伪；实现后的
  对抗审计照做）。执行细则 4 条：**判据必须可执行**（文档里的"同批判据"不算判据——反例：raw 的
  B 类赋值链只有文字、A 类遮蔽有测试）· **验证只读且全量在冻结树** · **零可见变化要给对拍产物** ·
  **派生项标来源**。动机：P3 走"实现后才审计"⇒ 整类证伪 + 整体回退；M1 走"判据先对抗"⇒ 一轮过；
  M1 初测 `+13.7%` 才发现超阈。细则多为行为约束、可执行面弱 ⇒ 其中「零可见变化」的证据形态
  已立为 `TODO.md` 条目（对拍工具补产物摘要档）。

- **`tools/ab_pipeline_compare.py`：只读 A/B 对拍**（`git archive HEAD` → 临时目录跑 PRE、当前树跑
  POST，逐输入 diff 诊断 / `success` / `error` / `output`，`--expect-changed N` 判"零变化 / 仅预期
  变化"；`finally` 删临时目录、**任何时候不写工作树**）。用途：每轮收尾的"零用户可见变化"证据。
  - **动机（实测教训）**：本轮验证脚本原以"把 HEAD 版本**写回工作树**再恢复"实现，**在共享工作区
    会与并发的全量测试互撞**（worker 里已 import 的模块是新版、未 import 的是 HEAD 版）⇒ 制造出
    **5 条假红**（同文件单跑 17 passed / `tests/engine` 1638 passed / 全量 5 failed）；受控实验在
    `git archive` 副本上复现了该失败族（32 failed/23 passed）。改为只读实现后，全量在 **并行 /
    单进程 / 顺序巡检**三档均 **3359 passed / 7 skipped**。`tools/README.md` 已登记该纪律。

- **P3b-M1：raw 资格判定（三条判据 + 深度守卫，零用户可见变化）**（循环 #5）。为"歧义位点走
  raw"先做**资格判定**基础设施——**只判资格、不接 raw、不摘诊断**（用户诊断面逐字节不变）。
  - **三条判据**：① **替换式试解析**（`_substitution_trial`）——把待判定 `( id )` 的标识符按其
    "类型名形态"替换后**重跑同一候选集**，整句通过（`errs==0 ∧ consumed==limit-i`）才算"该句
    唯一问题是符号歧义"；② **只认 typedef 命名空间**（kind 语义由包声明）；③ **声明位置先后
    （行 + 列）** + **深度守卫**（`decl_depth ≤ use_depth`，文本级计 `{}` 深度）——`order_ok` /
    `depth_ok` 分别记录，`eligible = ①∧②∧order_ok∧depth_ok`。
  - **声明面（语言知识在 TOML）**：`grammar/c/base/_pre_scan.toml` 的 `[pre_scan.decl.typedef]` 加
    `type_name = true` + `trial_as = "keyword.int"`；`type_name=true` 却不给 `trial_as` ⇒
    `load_pre_scan_config` **fail-fast**。新增带行/列/深度的**并行**读取面 `pre_scan_with_lines`
    （`pre_scan()` 的签名与行为不变）。
  - **踩到并修的引擎坑**：packrat memo **以 token 位置为键** ⇒ 改型后旧结果被命中（目标句被误判
    `errs=1`）⇒ 新增 `RuleMatcher.memo_suspended()`（快照/清空/还原），试解析在干净缓存上求值。
  - **独立审计（另派对抗性复审）**：旧 8 条"语句级 raw 吞真错"反例**全部堵住**、951 条输入
    **0 新增误报**、`tpc lint --json` 209 文件 SHA256 与 rc **逐文件相同**、lint accuracy 33/33
    FP 0、真实语料误报基线 5548 无增长。仍有两类落在判据外：**A 作用域**
    （`void f(void) { typedef int t; }\nx = (t)y;`）——**已由深度守卫关掉**（`depth_ok=False`）；
    **B 赋值链**（`x = (t)y + z = 1;`）——引擎**既有**宽松（`(int)` 版在改前也通过），单列给
    M2+P4（见「Changed」）。
  - **性能**（真实语料 tv80_core 4755 行 / 2314 个未收敛位点）：初测 `tpc lint` **+13.7%** 超
    阈值 ⇒ 定位**不是试解析**（verilog 无 trial），而是逐字符偏移映射表 + 按位点重扫前缀深度
    ⇒ 改**段表 + 二分反查**与**前缀深度缓存**后复测 **+0.0%**（`format` −0.1%）；C 压力样本
    （200 个 eligible 位点）+6.8%/+7.6% ⇒ 未超 ~10%，按裁定**不加**试解析次数上限。

- **机制卫生清理：旧回调链的两处残留**（2026-10-11，作者提问起子）。判据 = "删除先证后删"：
  - **`transform_callbacks` 死消费链**：该能力自 **P1.5 step 2** 起**无任何包声明**（`component_protocol.md`
    已注记删除）⇒ `get_capability` 恒 None ⇒ 回调恒空 ⇒ **`trans_callback/` 目录与 `cb_json` 字段
    永远为空**。已删：`pipeline/schedule.py::_dump_analyze_artifacts` 的消费路径（+ 未使用的
    `get_capability` import）、`pipeline/__init__.py` 的 `cb_dir`/`cb_json`（字段 + `_resolve_paths`
    三处引用）、`tests/fuzz/generate.py` 的 `_OUTPUT_SUBDIRS` 条目。
  - **`_capture_hooks` 死扩展点**：`analyzer/primitives/_symbol.py` 自述"**目前未使用，保留扩展点**"，
    全仓**无注册方**、**无 TOML 声明** ⇒ `hook` 恒 None。已删：定义、hooks 循环、`capture_hooks`
    配置读取、`Callable` import、docstring 示例与措辞，以及 `core/global_state.py` 的登记。
  - **验证**：`capture_hooks` / `resolve_invert` / `cb_dir` / `cb_json` **全仓零匹配**；按影响范围
    `pytest tests/engine/analyzer tests/engine/pipeline tests/policy` **880 passed**；pyright strict
    **0**；`check_doc_refs` / `check_hardcode --strict-*` 干净。
- **`core/component_protocol.md` 补「跨阶段组合形式选型」表**：能力面（`[capabilities]` +
  `get_capability[_in]`）/ 产物通道（挂符号 attrs）/ 槽位契约（`[[transform.slots]]`）/ 节点属性通道
  （跨阶段结论长在同一 AST 对象）四者的**判据**（传函数还是数据、要不要绑定节点）+ "⚠ 勿复活旧回调链"
  警示。结论：**四者语义分工不同，不建议统一**；P4 理解路径选的节点属性通道是最省 plumbing 的一种。

- **M2（raw + 窄档摘诊断）推迟到与 P4 原子落地**（循环 #5，Lead 裁定；本轮实现已撤出）。
  理由：独立复审证明 M1 的资格判定在**作用域遮蔽**上不健全（`pre_scan` 无作用域，且块内语句位
  尚不产生位点）⇒ raw 段的合法性必须由 analyzer 用 `phase="analyze"` 的**精确符号面校验**
  （**校验不过 ⇒ 报错，不静默**）。同批判据：审计 **A**（作用域/遮蔽）、**B**（引擎既有赋值链
  宽松，单列）、`tpc check` 对静默输入 `parse_ok=False` 却 `exit_code=0/syntax=[]` 的自相矛盾。
  - **覆盖边界单独立项 P3c**：资格判定目前只覆盖**块体语句位**；C 函数体内（`CompoundStmt` 的
    `@Stmt*` 由 production 展开）不产生位点 ⇒ 接入点已调研
    （`parser/_production.py::_repeat_loop` 的 `result is None` 分支）。
  - 守卫测试改回"**M2 未上线**"（条目无降级字段/常量/方法），M2 落地时必须显式改它。

- **P2b-1：linter 符号相关性标记（零用户可见变化）**（循环 #3）。符号输入走引擎既有
  `[lexer] pre_scan`（`linter/scanner.py::_pre_scan_names` → `set_symbol_hints` →
  `discovery` → `lookahead`），**不 import 包侧插件、不硬编码 kind**；收敛判定条目新增
  `symbol_dependent` / `symbol_names` / `symbol_shape` / `region`。
  - **口径（实测收窄）**：位点句子区间含**括号紧邻**的 `( id )` ∧ `id ∈ pre_scan` 名集合。
    只按"区间含名"会把 verilog 的 `module/function/task` 名算进来（lint_err 语料实测 **2 个
    位点误命中**，会误降级）；收窄后在 lint_err 47 / valid 64 / real 18 文件（2314 个未收敛
    位点）**0 命中**，只在目标形态（C 的 `(myint)x`）命中。
  - **判据**：`typedef int myint;\nx = (myint)y;` ⇒ 条目 `symbol_dependent=True`、
    `symbol_names=['myint']`，而**用户诊断面逐字节不变**（仍 2 条 blocking、管线仍
    `lint failed: 2 error(s)`；90 个 tracked 样本 lint JSON 0 差异、lint accuracy 逐项不变、
    diag baseline 5548 无增长）；`x = (1 + )y;` 与同名非 typedef 均**不标**；缺陷态（去掉
    pre_scan 名判定）**1 failed / 9 passed**。
  - **诊断摘除（P2b-2）刻意推迟到与 P3 同批**（见下「Changed」）；测试内含一条**决定守卫**
    （断言无降级字段/常量/方法），P3 重新引入时必须显式改它。
- **`[pre_scan] fallback = bool`（默认 `true`）**：预扫描的"声明类别之外的关键字兜底收集"
  现在可关。C 包已声明 `fallback = false` —— 引擎原先无条件建 `\b(kw)\s+(\w+)` 兜底，会
  `typedef int myint;` 里把 `int` 也收成 `typedef`（按 `phase` 对比/据名判定的消费方被污染），
  而包侧无法关闭。声明类别的收集不受该键影响；非 bool 即 `ConfigError`（fail-fast）。
  判据：`tests/engine/lexer/test_pre_scan_fallback.py`（4 例，含 C 包符号面干净）+
  `check_gate_efficacy` 新变异（无条件建兜底 ⇒ 必红）。

- **循环 #4：P3（parser 歧义位点 raw）首次落地经独立审计证伪，已整体回退（未发布）**。
  首次实现（语句起点落在"未收敛 ∧ 符号相关"位点 ⇒ **整句** raw + 同批重新引入窄档摘诊断）
  四条硬闸当时全绿（`(myint)y` 0 blocking + `success=True` + 输出保真；`(1 + )y` 仍 blocking；
  `(int)y` 不回归；lint accuracy 33/33、diag baseline 无增长），但**独立对抗性审计**
  （838 条语料 + 55 条定向输入）发现：**语句级 raw 会吞掉同句里与符号歧义无关的真错**。
  - **最小复现**：`typedef int t;\nx = (t)y + ;\n` ⇒ 改动后 `tpc lint` **0 诊断 rc0**、
    `tpc format` rc0 直出**非法 C**（改动前 2 条 blocking）；同类 7 处：`+ (u)z + ;`、跨行 `+`、
    `+ "unterminated;`、缺 `;` 的 `x=(t)y`、`x=((t))y;`。
  - **裁定**：掩盖真错比"报错但不出格式"更坏，且修复需要**新判据**而非小补丁 ⇒ **整体回退**到
    循环 #3 状态（该实现**从未提交**，无兼容负担；代码与测试存档 `_drafts/p3_first_attempt.patch`
    与 `_drafts/p3_test_parser_raw_site.py`）。回退后基线复绿（全量 + 目标子集 + pyright）。
  - **重做判据（P3b，已入 `TODO.md` / `ROADMAP.md`）**：① **替换式试解析**证明"该句唯一问题是
    符号歧义"（把待判定的 `( id )` 按类型名形态试解析，整句通过才允许 raw）；② 只认 **typedef
    命名空间**的名（`struct t{}` 的 tag 名不算）；③ **声明顺序敏感**（`x=(t)y; typedef int t;`
    不得 raw）。审计同时点出跨层缺口：`_pre_scan.toml` 自述"只作提示/对比、判定用 `analyze`"，
    而 P2b-1 的标记已把它升为**行为输入**——三条判据正是补这个缺口。
  - **过程价值**：这是"独立判据 + 全量框架测试"第一次在**提交前**拦下一个会掩盖真错的改动；
    循环 #4 结论 = **partial（实现未采纳，已有重做判据）+ verified（回退后基线复绿）**。
- **P2b 拆片裁决：P2b-2（摘诊断）与 P3（parser raw）同批落地**（循环 #3，Lead 裁决）。
  事实：P2b-2 单独落地后，lint 不再拦但管线换成 `parse truncated` 失败、**输出仍为空**——
  用户诊断面反而更差（原来有明确 lint 报错，现在干净 + 一句含糊的 parse truncated）。
  故本轮只落 **P2b-1 标记**（零用户可见变化），把"摘 blocking"与"raw 暂缓建树"**原子耦合**。
  对照事实已写进 `linter/linter_architecture.md` 供 P3 当判据：`x = (int)y;`（内建类型转换）
  **通过**，`typedef int myint;\nx = (myint)y;` 当前 **parse truncated**。

### Fixed

- **世界 B 列对齐重组丢端口方向 ⇒ 格式化静默改写语义**
  （`grammar/verilog/plugins/formatter/passes/column_align.py::_unit_cols`）。
  多声明行的逐单元对齐（P1.5）按"**共享类型头**"模型工作：非首单元的头 token 一律
  丢弃。但 ANSI 端口表里**每个端口自带方向**（`output awvalid, input awready, …`），
  这些头不是共享头——一丢就把方向**继承改写**了。
  - **实测（PicoRV32 真实核 94.6 KB）**：3 个模块共 **30 处**方向改写——`picorv32_axi` 11 个
    `input→output`、`picorv32_axi_adapter` 8 个 `input→output`、`picorv32_wb` 11 个
    `output→input`；全文件方向关键字 **61/146 → 34/107**。输出
    **语法合法**（Verible 对 `module m(output a, b);` exit 0）⇒ 不报错、静默：仿真/
    综合看到的是**另一个接口**。
  - **定位**：`format_output=False`（只跑世界 A）关键字完好 (12,38)，开 formatter 变
    (2,23) ⇒ 落在世界 B；最小复现 216 字节（单模块 + 含注释的 ANSI 端口表）。
  - **修法**：`_unit_cols` 在"后续单元自带头部"时返回 None ⇒ **整行跳过、保留原文**。
    共享头情形（`reg a, b;`）后续单元本无头 token ⇒ 行为不变。不选"把方向塞进类型列"
    是因为那会让首端口名字列被推开十余格，且列对齐的共享头假设本就不成立。
  - **判据**：整份 picorv32 方向关键字 **(61,146) → (61,146)**、逐模块方向表 **0 改写**、
    幂等成立；`tests/languages/verilog/test_column_align.py` 新增 4 例（跳过 2 + 对照 1
    + 端到端 1）。
  - **回归**：`tests/languages/verilog` 403 passed。
  - **门禁盲区（记档）**：Verilog 往返判据只比注释清单/行覆盖/幂等，**没有"端口方向 /
    显著 token 序列"这一项** ⇒ 这类缺陷可长期静默（本次靠人工核对端口表才发现）。

- **符号回滚三处洞 + 跨 parse 残留**（循环 #3；P3 前置，**行为零变化**）：
  ① `ParseContext` 快照**纳入符号 store**（`bind_symbol_store()` + 快照末位带 `_ScopeStack.snapshot()`，
  既有 6 个快照点自动覆盖）；② `_ScopeStack` 加**撤销日志**，`restore` 截栈后按日志精确还原
  （含**同深度** register；原先 `restore(2)` 后 `lookup('leaked')=='typedef'`）；③ pratt 分支
  补作用域帧配对（抽 `_push_rule_scope()` 共用；**语义路径**帧仍不推 ⇒ 日志/路径输出不变）；
  ④ `Parser.parse()` 每轮重建 store 并绑定 context（跨 parse 复用不再读到 root 残留）。
  - **判据**：新增 `tests/engine/parser/test_symbol_rollback.py`（9 例）；**四处缺陷注入分别
    2 / 5 / 1 / 1 failed**（恢复后 9 passed）；`tests/engine/parser` 212、四语言包 1272、
    `tests/engine` 1596 全绿。
  - **行为零变化**：`tests/e2e/run_all_tests.py` FAIL 0（102 例），与"四处修复全回退"的对照
    **逐用例结论行全同**（仅耗时不同）；`eval_diag_baseline` 5548 → 5548；`run_edge` clean 6 /
    reject 7 / failures 0。
  - **剩余边界（已登记缺口档）**：`sibling_counter` 与簿记集合（trailing/anchor/repeat/fail_sites）
    不在快照内（只影响 `path=`/观测面）；`restore` 仍"只截不补"（回滚到更深快照未支持）。

- **C 语义基座 P1：声明式符号收集产物（作用域 + 声明序 + 分期标注）**（循环 #2 实现项；方向为
  作者 2026-10-10 拍板）。
  - **产物**：`{name, kind, scope, scope_kind, decl_order, decl_line, phase}`，
    `kind ∈ {typedef, tag, variable, function, enumerator}`；读取入口
    `AnalysisTraversal.context` → `_api.product_from(at)`（analyze 期）/
    `_api.two_phase_product(at, src, "grammar/c")`（两期合并，**每条自带 `phase`**）。
  - **声明面分工（语言知识全在 TOML）**：核心包 `[Rule.analyzer.c_symbol_collect]`（收集点 /
    AST 路径 / typedef·函数标记）+ `base/_pre_scan.toml`（`phase="pre_scan"`，**不声明
    `rule_hints`** ⇒ 不重排 parser 候选）+ `plugins/semantics/`（原语注册 + 后置产物 + 纯查询
    `_api.py`）。默认偏置**显式化**：未声明标识符 = `not typedef`（`DEFAULT_TYPEDEF_BIAS`）。
  - **分期语义**：`pre_scan` 只作提示/对比（粗收集、无作用域/顺序），判定只看 `analyze` 期。
  - **判据**：`tests/languages/c/test_c_symbol_collection.py` 9 例（正 / 负 / 声明顺序 /
    出块失效 / 内层遮蔽 / 分期可区分 / kind 覆盖 / 产物写 context / 无新诊断）；
    **6 条缺陷态变红**（3 / 4 / 1 / 1 / 1 / 1 failed，恢复后 9 passed）。
  - **回归**：`tests/languages/c + tests/engine/analyzer` 1042 → **1051 passed**；smoke 462；
    `tools/c_acceptance.py` 40/42；pyright strict 0（新增/改动 4 个 py）。
  - **唯一引擎侧改动**：`analyzer/traversal.py` 公开 `context` 属性（+10 行，无行为变化——
    `check()` 的结果面刻意不收窄）。
  - **遗留（已入 `TODO.md`）**：引擎 `lexer/pre_scan.py` 的兜底正则会带入 `int: typedef` 这类
    **非声明名**（包侧无法关闭；消费方按"pre_scan 只作提示"处理）。

- **P2a：linter「候选是否收敛」判定 + 内部 warning 旁路**（循环 #2；作者"关键在 linter"的
  落地第一步，**用户可见面零变化**）。
  - **判定口径**（`linter/lookahead.py::_try_parse` + `_record_convergence`）：**上下文允许
    候选**里 `errs == 0` 的 ≥2 且最大 `consumed` 并列 ⇒ `ambiguous_full_match`；允许集非空但
    全败 ⇒ `no_full_match`；唯一最优或可区分 ⇒ 收敛。`_decide_best` 的既有择一行为**不改**。
  - **上下文允许集**：`_collect_member_only`（语言无关推导：`is_statement` ∧ 有 caller ∧
    caller 不是 inline 语句分派器）⇒ 排除"容器成员专用语句"（C 的 `StructMember`），
    `myint v;` 不再被伪候选带偏；只作用于判定，**不**改 `classify` 返回值。
  - **旁路载体**：`LookaheadTable`（按次重置）→ `Discovery` → `LinterScanner` → `_stage_lint` →
    `_PipelineContext.internal_warnings`（条目含 `line`/`column`，供 P3 跨阶段定位）；
    **不进**诊断、不进 `--json`、不影响 exit code（先例 `Discovery._unrecognized`）。
  - **零变化三证**：lint accuracy 逐项相同（err 33 / detected 33 / hit 33 / fp 0 / valid 7）；
    真实语料误报基线 5548 → **5548**（无增长）；`tpc lint --json`（144 文件 in-process +
    15 文件真 CLI）stdout/rc **SHA256 逐字节相同**。
  - **判据**：`tests/engine/linter/test_linter_lookahead.py::TestConvergenceJudgment`（7 例）+
    新 `tests/engine/pipeline/test_lint_internal_warnings.py`（3 例）；缺陷态（去掉上下文过滤）
    **7 failed / 23 passed**（恢复后 sha 一致）。回归 linter+pipeline 330 → **340 passed**。

### Fixed

- **yaml 正零小数 `key: 0.5` 静默丢内容**（`grammar/yaml/base/_number.toml`；循环 #1 实现项）。
  - **成因（实测）**：`yaml_dec` 是 `size = { digits = "nonzero" }` ⇒ `number_gen.build_size`
    只建 digit1-9 的首字符转移（`lexer/number_gen.py:192-196`），而**小数/指数链**（`dot`/`eE`）
    挂在 size 子图上 ⇒ `0.5` 进不了该链；`yaml_zero`（`base_prefix="0"` 前缀形态）又没有小数
    延续 ⇒ 切成 `number(0)` + `plain(.5)`，渲染 `key: 0`（`.5` 静默消失）。
  - **修法（镜像既有解，非自创）**：`yaml_dec` 改 `size = { digits = "any" }`——C 包同族先例
    `grammar/c/base/_number.toml` 的 `c_dec` 就是这么解的（其注释记着完全相同的症状）；同时按
    "先证后删"删除 `yaml_zero`（语言 ⊆ `yaml_dec(any)` 且声明其后、等长取先 ⇒ 从不产出 token；
    机器对照 24 条语料 **变化 0 条**）。**纯包侧，零引擎改动**。
  - **判据**：`key: 0.5` / `0.25` / `0.5e3` / `0.5E-3` → 单 `literal.number`、渲染逐字、token
    逐项相同、幂等；`0` / `017` / `00` / `1.5` / `5` / `-0.5` / `-5` / `seq:\n- 8080` /
    `seq:\n- -5` 全不回归。`tests/languages/yaml` **91 → 110 passed**；
    `tests/engine/lexer + parser` 434 不变（未动引擎）；smoke 462。
  - **跨包机器对照**（HEAD 包副本 vs 工作树，逐条 token 流）：verilog **0/8**、c **0/9**
    （`017` 八进制、`.5` 前导点逐字不变）、c4 **0/7** ⇒ 非 yaml 合计 **0 差异**；yaml 差异恰
    6 条（全 `0.` 开头形态）。
  - **缺陷态变红**：写回 HEAD 版声明 → **9 failed / 32 passed**（失败全在新增 `TestZeroFraction`，
    对照全绿）；还原后 sha 一致。
  - **残留边界（预先存在、本轮零变化）**：c4 无浮点字面量声明（`grammar/c4/README.md` 的字面量
    集合 = 十/十六/八进制），`.5`/`0.5` 走词法报错路径——属**既定形态**，不立条目；yaml 点首
    `.5` 仍归裸标量（未声明 `lead_dot`，渲染保真），已写进 `grammar/yaml/README.md`。

- **yaml 负数形态：`key: -5` 被当块序列、`list: [1, -2]` 整篇渲染成空串**
  （`grammar/yaml/base/_number.toml` 的 `yaml_neg` 是**不可达声明** ⇒ 负数在词法层被切成
  `sub` + `number`，语法层再按"块序列指示符"读走）。
  - **实测缺陷**（Lead 探针 + 修复前基线）：`key: -5` → `'\nkey: \n- 5'`（语义变：值成了
    序列项）；`key: -5  # c` → 注释一并丢；`list: [1, -2]` → **`''`（parse 截断，整篇渲染成
    空串）**——内容级损失，非排版差异。
  - **包侧不可行（实测反证）**：语法侧 `NegativeNumber = [sub, number]` 能修好同行/flow 形态，
    但把 `seq:\n- 8080` 吞成 `seq: -8080`（序列指示符被吃）。根因：换行/空格都是 trivia，
    `key: -5` 与换行后的 `- 8080` 化简为**同一 token 对**——"符号与数字是否相邻"只能在词法层判。
  - **修法**：新增与 `lead_dot` 同族的声明键 **`lead_sign`**（`lexer/number_gen.py`
    `build_lead_sign`：符号态**不接受** → 符号后至少一位数字；只对无前缀形态合法、与
    `lead_dot` 互斥、非 bool/违规即 ConfigError），`number_runner.starts_at_declared_non_digit`
    的放行集合加 `lead_sign`；`yaml_neg` 改为 `base_prefix="none" + size={digits="any"} +
    lead_sign=true`（旧 `base_prefix="-"` 按"先证后删"删除：三条入口判据全不命中且全仓零功能引用）。
  - **判据**：`key: -5` → 单 token `literal.number('-5')`、渲染 `key: -5`（相邻）、`# c` 注释
    保住；`list: [1, -2]` / `list: [-1]` / `m: {x: -1}` / `seq:\n- -5` 同；对照
    `seq:\n- 8080` / `- 5` / `[1, 2]` **不回归**。`tests/languages/yaml` **91 passed**
    （改前 82，+9）、`tests/engine/lexer + tests/engine/parser` **434 passed**（改前 414，+20）、
    smoke 462、verilog+c+c4 1153 全绿。
  - **影响面（机器对照）**：HEAD 引擎 vs 新引擎在 29 条数字语料上，verilog / c / c4
    **0 差异**；yaml 恰好 4 条（`-5` / `+5` / `-0.5` / `-1.5` 由拆 token 变单数字）。
  - **缺陷态变红**：三个修复文件临时还原 HEAD → 新判据 **23 failed / 56 passed**（失败全是
    新增判据；既有防劫持门禁 `test_starts_at_declared_non_digit_is_gated` 仍绿）。
  - 两处已接受的行为变化：行首裸 `-8080` 变单数字 token（顶层裸标量本就不支持，非回归）；
    `key: +5` 由词法 `ValueError` 变为可用。**另立 TODO**：`key: 0.5`（正零小数）仍截断为
    `key: 0`（`yaml_zero` 前缀形态无小数链），不在本次范围。
- **`tools/feature_sites.py --save` 在 Windows 把基线写成 CRLF，且 `recorded` 写死旧日期**。
  `.gitattributes` 定死 `eol=lf`，故每次重录都会把 `tools/feature_sites_baseline.json`
  写脏（本轮 `--save` 实测踩到）。修法：`write_text(..., newline="")`（与
  `check_gate_efficacy.py` 同口径）+ `recorded` 改 `date.today().isoformat()`。
  - **顺带透明化**：重录吸收了**存量漂移**（非本轮改动所致）——`formatter` total 78 → 80
    （多出 `tests/fuzz/README.md`、`oracle.py`）、`config scatter` 26 → 29（`style_check`
    2 → 7、`macro_hygiene` 4 → 6），删档（ADR-0017/18/20）致 5 个实例 total 各 −1。
  - **判据**：`python tools/feature_sites.py compare` → ✓ 无散点增长；
    `tests/policy/test_feature_sites.py` + `test_code_registry_sync.py` 12 passed；
    `git ls-files --eol tools/feature_sites_baseline.json` → `i/lf w/lf`。

- **`SyntaxWarning` 门禁在 Python 3.11 上恒绿（反向自检红）**
  （`tests/policy/test_no_syntax_warnings.py`）。非法转义的编译警告**类别随版本变**：
  **3.12 起是 `SyntaxWarning`，3.11 及以前是 `DeprecationWarning`**（实测
  3.11.13 → `DeprecationWarning: invalid escape sequence 'p'`；3.14.5 →
  `SyntaxWarning: "\p" is an invalid escape sequence…`）。原判据只认
  `issubclass(category, SyntaxWarning)` ⇒ 3.11 上 `_syntax_warnings` 恒返回空：**全仓门禁
  恒绿**（该管的非法转义一处都扫不到）+ 反向自检 `hits == []` 红——CI `3.11 ubuntu`
  的 `1 failed, 3202 passed` 就是这一条（前一轮被更早的红盖住，这轮才露头）。
  - **修法**：判据改"类别**或**消息"双判（新增 `_is_invalid_escape`：任何
    `SyntaxWarning`，或消息含 `invalid escape sequence` 的警告）——3.11 面因此被门禁
    **真正覆盖**，不是只把自检改绿。
  - **判据**：PyPy 3.11.13 复跑同一判据 = 全仓 `hits: 0`、自检
    `hits: ["<self-check>:1 invalid escape sequence 'p'"]`（改前为空）；本机 3.14 三例绿。
  - **回归**：新增 `test_escape_predicate_covers_pre_312_deprecation_warning`（跨版本判据
    单测，与解释器版本无关）+ 自检用例保留。

- **fuzz 种子集随平台/本机残留而变 ⇒ CI 报的 finding 本机复现不出**
  （`tests/fuzz/generate.py::collect_seeds`）。两个独立原因叠加：
  ① `os.walk` 的**目录遍历序**取决于文件系统（Windows ≠ Linux），顺序一变
  `rng.choice(seeds)` 抽到的种子就变——同一 `--seed` 在 CI 与本机跑的是**两串输入**；
  ② 收取范围含流水线**自己的输出目录**（`out_dir/{gen,ast,symbols,lex,trans_callback}`，
  `.gitignore` 已列明），本机因跑过 e2e 残留 66 个 `gen/*.v` ⇒ 种子 185 个而 CI 只有
  119 个。
  - **修法**：walk 期间原地排序目录名（并剔除输出目录），结果再按 POSIX 形式路径排序
    （排序键不含平台分隔符）。
  - **判据**：修前 `--iters 500` 本机 `findings: 0` 而 CI 报
    `[NON-IDEMPOTENT] mut:ref_comments.v`；修后本机种子数 = CI 的 **119**，且同一命令
    **逐字复现**该 finding（再据此缩小到 34 字节最小复现）。
    **另核**：与 `PYTHONHASHSEED` 无关（`0` / `12345` 两档同为 `findings: 0` + 同一条
    advisory），且远端 Nightly（ubuntu，5000 轮）与本地同序同结论 ⇒ 跨平台同序列。
  - **回归**：`tests/policy/test_fuzz_shrink.py::TestSeedCollection`（3 例：排除输出目录 /
    POSIX 键排序 / 目录序无关）。

- **fuzz oracle 判据比已接受契约更严 ⇒ 拿"刻意接受的行为"当缺陷报红**
  （`tests/fuzz/oracle.py`）。`non-idempotent` 一类此前对**一切**文本漂移判违反，与产品
  契约和已接收档冲突：
  - **展开路径**（源含宏/指令 marker）——`pipeline._check_idempotent` 明确跳过
    （宏体替换/条件分支/注释锚点漂移是展开语义），oracle 却照判；
  - **一遍收敛的空白漂移**——注释回插在格式化**之后**，注释邻接空白不是首遍不动点
    （`module c( input n /**/);` → `… /**/ );`，三遍起稳定），与
    `docs/gaps/gap-formatter-line-behavior.md` #5 的"一遍收敛、输出合法、仅空白差异"同型。
  - **修法**：判据改成"**不收敛**或**改动落到非空白字符**才算违反"，上述两类记
    **advisory**（`evaluate_format(advisories=…)`）——不进 findings、不落盘、不影响退出码，
    但由 `run_fuzz` 汇总打印（不静默吞掉）。
  - **判据**：`--iters 5000` 由 `findings: 1` → **`findings: 0` + 1 条 advisory**；判别性
    对照 = 注入式假管线"每遍多一个 `#`"（非收敛、非空白）仍判违反
    （`test_fuzz_shrink.py::TestChain::test_refuse_sediment_for_live_nonidempotence` 原样绿）。
  - **不在豁免面上的**（实测核对，避免把两条并成一条）：C 包注释折行漂移
    （`int first /* x×60 */, second;`）注释是从 `first,` 之后**换位到** `second` 之后——
    压掉空白后两遍**不相同** ⇒ 仍判违反，维持作者"永久留在活缺陷一侧"的定案。
  - **回归**：`tests/policy/test_fuzz_shrink.py` 新增 `TestOracleAcceptedDrift`（4 例）。

- **跨盘 nodeid 归一只在 Windows 成立 ⇒ CI 的 Linux 腿必红**
  （`tools/check_test_isolation.py::_normalize_id`）。`os.path.relpath` 抛 `ValueError`
  的跨盘分支此前把**原路径**回填给后续判据，而 `C:/tmp/...` 在 POSIX 上不以 `/` 开头、
  `isabs` 为假 ⇒ 归一失效（同一失败在"绝对 vs 相对"两种写法下算成两条）。
  - **修法**：跨盘即"给不出仓内相对路径"⇒ 该分支直接压 basename（Windows/POSIX 的
    `basename` 在 `C:/a/b.py` 上都取 `b.py`）。
  - **判据**：CI 3.11/3.13 ubuntu 的 `test_normalize_id_survives_cross_drive`
  （`1 failed, 3195 passed, 18 skipped` 里唯一那条）转绿；本机
  `tests/policy/test_check_test_isolation.py` 20 passed。

- **CI Windows 侧门禁脚本自崩（`UnicodeEncodeError`）——5 个入口脚本补 stdout 自护**。
  GitHub 的 windows runner 不设 `PYTHONUTF8`（本机 DSH 宿主设了 `1`），Python stdout 取
  ANSI 代码页（cp1252）⇒ 打印中文的门禁脚本**自己抛 `UnicodeEncodeError` 退出 1**：
  实测 `ci.yml` 的 policy 步（`check_hardcode.py` / `check_doc_refs.py`）与随后的
  `tests/edge/run_edge.py` / `tests/fuzz/run_fuzz.py`，以及 nightly 的
  `tools/check_test_isolation.py`（它只给**子进程**设 `PYTHONIOENCODING`，自己没护）。
  - **修法**：5 个脚本各加 `sys.stdout/stderr.reconfigure(encoding="utf-8")` 自护
    （`hasattr` + `try/except` 守卫，与 `tests/_bootstrap.py` / `tests/conftest.py` 同一模式；
    reconfigure 只影响本进程，比替换 `sys.stdout` 安全）；`policy/doc_sync.py` 一并补齐
    （同目录工具一致性）。
  - **判据**：`PYTHONIOENCODING=cp1252` 复现旧态 5 脚本全崩；加护后 5 脚本 `exit 0`、
    无 `UnicodeEncodeError`。
  - **回归**：`tests/policy` 300 passed；pyright strict 0 errors。
  - **盲区**（本项为何没被本地排练发现）：`tools/ci_rehearsal.py` 在 `PYTHONUTF8=1` 的
    开发机上跑，环境与 CI runner 不同 ⇒ 该步本地绿、CI 红。遗留项见 TODO「测试基础设施」。

- **`tpc check` 共享渲染器漏接线 ⇒ 精化产物文本静默丢 token**（`analyzer/shared_components.py`）。
  同一函数第 73 行已构造 `Lexer`，但 `Renderer(...)` 没把行终止型注释词表传下去（与
  `pipeline/__init__.py` 的既定接线不一致）⇒ 渲染**子树**时行注释把同行后续元素吃进注释文本：
  实测 `#(parameter W = 4 // note` + 换行 + `+ 2)` 的 `param_default["lib"]["W"]`
  = **`'4 // note + 2'`**（正确为 `'4 + 2 // note'`）、`b #(.W(4 // c` + 换行 + `* 4))` 的
  `param_override` 覆盖值 = `'4 // c * 4'`（正确为 `'4 * 4 // c'`）。
  - **修法**：把内联 `Lexer(...)` 提为局部名，渲染器接上 `line_comment_starts=…`（**唯一**
    生产侧裸接线点；复扫全仓 9 个 `Renderer(` 构造点后 8 WIRED / 1 bare——剩下的
    `test_verbatim_node.py` 与注释接线无关，刻意不动）。
  - **判据**：`tests/engine/analyzer/test_shared_components_wiring.py`（3 例，走真实
    `ProjectChecker.check()`；用"产物文本重新词法化后显著 token 不丢"而非钉死文本，对注释落位
    变化稳健）。**缺陷态实测 3 红**（`'4 // note + 2'` / `'4 // c * 4'`），修复后 3 绿。
  - **回归**：`tests/engine/analyzer` 326 → **329 passed**；golden 值（`"W / 2"` / `"W * 2"` 等）
    原样；`tests/engine/pipeline` 130；lint recall 33/33 FP 0；diag 基线 5548 无增长；edge
    failures 0；`-m smoke` 462。
  - **如实残留（未证）**：这处丢 token **是否会改变用户可见诊断**仍未知——六个样本上诊断面
    无差异（0/0、exit 0），现象是静默的产物文本退化；闭环需消费方分析或更大样本轮。
- **引擎：FOLLOW 推导补全——备选支 / 括号分组 / 后缀组内部的"同层后续兄弟"也进后继集**
  （`parser/follow.py::_propagate_intra`，新增）。旧口径只扫规则**顶层元素列表**，
  `_elem_calls` 取出嵌套 call 却统一并入"元素外" beta ⇒ `(@X, lit)` 这类**备选支内的序列**
  里 `@X` 拿不到同支的 `lit`，该支在**匹配期**被 FOLLOW 检查卡死（加载期不报错，静默）。
  - **活的症状（c4）**：`IndexExpr` 的 `(l_square,@Expression,r_square)+` 组内 `@Expression`
    拿不到 `]` ⇒ **9 个下标形态整条截断**：`a[(0)]` / `a[(i)]` / `a[f(1)]` / `a[f()]` /
    `a[a[0]]` / `a[b[i]]` / `a[sizeof(int)]` / `a[0][f(1)]` / `a[f(1)][0]`（`a[0]`/`a[i]`
    看似正常，是 pratt 内置字面量前缀绕过规则匹配、也就绕过 FOLLOW 检查掩盖的）。
  - **只增不减（机器可证）**：对四个包算改前/改后 FOLLOW 差集 = verilog 新增 0/删除 0、
    c（HEAD 快照）0/0、**c4 新增 11/删除 0**、yaml 0/0 ⇒ 严格 fail-open（不会新增拒绝路径；
    元素级原口径的过度包含**原样保留**，只加一路结构级递归）。分支选择仍可能变化，
    故仍以全量 + 语料门禁为准。
  - **判据**：`tests/engine/parser/test_follow.py` 新增 5 例（备选支尾部 / 括号分组尾部 /
    repeat elem 尾部 / 2 条负向"各支不得互当前继"）；新增
    `tests/languages/c4/test_c4_index_expr.py`（9 正 + 7 对照 + 3 反 + FOLLOW 锚点）。
    **缺陷态实测**：test_follow 3 红 / 12 绿、c4 新用例 10 红 / 10 绿；修复后 15 + 20 绿，
    c4 9/9 翻转、7 对照 0 回归、3 反样本两态皆拒。
  - **回归**：`tests/engine/parser + tests/languages/c4` 244、三语言包 1191、`-m smoke` 462、
    `tests/e2e/run_all_tests.py` 102 例 FAIL 0 且与"HEAD FOLLOW 口径"**逐用例一致**、
    lint recall 100% / FP 0、diag 基线无增长、edge 7 reject / 0 failure；pyright strict 0。
  - **文档**：`grammar/grammar_rule_fields.md`「边界后继」增「FOLLOW 传播范围」段（已递归到
    嵌套内部 + 只增不减 + **仍不覆盖的旁路**：pratt 规则不做 FOLLOW 检查 / `_prod_refs_block`
    旁路 / 静态下界 + 前缀族 fail-open）。
- **C 包：枚举体 `}` 前的尾随逗号被渲染静默丢弃**（`enum e { A, B, };` → `enum e {A, B};`）。
  `EnumBody` 把尾逗号写成**独立可选元素**（`symbol.base.comma?`，`$4`），而渲染走 `items`
  绑定 ⇒ 独立可选元素不进 `items`、静默少一个非 trivia token（与 `grammar/c/README.md`
  「写包者须知」第 8 条同型）。C 里该逗号无语义，但违反本包渲染判据 7「显著 token 序列
  逐项相同（只许动空白）」。
  - **修法**（只动语言包 TOML，production 一行未改）：`EnumBody.parser.node` 增
    `trailing_comma = "$4"`，布局在 compact 段与 `"}"` 之间插 `{ opt = { ref = … } }`
    ——**不能混进 `items`**（join 的分隔符 `", "` 会与标点叠加、多印一个逗号）。
  - **判据**：`tests/languages/c/test_c_render_fidelity.py` 新增 `TestEnumTrailingComma`
    （8 个带尾逗号形态 + 5 个无尾逗号形态 × {token 序列、幂等、无逗号不得凭空多印}，31 例）；
    **缺陷态实测 8 红 / 23 绿**，修复后 31 绿；`pytest tests/languages/c` 656 → **687 passed**；
    三样本 ratio 0.9926/0.9925/0.9822 未降（0.992553/0.992543/0.982216，行覆盖不变）。
  - **同轮实测到的相邻缺陷（未修，已登记）**：`enum e { A, B, // note` + 换行 + `};` 的行注释
    被挂到 `EnumBody` **容器** `trailing` 槽 ⇒ 渲染冲掉收尾 `;`、不幂等、**产物非法 C**
    （先于本次修复存在；#6 同族但**丢 token**）。**两种接线表现不同**（Lead 复核）：生产路径
    （`pipeline` 传 `line_comment_starts=…`）只有尾逗号形态坏；裸 `Renderer(rules_dir)`
    （= 各语言包 harness 的接线）两种形态都坏。已登记缺口档渲染现状表 #8 + 「未做」第 4 条
    （语言包 harness 接线与生产路径不一致，**全仓性**）与 `TODO.md` 对应条目，待作者判。
- **跨语言配置串味：切语言时"本包未声明的 key"没有推回默认 ⇒ 上一个语言的配置留在模块级
  变量里**（`core/config_registry.py::_push_loaded_config`）。实测症状 = `TODO.md` 那条
  「跨语言检查规则泄漏」：同一进程里先扫 verilog、再 `load_all("grammar/c")` 扫 C 源，
  C 包**不声明** `linter.style_check`，于是模块变量仍是 verilog 的（`max_line_width=100`）
  ⇒ **C 源上跑起 verilog 的排版检查**，>100 列的行报出 `ST003`（此前只用白名单挡着，
  且"干净进程 vs 先跑过 verilog"两种顺序结果不同）。
  - **真因（本轮定位，与旧记载不同）**：泄漏不在 linter 自身（每次 `scan` 都新建
    `CheckerRegistry`），而在**模块级 `declare_cfg` 变量**：`_push_loaded_config` 在
    `KeyError` 分支"什么都不推"，注释写的是"保留模块默认值"，但代码没推任何东西——
    而变量当前值可能是**上一个语言**推的。同一机制也影响 `linter.macro_hygiene`
    与其它只被部分语言包声明的 key。
  - **修法**：`declare_cfg` 登记**编译期默认**（`_CONFIG_DEFAULTS`，深拷贝保存/推送），
    `_push_loaded_config` 在 `KeyError`/`RuntimeError` 分支改为**推回默认**。语义由此统一：
    **配置值 = 该语言包声明的 key（+ 用户/CLI 覆盖）；未声明的 key = 编译期默认。**
    同一 key 的多处 `declare_cfg` 默认值不一致 → **fail-fast**（"推回默认"必须唯一）。
  - **判据**：`tests/engine/core/test_config_loading.py` 新增 2 例（verilog→C 后
    `_style_check_cfg`/`_macro_hygiene_cfg` 回默认；默认值不一致 fail-fast）+
    `tests/languages/c/test_c_corpus_impl.py` 新增 `test_cross_language_no_check_rule_leak`
    （症状层：先 verilog 后 C，长行不得报 `ST003`），并把旧白名单
    `others <= {"ST003"}` **收紧为"无任何非 phase 码"**。
  - **文档**：`core/config_lifecycle.md` 新增 §1b（语义 / 真因 / 实测症状 / 判据 +
    "多语言共进程的新消费方仍优先走 `resolve`"的建议）。
  - ⚠ **同轮关闭两项旧 TODO**（判据达成，完成即删）：① 上面这条泄漏项（已修 + 判据）；
    ② 「隔离测试偶发红」——判据"整仓并行 N=10 次零红"**达成**：10/10 全绿，
    每次 **3045 passed / 7 skipped**（历史 1/3 红未再复现，N=10 按判据结案）。
  - ⚠ **另两处"全新检出处"判据复核通过**并据此删除两条已完成 TODO：单测依赖 gitignore
    生成物（`git worktree add` 到空目录后直接 `pytest tests -q` → **3034 passed /
    18 skipped / 0 failed**；产物缺失时相关用例**跳过**而非失败）、隔离工具 nodeid 归一
    （`_normalize_id` 已接 `ValueError`、始终保留 `::用例名`、路径压 posix；自测 20/20 绿）。

- **C 语义基座方向落档（作者 2026-10-10 裁决 8 条）**：`docs/gaps/gap-c-semantic-base.md`
  「待拍板」→「**已拍板**」。关键设计 = **不走 parser 谓词键/运行期钩子**（延后），改为
  **linter 先过歧义路径**——路径不收敛时出**内部 warning** → parser 走 **raw 暂缓建树** →
  **analyzer 插件**补理解路径；符号**提前注册 + 分期标注**；未声明标识符默认偏置**显式化**；
  raw 作**内部机制**（先例 = 宏体 raw 源区间）；parser `_ScopeStack` 与 analyzer `Scope/Symbol`
  **不合并**但机制文档写明**本质是一套识别系统的不同时期**；两遍只允许 pre-scan 重排候选。
  - **机制现状实测落档**：linter "平手静默择一"与"候选全败 ⇒ blocking ⇒ 输出空串"、
    `ident_candidates` 全局无上下文（伪候选）→ `docs/gaps/gap-parser-linter-approximation.md`；
    内部 warning 载体、raw 承载（`_verbatim_text`，渲染零改动）、**符号回滚两个洞**
    （快照不含符号 store；`restore(depth)` 不撤销同深度、pratt 不推 `rule_frame`）、**两侧
    token 流不同源**（位点须用行/列）、`phase` 走 `attrs` 两步法 → `gap-c-semantic-base.md`。
  - `ROADMAP.md`「C 语义层切片 1b」改为 **P1→P4 分片**（P1 已交付、P2a 已交付）。
- **任务循环落档**（作者 2026-10-09 定的六步循环）：`policy/collaboration.md` 新增「任务循环」
  —— ① 取任务输入（作者输入 + 已知缺口，一次一个）；② **复述核心约束**（引擎不留语言知识、
  只留抽象通用模式；语言能力流入插件；AST 前声明式闭环；AST 后插件驱动开放；时点管线编排；
  可视化报告输出）；③ 先调研后计划再实现，全程留记录、前后一致（不许狗头羊尾）；④ 独立判据
  + **全量框架测试**；⑤ 收口（声明缺口与归属、同步文档、删完成/废弃项、改动收最小）；
  ⑥ 回起点（循环记录以 `CHANGELOG.md` 为准，不另设流水账）。`AGENTS.md` 同步一行指针。
- **决策权移交 + `DRAFT.md` 暂存区清零**（作者 2026-10-09：细节决策全部交维护者，作者只参与
  框架级；主线 = **补齐 C 包框架缺口 → 性能化改进 → 缓慢迭代**，架构基本定型）。
  - `policy/collaboration.md` 新增「决策权归属」：**框架级**（架构方向、引擎↔插件边界、语言
    包战略与支持范围、发布/推送/版本、跨子系统机制立项、对外定位）→ 作者拍板；**细节级**
    （实现形态与算法、判据与门限、边界接受/不做登记、文档归位与裁剪、工具与门禁细节、命名
    文案）→ 维护者自决并落档；四条**升级判据**（要新增契约面/配置 schema、要改对外承诺、
    取舍不可逆且成本未知、作者点名）。`AGENTS.md`（一行指针）与 `ROADMAP.md`「当前主线」
    （主线三段 + 架构定型声明）同步。
  - **`DRAFT.md` 四条全部落定出口，暂存区按纪律清空删除**：① `tpc check` 产物丢 token 的
    "用户可见影响"不可追溯 → **接受**（现状入
    `docs/gaps/gap-semantic-elaboration-boundaries.md` 边界 5）；② `c99` 基线不再切 `c89` 层
    → **不做**（入 `docs/gaps/gap-language-pack-scope.md`「C 语言包：接受域现状」仍存边界表）；
    ③ yaml `yaml_neg` → 调查落锤为**内容级缺陷**（转修复，见下 Fixed）；④ `feature_sites`
    基线静默过期 → **立项**（入 `ROADMAP.md` P2.8「按需门禁的定期节奏」）。
- **规划文件收口：TODO/ROADMAP 重写、gaps 十档裁剪、ADR 清空、新建 `DRAFT.md`**
  （作者 2026-10-08 要求：清理过时/已解决的缺口，把要做的事收口到 TODO 与决策文件，
  不让这些文件无限增长，**预期外的情况单独放短期草稿**）。三份规划面此前已从"待办清单"
  退化成"过程档案馆"——正文大量是已完成叙述与测试/CHANGELOG 的复述。
  - **归位口径**（本轮统一）：未完成·短期 → `TODO.md`（每项 ≤6 行 = 现状 + 判据/触发条件 +
    链）；未完成·中长期 → `ROADMAP.md`（≤8 行）；现状边界 → `docs/gaps/`；生效决策 →
    `docs/decisions/`（完成即删）；**预期外/未定判/影响面未知 → 根目录 `DRAFT.md`**（新建：
    每条必写"现象 + 待判点 + 出口"，上限 8 条 / 70 行，**清空即删**）。删除判据沿用
    `policy/doc-alignment.md`（C1 / C2 / C3 / B5 + 完成即删）。
  - **新增容量门禁** `tests/policy/test_planning_doc_budget.py`：`TODO` ≤160 / `ROADMAP`
    ≤320 / `DRAFT` ≤70 / 单 gap 档 ≤200 / 单 ADR ≤150 / ADR 总数 ≤10——**超限先删旧**门禁化
    （取代"下次记得删"）；口径写进 `policy/doc-alignment.md`「容量上限」+
    `docs/README.md`。
  - **行数变化**：TODO 397 → **78**；ROADMAP 498 → **320**；gaps 十档 1228 → **690**
    （索引 README 65 行）；`gap-language-pack-scope.md` 427 → **133**、
    `gap-language-penetration.md` 193 → 85、`gap-feature-scatter.md` 194 → 83——十档均
    ≤200、**无整档删除**（活边界本体都在，删的是过程叙述与复述）。
  - **`docs/decisions/` 清空（保留 README 制度）**：0017 / 0018 / 0020 三档 ADR 全删——
    决策**全部仍在生效**，但已分别被 `preprocessor/README.md` / `linter/linter_architecture.md` /
    `core/component_protocol.md` / `core/engine_capabilities.py` / `docs/gaps/gap-feature-scatter.md`
    与相应测试吸收（命中"完成即删"）；`check_doc_refs` 的 D4 孤儿（ADR-0020）随之为 0。
    代码/测试里 **20 处内联历史标签按政策保留**（`（ADR-00xx 决策 N）` 作历史编号，全仓另有
    200+ 处已删 ADR 的历史标签，只清这 20 处反而不一致）。
  - **搬迁而非删除的知识**：① L2「引擎 vs 插件的能力边界设计原则」（三分法 / 两个可机械测的
    失效信号 / 普适原语清单 / 取舍定位）从旧 TODO 整节搬进 `core/component_protocol.md`；
    ② 被否备选与"为什么"内联进 `preprocessor/README.md`（宏处置策略：判定条件是语言知识，
    纯 TOML 策略表会演化成小型 DSL）与 `renderer/renderer_architecture.md`（宏节点 raw 直出
    的自述判据）。
  - **数字漂移修正**（逐条现测；权威源 = 工具/测试）：`tools/c_acceptance.py` **42 条 /
    接受 40 / 空洞 2**（旧记"40 条 · 接受 38"，同档还并存过"25/3"自相矛盾）；
    `render_coverage` verilog **265** 条规则（旧记 258）；档位矩阵 **26** 构造 × 4 档（旧记
    28）；C 保真 **62 例**（旧记 60）；`min_pack` 基线 `passed=1186`（旧记 1126）；渗透探针
    **硬信号 11 处全在 parser、analyzer 0**（旧记 analyzer"183 处"、Tier A 187）；
    generate 条件面声明键已迁插件 `gen_activity`、`test_gen_face.py` 已不存在（关联改指
    `test_elaboration_gen_activity.py`）；不可仓内复核的历史数字（差分语料规模、
    183k tok/s、"138 份样本"）改为标注口径而非当成现状。
  - **引用面同步**：`docs/MODEL_INDEX.md` / `grammar/c/README.md` / `grammar/c/tpc.toml` /
    `grammar/c/plugins/c11/tpc.toml` / `tools/README.md` / `tools/c_acceptance.py` /
    `tests/**` 的锚点与 `Doc:` 头改指裁后标题（「C 语言包：接受域现状」/「C 包渲染/保真面
    现状」/「运行时档位：`enabled` 的语义边界」/「已知偏差」）；`linter/linter_architecture.md`
    删掉过时行"while/repeat 无完整语法规则"（实测 `WhileLoop`/`RepeatLoop` 已在
    `grammar/verilog/04_statements/20_for.toml`）；移除 3 处指向 `_drafts/` 的一次性脚本引用
    （该目录随收尾销毁，`policy/structural_budget.md` 已明令不留此类引用）。
  - **新登记为待办**（此前只存在于审计/审计草稿）：结构欠账 `tools/structural_score.py
    --compare` 实测 **S = 0 → 287（16 项新增）**未按 R6 逐项下结论；未自护入口脚本现测
    **24** 个（旧记 18）；功能散点步 2b 剩余 16 点；`check_doc_refs` D3 不查 blockquote 续行
    （悬空 `Test:` 引用不可见）；渲染偏差 #3（解析侧注释归属的 **token 跨度**判据）。
  - **`DRAFT.md` 首批三条**：① `tpc check` 精化产物丢 token 的"用户可见影响"未证明
    （六样本诊断面 0/0）；② `c99` 基线要不要再切一层 `c89`（0.1.3 阶段 0 记为"首个待决项"
    后无归属）；③ yaml `yaml_neg` 声明的可达性（`-5` 实际是 `minus` + `5`，该声明从未生效）。
  - **覆盖率远期目标已达成**：全量 `python -m pytest tests -q -n 4 --cov` 实测 **90.39%**
    （12486 语句 / 1200 未覆盖；3218 passed / 7 skipped，290s）⇒ ROADMAP「覆盖率远期
    目标 ≥90%」按"完成即删"移除；`pyproject.toml` / `tests/README.md` /
    `docs/gaps/gap-verification-engineering.md` 的旧数字（89.73% / 86.81%）同步为现测值
    （覆盖率门禁 `fail_under = 80` 不变）。
  - **验证**：`tests/policy/test_planning_doc_budget.py` 绿（三文件在限内）；`check_doc_refs`
    D1/D2/D3/D4 全 0；`check_hardcode --strict-doc --strict-import` 干净；policy 套件 +
    受影响语言包/引擎套件全绿（数字见提交）。
- **测试口径：语言包保真 harness 的 renderer 对齐生产接线**（作者 2026-09-28 的 reminder 轮里
  由 Lead 定案落案 (a)）。生产路径 `pipeline/__init__.py` 构造 `Renderer(…, line_comment_starts=
  lexer.line_terminating_comment_starts())`（渲染器据此在行终止型注释前补硬换行，防"注释吃掉
  同行后续元素"），而语言包 harness 一直用**裸** `Renderer(rules_dir=…)` ⇒ **harness 面对的
  renderer 配置 ≠ 用户路径**，这一类缺陷在单测层不可见。
  - **改动**：5 处各一行（C 的 `test_c_render_fidelity` / `test_c_declarations` /
    `test_c_increment_plugin` / `test_c23_increment_plugin` + yaml 的 `conftest`）。
    **例数不变、零翻转**：`tests/languages/c + tests/languages/yaml` 792 → **795 passed**
    （+3 为新增门禁）；三样本 ratio/行覆盖**完全不变**（0.992553 / 0.992543 / 0.982216，
    无需重录）；`tests/engine/renderer + tests/engine/pipeline` 300 passed。
  - **新增接线门禁 3 条**：C `TestHarnessWiring`（`enum e { A, B // note` + 换行 + `};` 的
    token 序列 + 幂等；**裸接线 2 红 / 接线绿**——尾逗号形态两接线都坏，是已登记的 #8，
    不能当接线判据，已在注释写明）+ yaml `test_harness_renderer_keeps_line_comment_wiring`。
  - **同轮修**：`tests/languages/c/samples/edge_comments.c` 头注把漂移缺口写成 "#8"（实际 #6）
    的过期引用；改后三样本数字不变。
  - **登记**：缺口档「未做」第 4 条改写为"语言包 harness 已对齐；只剩生产侧
    `analyzer/shared_components.py` 一处"；yaml 真实 workflow 渲染不幂等登记进
    `docs/gaps/gap-formatter-line-behavior.md`（与接线无关、当前无门禁覆盖、本轮不修）。
- **工作区行尾统一为 LF（`.gitattributes` 定死规则）**——作者 2026-09-28 拍板"可以统一"，
  据此关闭 `TODO.md` 里那条"行尾风格不统一"的待拍板项。
  - **背景**：仓库只有本机 `core.autocrlf=true`（只在 `git add` 时归一索引、不回写工作区）
    ⇒ 工作区三态并存：831 个跟踪文件里 **CRLF 653 / 仅 LF 176 / 混合 2**。
  - **做法**：`.gitattributes` = `* text=auto eol=lf`（优先于 `core.autocrlf`，本机 / 干净
    检出 / CI 取到同一份内容），随后把本机工作区按索引重新物化 ⇒ `git ls-files --eol`
    现为 **全部 `i/lf w/lf`**、`git status` 干净。**索引内容零变化**（`autocrlf` 早已把
    索引归一为 LF），故这不是"改写已入库内容"的动作。
  - **两条核实**：① 混合的 2 个 = W201 夹具各 1 行 CRLF（都落在文件末行 `endmodule`）⇒
    判为**无意产物**；全仓无测试依赖夹具行尾（CRLF/BOM 覆盖由内联字符串用例守着）；
    ② 无二进制资产（仅 2 个 `.ps1`，LF 可运行），不需要 per-path 例外。
  - **判据**：全新检出 `git status` 干净 + `git ls-files --eol` 全 `i/lf w/lf` + 全量
    `pytest tests/` 在 Windows（LF 工作区）同绿。
- **四条"待拍板"按作者 2026-09-28 口径结案**（不再挂着当悬项；机制文档同步）：
  - **保真度渲染：注释折行漂移**（`TODO.md` 里那条带最小复现的长项）——**不修渲染**。
    否决"锚点感知 LineSuffix"（要新增"哪些符号是列表分隔符"的声明字段，且须逐形态验证
    "误路由 = 丢注释"）与"挂刚结束的项节点"（大概率只是把漂移换个方向）两案；
    **归入原始路径（raw）解决**：需要还原原文时从原文取信息，先例 = 宏
    （`MacroCall._macro_source_text` 直出原文）。注释从不丢失 ⇒ 该偏差登记为
    **已知且接受**（`docs/gaps/gap-language-pack-scope.md` 渲染现状表 #6 已改写；
    `tests/fuzz/README.md` 增"已知 oracle 判定"一条：不沉淀、不新增登记）。
  - **`[plugins] enabled` 的语义边界**（只门控声明面 vs 门控一切）——**不急着选**：
    先按现状走，等真实需要出现再定；`TODO.md` 该条从"需拍板"改为"慢慢补充"并写清
    两种语义各自的补齐方式（选 ① 就补 `core/config_lifecycle.md` 一节，选 ② 就按三条判据改造）。
  - **切片 1b 的"候选是否收敛"要不要升为 parser 一等判据**——**按项目约束走**（能纯语法
    判定就纯语法，判不了就记边界）；某机制在真实需要里证明非常好用之后再接受它升为一等判据
    （`ROADMAP.md` 待决项已加口径）。
  - **阶段 3/4/5 的顺序**（作者授权自定）：**先阶段 3**（结构类型与作用域语义——切片 1b 的
    前置，也是"AST 之后那半段"的第一个真实入口）；阶段 4 与语法面解耦、独立评估；
    阶段 5 随语料接入滚动做；三者排在 0.1.4（高性能组件）之后。

- **C 包 c23 属性：实参形态与属性表形态收口——多实参 `[[gnu::nonnull(1, 2)]]` + 尾随逗号
  `[[nodiscard,]]`**（作者口径"慢慢补充"下按实测优先级取的两条；①空实参 / ②相邻字面量 /
  ④空属性表 / ⑤配平 token 序列 登记"不做 / 低优先 + 触发条件"）。
  - **多实参**：实参由 `@Expression`（assignment-expression 层级、**不含逗号**）改收
    `@ArgumentList`（逗号分隔表达式列表，"实参表"语义）。修前 glibc/clang 头文件常见形态
    `[[gnu::nonnull(1, 2)]]` / `[[gnu::format(printf, 1, 2)]]` /
    `[[clang::no_sanitize("a", "b")]]` **全部解析失败**（实测），是本轮比登记三条边界更常见的
    真实缺口（由"属性剩余形态"专项调研实测发现）。
  - **尾随逗号**：`AttributeList` 加**独立可选元素** `(comma)?` + **单独绑定**
    `trailing_comma`（**不得塞进 `items`**：join 的 `sep = ", "` 会叠加成 `, ,`；
    不绑定则静默丢 token）；`[[nodiscard,,]]` / `[[,]]` **仍被拒**（不过接受）。
  - **判据**：`tests/languages/c/test_c23_increment_plugin.py` 199 → **223 passed**
    （7 条新形态 × parse/render/lint 三组参数化 + 3 条结构化判据）；反样本 10 条仍被拒
    （① ② ④ ⑤ + 破损形态）；**缺陷态实测**：③整体回退 10 红、只删绑定 4 红、塞进 items 4 红、
    ②′回退 16 红、绑定退回整组 9 红。C 包 **687 → 711 passed**；`tools/c_acceptance.py`
    仍 **40/42**（只扩展既有"属性说明符"用例源码，不增条数）。
  - **文档**：`plugins/c23/21_attributes.toml` 头注重写（①②④⑤ 逐条"现状 / 为什么不做 /
    触发条件" + 节号双引 `N3096 §6.7.12.1 / N3220 §6.7.13.2`）；`grammar/c/README.md`、`TODO.md`、
    `ROADMAP.md` 同步。
  - **调研留档**：引擎是否需要"配平 token 序列"新形态 = **暂不做**（现役 production 微语法是
    闭集，8 种候选拼写全 `GrammarError`；需新增元素类型、横跨 parser/linter/preprocessor
    10+ 处分派表），触发条件 = 真实语料出现非表达式 token 序列。
- **引擎新能力：空槽位（empty slot）——注入可落在"序列中段的原子规则位点"上**；C 包据此收口
  `[[属性]]` 剩下的两个位点（**声明符内** / **枚举项**）。接受面 **38/40 → 40/42**；
  档位矩阵 26 → **28**。
  - **问题（2026-09-28 实测，旧记载的两条死路）**：现役注入只能"并入某一条既有元素"
    （`@Rule.production[N]`）或"越界追加到末尾"——**插不了序列中段**。故声明符内属性缠成
    `choice[repeat, @Attr]`（可空 repeat 永远先"成功" ⇒ 属性支试不到、整条声明空 AST），
    枚举项则"`Enumerator` 序列中间没有可注入的交替点"。
  - **做法 = 把中段做成原子规则**：核心声明 `AttributeSlot`（`production = []` 的**非块规则**
    = 无自有形态的共用扩展点位；`inline = true` + 单字段绑定 ⇒ 不进 AST），
    `DirectDeclarator`（头与后缀链之间）与 `Enumerator`（`=` 之前）各留一个 `@AttributeSlot*`
    元素；插件把 `AttributeSpec` 注进槽位即可——**一处声明，两个位点**（同"公共宿主"的收益），
    且不依赖任何跨元素回溯。
  - **引擎侧两处配套**（与"空槽位"同一概念，成对落地）：`parser/grammar_inject.py::_inject_direct`
    对空产生式的**非块**规则走"零长 append"（旧实现 `if not prods: return` 静默跳过 ⇒
    槽位永远无形态）；`core/define.py::_check_pos_ref` 为 `empty_slot` 放行 `$1`
    （注入后它恰是唯一元素）。**块规则的空产生式（根块）语义不变**（由块机制驱动，注入 no-op）。
  - **位点按标准落**（避免顺手改宽）：属性紧跟 identifier 之后、后缀链之前（标准例
    `void f [[deprecated]] (void);`），故 `int a [[deprecated]] [3];` 认、`int a[3] [[deprecated]];`
    不认；枚举项属性在 `=` 之前（§6.7.2.2）。⚠ **一处过接受如实登记**：`(f) [[deprecated]]`
    也会被接受（标准只允许紧跟 identifier 之后）——要严格匹配需把 identifier 与属性合成一条
    head 规则，代价是 AST 多一层包装且属性会随 inline 展平丢失，判为不值。
  - **判据**：`tests/engine/parser/test_grammar_inject.py` 新增 `TestEmptyProductionSlot`（4 例）+
    `tests/engine/core/test_rule_schema.py` 新增 `TestEmptyProductionSlotBinding`（3 例）+
    `tests/languages/c/test_c23_increment_plugin.py` 8 条新形态进 `_CASES`（三组参数化各跑
    节点/渲染保真+幂等/linter 零诊断）、「两处共用同一空槽位且 inline 展平」断言、
    边界用例从四条收窄到**三条形态**；`test_c_standard_tiers.py` 矩阵 +2 行（`since=baseline`，
    即"无关键字依赖 ⇒ 四档都有"）；`tools/c_acceptance.py` 40 → **42 条**（接受 40 / 空洞 2）。
    门禁有效性（`tools/check_gate_efficacy.py`）新增 **4 条变异**：槽位 target 缺失、
    引擎填充分支回退、`$1` 放行回退、属性宿主换单点——每条都已证明在缺陷态变红。
  - **文档**：`grammar/grammar_rule_fields.md` §production 增"空产生式两种含义 + 空槽位用法"
    （`docs/language_walkthrough.md` 新增「规则注入」一节，含三个落点与选择顺序）；
    `grammar/c/01_declarations.toml`／`02_types.toml`／`plugins/c23/21_attributes.toml` 头注；
    `grammar/c/README.md`「写包者须知」+第 10 条（"要给序列中段加形态，别硬注——用空槽位"）。
    槽位另补了一条**兜底渲染配置**（`inline` 规则通常不走布局，但包内口径是"每条规则都有
    渲染配置"——`tools/render_coverage.py grammar/c` 现为 **112 条 / 112（100%）**）。
- **引擎新能力：配置声明级合并语义 `merge = "by-name"`——插件可给核心配置"补字段"**；
  C 包据此落地十进制浮点字面量后缀 `1.5df`/`1.5dd`/`1.5dl`（C 包标准增量面至此**全部收口**）。
  接受面 **37/39 → 38/40**；档位矩阵 25 → **26**。
  - **问题**：同名配置声明跨来源取值此前是**后者整体覆盖**（`_resolve_decls` 的
    `loaded[name] = merged`）。C23 的十进制后缀作用在**核心基线的数字形态**上
    （`[[number.based]] name = "c_dec"`）⇒ 插件只有两条死路：① 改核心 `base/_number.toml`
    （会让**基线档**也接受 `1.5dd`，污染档位语义）；② 整条重抄 `c_dec`（知识重复、必然漂移）。
  - **做法**：文件式声明可写 `merge = "by-name"`——该声明与同名声明之间改走
    `merge_by_name`：`dict+dict` 逐键递归、`list+list` **命名条目按 `name` 合并**
    （同名深合并·原位·保序，新名追加）、其余覆盖。于是插件只写局部条目：
    `_number_c23.toml` = `name = "c_dec"` + `suffix = { chars = "uUlLfFd", max = 3 }`，
    其余字段由核心形态供给（**知识的单一来源**）。
  - **纪律三条**：① **缺省不变**（不写 `merge` 仍是后者覆盖 ⇒ 对既有配置零影响，不搞隐式
    魔法）；② `merge` 只认 `"by-name"`，其他值 **fail-fast**；③ **认不出就不猜**——
    按名合并要求列表元素是"带非空 `name` 的表"，否则 fail-fast；同一 key 被多个插件声明且
    都写了 `merge` 而不一致，同样 fail-fast。
  - **验证（档位判别一并守住）**：c23 档 `1.5dd` 合成**一个** `literal.number`，且
    `1.5f`/`42u`/`0x1F`/`1.5e3L` 等核心后缀形态**不受影响**；**基线档仍切成 `1.5` + `dd`**
    （若有人把 `d` 写进核心 `_number.toml`，那条用例会红）。判据：
    `tests/engine/core/test_config_loading.py` 5 例（补/追加/保序、缺省覆盖不变、两条
    fail-fast）+ `tests/languages/c/test_c23_increment_plugin.py` 2 例 +
    `test_c_standard_tiers.py` 新增 1 行（`_Decimal64 e = 1.5dd;`，since=c23）。
  - **文档**：`core/config_lifecycle.md` 新增 §4b（语义 / 边界 / 纪律 / 判据）并更新声明字段
    清单；`grammar/c/README.md` 增「"加规则"之外还有一类：合并既有配置」一段；
    `plugins/c23/{tpc.toml,_number_c23.toml,20_decimal.toml,_token_ext.toml}` 头注。
- **C 包 c23 属性说明符 `[[…]]` 落地——c23 语法增量至此收口**。接受面 **36/38 → 37/39**；
  档位矩阵 23 → **25**。
  - 三条规则各担一层：`AttributeSpec` = `[[ … ]]`（词法上就是两个 `[` / 两个 `]` token，
    **无需改词法**）、`AttributeList` = 逗号分隔（`items` 合并绑定）、`Attribute` = 名
    （**带前缀** `gnu::unused` 按标准 `attribute-prefix :: identifier` 两层收）+ 可选实参组。
  - **注入点 = `@TypeQualifier`**（那个公共宿主）：一次注入覆盖声明/函数定义首说明符位、
    说明符序列其余位（`int [[deprecated]] x;`）、结构成员、参数位、类型名位；
    **连续属性说明符**（`[[a]] [[b]] int x;`）由 `SpecRest*` 自然吃掉。
  - **"属性声明"形态不需要额外规则**：`[[fallthrough]];` / `[[assume(x > 0)]];` 正好是
    "说明符 + 空声明符表 + `;`"，落进核心 `Declaration` 即可（文件与块作用域都通）——
    少一条规则、少一个位点。
  - ⚠ **实测边界（如实登记，判据钉住）**：① 空实参 `[[deprecated()]]`、② 相邻字面量拼接
    `[[deprecated("a" "b")]]`、③ 属性表**尾随逗号** `[[nodiscard,]]`（标准允许）——
    都需引擎侧"配平 token 序列 / 可空项列表"形态；④ 声明符**之后**与**枚举项**上的属性位点
    未做（要在核心 `Declarator`/`Enumerator` 后缀位加分支）。**✓ 实测可用**：嵌套括号实参
    `[[gnu::aligned(sizeof(void *))]]`、`[[gnu::aligned(16 * 2)]]`、属性在函数定义前、
    属性在 `const` 之后。
  - ⚠ **顺带撞出一条真实的档位边界（本轮最有价值的发现）**：`[[属性]]` **不依赖任何新关键字**，
    而插件**规则文件**由 `setup_grammar` → `load_all_components` **无条件**加载 ⇒
    **基线档（`enabled=[]`）也解析出 `AttributeSpec`**：这个构造上"档位 = 接受域"不成立。
    此前该边界只是假想（`TODO.md`「`[plugins] enabled` 的语义边界」），现在有了实测症状，
    判据 = `test_c_standard_tiers.py::TestKeywordFreeIncrementsAreNotTierGated`
    （含对照：靠关键字落地的增量在基线档确实进不来）。选"门控一切"语义时属性会自动被门控；
    选"只门控声明面"则要把"纯语法增量不受档位约束"写成该语义的**代价**。
  - **判据**：`test_c23_increment_plugin.py` 120 → 167 例（15 条属性用例进 `_CASES` 的三组
    参数化 + 「属性走 `TypeQualifier`」+ 边界钉住用例 + 注入清单扩到 12 个文件）；
    `test_c_standard_tiers.py` 新增 `TestKeywordFreeIncrementsAreNotTierGated`（2 例）；
    `tools/c_acceptance.py` 38 → 39 条；15 个属性形态 token 序列不变 + 幂等 + linter 零诊断。
- **C 包 c23 类型词落地：`_BitInt(N)` 与 `_Decimal32`/`_Decimal64`/`_Decimal128`
  ——c23 语法面只剩 `[[属性]]`**。接受面 **35/37 → 36/38**；档位矩阵 21 → **23**。
  - `_BitInt(N)`（§6.7.2.1）：标准形态**宽度必选**（`_BitInt` 单独出现不是类型说明符），
    故是 4 元素序列（与 `typeof` / `_Atomic(T)` 同形）；注入 `@SimpleType`（最窄公共点）。
  - `_Decimal32/64/128`（§6.7.2）：三者形态与位点完全相同、只差拼写 ⇒ **一条规则的裸 token
    交替**（同核心基线 `SimpleType` 的写法），同样注入 `@SimpleType`。
  - **接受域口径（本轮定，写进包内头注）**：`_BitInt` 的宽度收 `@Expression`——"是不是整型
    常量表达式、是否落在 `1..BITINT_MAXWIDTH`"归语义层（同 `_Alignas` 实参、位域宽度、
    数组长度三处既有宽进口径）；`_Decimal*` 只认"这是一个类型词"。
  - ⚠ **登记一条真缺口（不是"支持"）**：十进制浮点**字面量后缀** `1.5df`/`1.5dd`/`1.5dl`
    未落地，`1.5dd` 目前切成 `literal.number(1.5)` + `id(dd)` ⇒ `_Decimal64 x = 1.5dd;`
    整条解析失败。**两条实测证据**说明它为什么不在本包顺手做：① 后缀声明在
    `base/_number.toml`（**核心基线**），写进去会让**基线档**也接受 `1.5dd`（档位语义被污染）；
    ② 插件侧另声明一份 `number` 会被 `deep_merge` 的**列表后者覆盖**顶掉核心三条数字形态
    （`core/config_registry.py::deep_merge`："非 dict 值后者优先"）⇒ 要先给"数字形态列表"加
    **跨声明合并**语义（引擎侧小项，涉及所有 list 型配置的合并语义，不顺手改）。
    现状由 `test_decimal_literal_suffix_is_a_known_gap` 钉住（闭合时会红，提醒同步文档）。
  - **判据**：`test_c23_increment_plugin.py` 82 → 120 例（12 条新构造进 `_CASES` 的三组
    参数化：解析 / token 序列 + 幂等 / lint 零诊断；新增"类型词走 `SimpleType`"与上面那条
    缺口登记用例；注入目标清单扩到 11 个文件）；`test_c_standard_tiers.py` 矩阵 21 → 23 行；
    `tools/c_acceptance.py` 37 → 38 条；17 个类型词形态（声明/指针/成员/参数/类型名/cast）
    token 序列不变 + 幂等 + linter 零诊断。
- **C 包 c23 小写拼写落地 + 修掉一条过期边界：`static_assert`（新增块作用域）、
  `alignas` / `alignof` / `thread_local`**。接受面 **34/36 → 35/37**；档位矩阵 17 → **21**。
  - **"同构造异拼写"的包内约定已定**（TODO 里"需先定约定"那条的答复）：
    **c23 侧各写一条同形规则**（先例 = `static_assert`），不做跨插件 token 引用、
    也不用 `inject_replace_rule` 去改别的插件的规则。理由：词法层 **token 类型由拼写决定**
    （`lexer/main_lexer.py::_full_map_keywords` 用 `keyword_type(拼写)`，`[id.keyword]` 的
    **键名只是可读名**）⇒"一个 token 类型两种拼写"在现役词法里表达不了；改别人规则的
    production 只有软路径（ROADMAP 注入分类的 ③ 类）。**代价**：同一构造两种拼写 =
    **两个节点名**（`AlignasConstSpec` vs `AlignasC23Spec`）——按构造匹配的分析器需同时认
    这两个名；判据守"宿主必须与 c11 版一致"（否则两拼写的可达位点会漂移）。
  - **宿主与 c11 版对齐**：`alignas` → `@TypeQualifier`（被 6 处说明符位共同引用，
    一次注入六处生效）、`alignof` → 两处原子清单（`@PrimaryExpr` / `@PostfixExpr`）、
    `thread_local` → `@StorageClass`。
  - ⚠ **过期边界作废（实测）**：`10_static_assert_alias.toml` 原写"块作用域不可用（需在核心
    `Stmt` 选择器加分支 → 属『改』核心，与其余增量同批待办）"——不成立，照 c11 的
    `_Static_assert` 加一行 `targets = ["@Stmt"]` 即可（含 `if` body 位，靠传播注入）。
  - **判据**：`test_c23_increment_plugin.py` 45 → 82 例（10 条新构造进 `_CASES` 的三组
    参数化：解析 / token 序列 + 幂等 / lint 零诊断；新增"小写拼写复用 c11 宿主"、
    "`static_assert` 块作用域靠注入"、注入目标清单扩到 9 个文件）；
    `test_c_standard_tiers.py` 矩阵 17 → 21 行（`static_assert` 块作用域 + 三个拼写）；
    `tools/c_acceptance.py` 36 → 37 条；13 个拼写形态 token 序列不变 + 幂等 + linter 零诊断。
- **C 包 c11 说明符位增量收口：`_Alignas` / `_Atomic` 落地——c11 的 6 个新关键字全部有规则**。
  接受面 **32/34 → 34/36**（空洞仍只剩预处理两项）；档位矩阵 11 → **17 构造 × 4 档**。
  - **`_Alignas`（§6.7.5）**：两条规则分别表达**常量表达式**与**类型名**两种实参形态
    （`AlignasConstSpec` / `AlignasTypeSpec`）；注入点 = `@TypeQualifier`——本包说明符位由
    6 条规则分别表达（`Declaration`/`SpecRest`/`FuncDef`/`MemberSpec`/`ParamSpec`/`TypeName`），
    而 `TypeQualifier` 被这 6 处共同引用 ⇒ **一次注入六处生效**。
  - **`_Atomic`（§6.7.2.4 / §6.7.3）**：两种形态（类型限定符 `_Atomic int x;` 与类型说明符
    `_Atomic(int) x;`）**写在一条规则里**（`AtomicSpec` = `_Atomic` + 可选组 `( type-name )`），
    同样挂 `@TypeQualifier`。
    ⚠ 本轮实测的**引擎性质**：选择器只在**同一元素内**换候选，**不跨元素/跨兄弟回溯**——
    拆成两条规则（单 token 限定符 + 4 元素说明符）时，`_Atomic(int) x;` 会先命中单 token
    那条、随后元素失败且**不回头** ⇒ 整条声明**空 AST**（渲染空串，比报错更难发现）。
    收进一条规则的**可选组**后，两种形态都在规则内部判定，不产生需要回溯的分岔
    ——与 ROADMAP「C 语义层切片 1b」里"候选路径是否收敛"是同一性质。
  - ⚠ **注入点选择有实测差异（A/B）**：其余条件相同、只换 `targets` 时，"6 处逐点注入"
    会让块作用域 `_Alignas(16) int x;` 折成两行、且**成员/参数/类型名三处空 AST**；改挂
    `TypeQualifier` 后四症全消。变量已隔离，引擎内部机制未追到底——处置原则记进包内头注：
    **优先找"被多处共同引用的那条规则"当宿主，别逐点铺**。
  - **判据**：`test_c_increment_plugin.py` 62 → 95 例（6 条增量进 `_C11_INCREMENTS` 的
    解析 / 逐字渲染 / 幂等 / lint 三组参数化 + 新 `TestC11SpecifierSlotIncrements`：
    9 条说明符位用例、**两形态同一 env 并存**、`_Alignas` 覆盖六处说明符位、核心基线文件
    不含增量名、注入目标可追）；`test_c_standard_tiers.py` 矩阵 11 → 17 行（4 项 + 2 条块作用域）；
    `tools/c_acceptance.py` 34 → 36 条。19 个说明符位形态（文件/块/成员/参数/类型名/cast）
    全部 **token 序列不变 + 逐字还原 + 幂等 + linter 零诊断**。
- **引擎级 `enabled=` 档位覆盖参数：同一个 pack 可在同一次进程内切档**
  （`ConfigRegistry.load_language` / `load_all` / `resolve` / `resolve_with_sources(..., enabled=[…])`；
  `None` = 用包内 `[plugins] enabled`，**不是**"沿用上次"）。此前"档位对照"只能靠 pack 副本；
  现在 `enabled=["c11"]` → `enabled=[]` 会把**词法扩展 + 配置声明**一起按档位重建。
  - **两处静默失效根因**（症状统一为"改了 `enabled` 毫无变化"，也是上一轮按逐处清单实施后
    以为没生效的原因）：① `_ensure_entries_for` 的判据只有 `rules_dir`——同包切档直接复用
    上一档 `_entries`（含 `[lexer] token_ext`）；改为 `(_entries_source, _entries_enabled)`
    二元组。② `_resolve_cache` 的 key 无档位——同包两档声明不同却算同一个 key，
    `Lexer` / 数字形态拿到上一档配置；key 里加 `tier`。
  - **隐式消费方自动跟随**：显式档位在 `load_language` / `load_all` 时**登记**为该包"当前
    档位"，故 `resolve(pack)`（`Lexer` 走它）无需额外参数即按该档解析；未曾 load 过的包
    回退到包内清单。
  - **fail-fast 两条**：`enabled` 必须是字符串列表（非列表 / 含空串 / 含非字符串 →
    `ConfigError`）；清单里的插件名**必须能解析到插件包**——此前是**静默跳过**（拼错一个
    名字就少加载一个插件，"启用组合等效某标准"直接失真）。
  - **判据**：`tests/languages/c/test_c_standard_tiers.py` 的 **26 构造 × 4 档矩阵**
    （`enabled=[]` / `["c11"]` / `["c11","c17"]` / `["c11","c17","c23"]`，按**解析成哪个节点**
    判定——比"规则表里有没有"更能抓出缓存串档）+ 同进程连续切档 + `Lexer` 跟随档位 +
    `enabled=None` 回落到包默认 + 非法参数 fail-fast；`tools/check_gate_efficacy.py` 增两条
    变异（删档位比较、删 `_resolve_cache` 的 tier key，逐条实测变红）。
  - **边界（不是 bug，已落档 `TODO.md`）**：`enabled` 只门控**声明面**；插件的**规则文件与
    Python 组件**由 `setup_grammar` → `load_all_components` 加载、**不看** `enabled`。
    C 包插件是纯 TOML、c4 插件是纯 Python（且 c4 包**没有** `[plugins]` 段），两条路径当前
    恰好正交——语义边界与两种候选语义（只门控声明面 / 门控一切）见该条。

- **C 标准增量插件：c11 补 4 项、c23 补 6 项语法面；并更正"这类增量做不了"的旧判断**。
  接受面 **26/28 → 32/34**（空洞仍只剩预处理两项）。落地方式**全是"声明的注入"**
  （`[ExtRule.inject] targets = […]`），核心基线文件**一行未动**：

  | 插件 | 新增 | 注入点 |
  |---|---|---|
  | c11 | `_Static_assert` **块作用域** | `@Stmt`（此前只支持文件作用域） |
  | c11 | `_Alignof` / `_Generic` | 两处原子清单（`@PrimaryExpr` / `@PostfixExpr`） |
  | c11 | `_Noreturn` / `_Thread_local` | `@FuncSpec` / `@StorageClass` |
  | c23 | `nullptr` / `true`·`false` | 两处原子清单 |
  | c23 | `bool` / `typeof`·`typeof_unqual` | `@SimpleType`（最窄注入点：**一次注入，声明/成员/参数/类型名四处生效**） |
  | c23 | `constexpr` | `@StorageClass` |

  - **旧判断作废（本轮实测）**：c11/c23 插件头注与 ROADMAP 都写着这些增量"要往既有规则
    的交替里塞分支，而现役 `grammar_inject` 只能做 production 的字符串子串补丁（且软失败），
    所以做不了，需引擎补『改』路径"。**两条都不成立**：`inject_productions` 的直接注入
    就是**树层** `insert_choice_candidate`（把 `@ExtRule` 作为候选并进目标 production 的
    交替），且 fail-fast——机制早在，缺的只是插件没写那几行声明。ROADMAP 该条已按实测
    收窄为"**仍缺的是『改/删一支』**（`inject_replace_rule` 仍是软失败的子串补丁），
    触发条件 = 出现真正需要改既有分支的标准演进"。
  - **两条形态坑（都被 fail-fast 当场拦下，已写进包内注释与 README）**：① `production`
    是**一条产生式的元素序列**（列表长度 = slot 数、`$N` 按元素下标），不是"多条备选
    产生式"——备选要在**同一元素内**用 `|`；② 裸交替与逗号同现时 `|` **先结合**
    （`"a|b, X"` = `choice[a,(b,X)]`，不是 `(a|b),X`）。
  - **判据**：`tests/languages/c/test_c_increment_plugin.py`（13 → 45 例：含
    "原候选一支不少且序不变""注入来源可追（TOML 里声明，核心文件不含增量名）"
    "原子增量必须注进**两处**原子清单"）+ 新 `tests/languages/c/test_c23_increment_plugin.py`
    （45 例：13 条构造 × 解析/渲染 token 序列/幂等/lint + 注入点 + 档位判别）；
    `test_c_standard_tiers.py` 增"**块作用域**随档位变"（基线档当普通调用、c11 档进插件节点）；
    `tools/c_acceptance.py` 增 6 条增量用例（28 → 34 条）。
  - **顺带更正的过期文档**：`grammar/c/README.md`（接受面数字、标准增量清单、未做表改为
    真正剩余项）、c11 `_token_ext.toml`/`tpc.toml` 与 c23 `tpc.toml` 头注、ROADMAP
    标准增量条与注入条、缺口档「增量插件形态实测」第 3 点（`[plugins] enabled` **是**
    运行时启用清单——2026-09-25 曾记为"打包面装饰"，实测更正）。
  - 另记一条**渲染偏差**（本轮实测，非本次改动引入）：类型名里的指针星号与类型词之间
    不留空格（`sizeof(char *)` → `sizeof(char*)`、`(char *)q` → `(char*)q`）——
    `CastTypeName` 布局的旧注释写的与实测不符，已更正；纯排版差异（token 序列不变），
    记入缺口档渲染现状表 #7。

### Fixed

- **fuzz 回馈链路补齐后两步：自动最小化 + 自动沉淀**（作者 2026-09-26 指出"链路只差这两步"）。
  此前这两步是 `tests/fuzz/README.md`「迭代指南」里的**人工动作**（打开 findings → 手缩
  → 判定 → 修 → 沉淀 edge 回归）。现在四环闭环：

  ```
  run_fuzz.py（找）→ oracle.py（判据）→ shrink.py（缩 + 沉淀）→ run_edge.py（门禁）
  ```

  - **判据单一来源**（新 `tests/fuzz/oracle.py`）：六类违反（crash / silent-fail /
    tokenize-fail / token-corrupt / idem-crash / non-idempotent）从 `run_fuzz.py` 抽出，
    `run_fuzz` / `shrink` / `run_edge` 三方共用——最小化若换一套判据，缩出来的就不是
    原来那个 bug。
  - **最小化**（新 `tests/fuzz/shrink.py`）：ddmin（Zeller TSE 2002）分 pass 跑——
    行级块删除 + 保补集 → 尾截 → 去前导空行 → **行内字符级**（可选 token 级）。
    判据只比**类别**不比 detail（detail 含计数，会随收缩变化）。`--max-tests` 封顶，
    到顶如实报 `partial`。
  - **沉淀**：最小复现 + **溯源抬头**（判定 / fuzz 类别 / 原 finding / 尺寸 / 修复后
    必须成功或失败）写进 `edge_corpus/{clean,reject}/`，抬头里的**类别**从此成为该条
    语料的回归判据（`run_edge.py` 复检）。抬头生成**拒绝**留 `成因待补`。
  - **两处闸（时序决定，都实测过）**：① **未修不许沉淀**——类别仍复现则拒绝
    （写进去等于把缺陷固化成期望行为；判别性用例是 `success=True` 的非幂等样本，
    只按 clean/reject 判会一路写进 clean/）；② **已修不再最小化**——直接走沉淀
    （修好前版本的分岔缺失会让"带 --sediment 永远沉淀不了"）。
  - **链路语言包可指定**：`--pack` 一处驱动**生成器 / 词法 / 管线 / 种子**。此前
    `--rules-dir` 只作用于前两者、管线恒用默认包（"用 A 包生成、用 B 包格式化"，
    finding 全是假的），且 `collect_seeds` 只认 `.v`、`_content_pool` 里硬编码了
    一串 Verilog 关键字（既重复又把语言知识写进 harness）——均已修。**C 包由此获得
    fuzz 覆盖**（首轮 4000 轮 / 21 iter/s，0 findings）。
  - **门禁**：`tests/policy/test_fuzz_shrink.py`（ddmin 合成谓词单测 + 注入式假管线跑
    finding→缩→沉淀→抬头→复检的完整文件路径，19 例）、
    `tests/policy/test_edge_corpus_provenance.py`（抬头判定须与目录一致 / 类别须是已定义
    类别 / 不留"成因待补"；2026-09-26 起要求类别项，此前 4 条手工沉淀豁免——它们的失败
    模式当时还没有类别名，硬凑是造假）；`run_edge.py` 增 `--corpus/--pack/--ext` 与
    类别复检；`tools/check_gate_efficacy.py` 新增 3 条变异（逐条实测变红）。
  - **评估落档**：`docs/references.md`「测试输入最小化与回归沉淀」——ddmin（直接采用 🔥）、
    Hypothesis（缩减对象是**选择序列** + **失败用例库**，对应本仓的 findings 索引与 edge
    语料 🔥）、C-Reduce/afl-tmin（pass 化 + 两档判据 + 预算报 partial 🔥）、Perses
    （语法引导缩减：**评估后不实现**，写明三条理由与触发条件 📌）。
  - **实测（真实路径）**：C 包注释折行漂移个案
    `intrst/* x×60 */,second;`（86→81 字节、单行，判据 184 次、1-minimal）——行级无事可做，
    真正可缩的是**注释长度（折行阈值 60）**；因缺陷未修，沉淀**如期被拒**。该最小复现已
    写进 `TODO.md` 对应条目（可复现的最小输入 + 阈值 + 进入方式）。

### Fixed

- **lexer 最长匹配要求「每一层中间前缀自身也是声明过的符号」→ 中间形态未声明的符号
  永远匹配不到**（`lexer/main_lexer.py::_scan_symbol`）：C 的变参 `...` 要经过未声明的
  `..`，于是被降级成三个 `.`——`int printf(const char *fmt, ...);` 整条解析失败、
  linter 还报 2 条误报（`unexpected '('` / `expected ';', got 'keyword.const'`），
  即**真实工程头文件里最常见的形态被合法代码检查链拒绝**。
  该缺陷早已被两处"绕过"记录在案：yaml 与 verilog 各自声明了一个
  `double_dot = ".."`（yaml 的注释写明"中间形态，无独立语义，仅为 `...` 的 probe 链"）
  ——本修点落地后两处占位声明已按"删除先证后删"删除（判据：其存在理由即喂 probe 链；
  无规则/测试引用；`..` 在两种语言里都不是符号）。
  改为按**声明集取最长**、用真前缀集决定是否继续探（未声明前缀只前进不采纳，
  探完回退到最长已声明候选）。判据：`tests/engine/lexer/test_lexer.py::TestSymbolLongestMatch`
  （自建 token 表，不依赖语言包）+ 全量回归 + 真实语料误报基线不增。

- **C 包支持变参尾段 `...`**（`int printf(const char *fmt, ...);`）——接受面
  **25/28 → 26/28**，空洞只剩预处理两项。改法是纯配置：
  `ParamList` 第二项写成 `(symbol.base.comma,(@ParamDecl|symbol.extend.ellipsis))*`
  （尾段落重复组迭代项，`items` 绑定自然收进列表并按源序渲染）。
  ⚠ **这一项此前被记为"需引擎侧形态"的缺口（三种配置写法"全部证伪"）——结论是错的**，
  真根因两条、都不是形态问题：① 上面那条 lexer 缺陷；② 配置里 token 类型写成
  `symbol.base.ellipsis`，而 `ellipsis` 声明在 `[symbol.extend]` 下（完整类型
  `symbol.extend.ellipsis`），该元素因而永不匹配——症状与"形态表达不了"一模一样。
  两条修好后本形态是纯配置可达的。同时实测到一条易踩的坑：尾段若写成**独立可选元素**
  （`(comma,ellipsis)?` 单独一项）也能解析，但 `items` 绑定拿不到它 ⇒ 渲染**静默丢掉**
  `...`（输出 `int printf(const char *fmt);`）——"解析进 AST ≠ 保真"。
  判据：`tests/languages/c/test_c_declarations.py::TestVariadicParameter`（7 例：进 AST /
  尾段在 `ParamList.items` 里 / 对照非变参 / `int f(...);` 仍拒（C99 要求至少一个具名
  参数）/ linter 零诊断 / 渲染逐字还原 + 幂等），`tools/c_acceptance.py` 复核。

### Fixed（前一轮，linter 误报）

- **linter 在合法 C 上大面积误报的根因（不是"匹配器不回溯"）**：`grammar/c` 的
  `ring_buffer.h` / `ring_buffer.c` / `edge_comments.c` 三份**合法**样本上，linter 分别报
  **14 / 7 / 2 条** `phase-statement`，即合法代码 100% 被报错（检查链在最基础的头文件上
  不可用）。四条**引擎侧**近似缺陷、逐个独立可验证：

  1. **匹配器把"必选 call 零进展"当空匹配成功**（`linter/checkers/matcher.py` 的
     `_no_progress_ok`）：旧判据是"本次没新增错误"，于是失败的规则被**静默跳过**，
     后续元素在错位上继续匹配。实测链：`@StructOrUnion` 失败被跳过 → `StructSpecifier`
     把裸标识符当结构说明符吃掉 → `struct … { … };` 的成员 `int values[4];` 解不出 →
     整条声明报 `expected ';', got '{'`。改为**按目标规则的可空性**判定
     （production 可整体推导出空才允许零进展），并加规则级可空性缓存。
  2. **`_match_seq` 把"可空元素零进展"当整体失败**：单元素初始化列表解不出
     （`{.k = 0}` / `int a[4] = {1};` / `{ {1} }` 全报 `expected ';', got '{'`）；
     改为按同一可空性判据放行。
  3. **容器区间不含嵌套语句/块尾部**（`linter/discovery.py` 的 `_container_end`）：
     matcher 对 `@Stmt` / 具体语句规则按扁平化策略**不消费**（嵌套语句由独立 checker
     负责），故容器区间止于 body 之前，父 checker 反而在"production 仍有必选元素"处
     报 EOF 假红（`void f(void) { … }` 全中）。新增 `_stmt_tail_end` / `_stmt_extent`
     补算尾部；verilog 因容器都经 `@Stmt` 分派器（is_statement=false → 内联匹配）
     绕开了该形态，故此前未暴露。
  4. **`_advance_match` 对零进展元素做 `j + 1` 兜底**：body 起点被算到参数位
     （`void f(void)` 的 `(void)` 被当括号声明符解析），多注册一个假子节点并误报；
     改为返回真实匹配位置（调用方按 production 逐元素推进，循环有界，无死循环风险）。
     连带修出一个**静默漏检**：`_discover_bracket` 此前对"块规则"也走"整体跳过括号
     区间"，块内语句既不解析也不诊断——c4 的"块内缺分号"一度被发现，靠的正是
     `j + 1` 兜底把 body 起点错算到 `{` 之后一格（偶然生效）；现在改为**转块分支**
     （注册块节点 + 递归 body），c4 的块内检出从"偶然"变"必然"。

  验证：三份样本诊断 **14 / 7 / 2 → 0 / 0 / 0**；`tests/e2e/eval_lint_accuracy.py`
  recall 33/33、误报 0（不变）；`tests/e2e/eval_diag_baseline.py` 真实语料
  **5548 → 5548**（无增长）；`tests/engine/linter` + `tests/languages/{c,c4,yaml}`
  **620 passed**；全量 **2658 passed / 7 skipped**。
  门禁有效性：`tools/check_gate_efficacy.py` 新增 **4 条变异**（把每条修复改回旧行为
  ⇒ 期望的测试变红，逐条实测通过）；匹配器语义另有**最小合成树**单测
  （`test_linter_matcher.py::TestMatcherZeroProgressSemantics`，不依赖任何语言包）。

  顺带更正两处**过时归因**：① 旧缺口档把成因写成"匹配器严格逐 token 匹配**不回溯**、
  规则内部的可选分支不被尝试"——实测不符（可选分支**有**被尝试，真正的锅是"失败的
  必选 call 被静默跳过"），该档的 C 节已按"条目消失即删"清掉；② 旧档记的"机制 B：
  `enum` 开头返回空候选"在本包当前状态**不可复现**（`enum e { A, B };` 等 6 例候选均为
  `['Declaration']`、零诊断），一并删除。

  同时更新三处按"缺口登记"写的测试断言（缺口档纪律：缺口闭环后换成"零诊断"断言）：
  `test_c_corpus.py::test_linter_reports_no_false_positives`、
  `test_c_corpus_impl.py::test_linter_reports_no_false_positives`，以及一条过期的阶段
  边界断言（`test_function_body_is_not_supported_yet` → 阶段 3 已落地，改为"函数体
  合法 ⇒ 零诊断"）；另把 `a b;` 从"表达式错误"负样本移出——它在 C 里语法上是**声明**
  （typedef 名歧义，本包按既定分层宽进、真伪由语义层判），原先"报错"靠的正是上面第 1 条
  缺陷制造的假报。

- **新增已知边界（记 `TODO.md`，本轮未动）**：C 的块内诊断粒度粗——块内多个错误只报
  一条，且报文位置被后续元素带偏（实测 `void f(void) { a + ; b + ; }` → 1 条
  `expected 'bracket.r_curly_bracket', got 'id'`，指着 `b` 说"期望 `}`"，真错在
  `a + ;`；c4 同位样本 → 2 条精确诊断）。**两条候选修法都已实测过代价**：包侧把
  `CompoundStmt` 改成块规则会让块体语句改走引擎的规则选择器序（C 包里 `Declaration`
  在 `ExprStmt` 之前）⇒ `void f(void) { x; }` 的体内语句从 `ExprStmt` 变成
  `Declaration`，推翻本包刻意选定并锁进测试的消歧；引擎侧改 `_match_repeat` 的错误
  恢复则改变所有语言在坏输入上的诊断面。它不影响"合法代码零误报"（本轮已闭环），
  只是坏输入的诊断质量，故按"先落档后动手"记档待专用一轮。

- **收尾轮实测更正一处「接受面已闭环」的错觉：变参 `...` 从未支持**（本包文档此前把
  它写在「已落地」里）：

  - **怎么发现的**：发布冒烟顺手把文档里**声称支持**的形态逐条实测
    （`_drafts/probe_claims.py`），`int printf(const char *fmt, ...);` 当场解析失败
    （空 AST）。**不是靠读代码发现的**——这正是「断言必须实测」的价值。
  - **为什么一直没被发现（两处漏项叠加）**：① 阶段 2 的 TODO 枚举里没写它；
    ② 接受面盘点工具 `tools/c_acceptance.py` 的 27 条构造清单里**也没有变参用例**
    ⇒ 「空洞只剩预处理两项」在工具与文档之间**互相印证**。**专治「无声空洞」的工具
    自己有一个无声空洞**——工具的价值取决于清单，清单漏了就等于没量。
  - **补洞尝试（三种配置写法全部证伪，已落档）**：`ellipsis = "..."` token 本来就在
    `base/_token.toml`，缺口纯在 `ParamList` 形态上——① 尾随可选：`(comma,@ParamDecl)*`
    贪婪且**不回溯出中段**，重复组先吃掉 `,` 再在 `...` 上失败，可选项拿不到机会；
    ② 整条 production 写成两分支交替：单串交替被当成**一个 slot**，加载期
    `GrammarError`（`$2` 越界；fail-fast，无静默降级）；③ 交替放进重复组内部：
    重复组内的交替**不落穿**到第二支。⇒ 要支持需**引擎侧**形态（生产式匹配的回溯
    语义，或一个专收尾段的规则位），**不是本包配置能绕过的**；试验改动已按纪律
    **全部回退**（不留半成品）。
  - **改成什么**：工具清单补变参用例（27 → **28 条**，计数改为 **接受 25 / 空洞 3**）；
    缺口档新增「变参缺口的实锤」（三种写法的结果与根因表）+ 接受域表函数行拆出该缺口；
    `grammar/c/README.md` 把错误断言移出「已落地」、未做表补行；`TODO.md` 剩余能力面
    补该项。工具清单注释里落下**防漏纪律**：清单必须与缺口档接受域表**逐行对照**
    （表里有、清单无 ⇒ 漏项）。

  验证：`python tools/c_acceptance.py` → **接受 25 / 空洞 3（共 28）**，空洞逐条为
  `#include` / `#define` / 变参；`tests/languages/c` **322 passed**（本轮未改任何语法，
  只改盘点面与文档——**把"没做"写对，也是交付的一部分**）。

- **C 语义层首个切片 1a：强制转换 `(T)x` 与复合字面量 `(T){…}`（无歧义面）**，
  连带动了引擎一项能力（`pratt_level`）：

  - **范围（`ROADMAP.md`「C 语义层首个切片」切片 1a）**：只接受**类型关键字起头**的类型名
    （`CastTypeName`，**不含 `@TypedefName`**）——`(int)x` / `(unsigned long)y` /
    `(char *)p` / `(struct p *)q` / `(enum e)v` / `(int){1}` / `(struct p){1, 2}` /
    `(struct p){.x = 1}`。理由：类型关键字不可能起始表达式 → 与 `(expr)` 候选集**不交**，
    按 FIRST 集即可判定、**不需要符号表**。typedef 名起头（`(myint)x`）是真歧义
    （`(a)*b` 是乘法还是转换），留切片 1b（需符号表），草案与判据在 ROADMAP。
  - **引擎新能力 `[Rule.parser] pratt_level`**：pratt 入口的**优先级上限**——
    `"expression"`（默认，rbp=0，吃全部中缀）/ `"unary"`（起于 `max_infix_prio`，
    不吃中缀）；取值非法即 ConfigError。语义与用途见
    `parser/expression_conventions.md` §7。**加性**：未声明的规则行为零变化。
  - **⚠ 过程中实测出两处 `sizeof` 实现偏差并修正**（都与"操作数不该吞中缀/转换"同族）：
    ① `sizeof a * b` 原解析成 `sizeof (a*b)`（应 `(sizeof a) * b`——`sizeof` 与一元同级）；
    ② 引入 `CastExpr` 后 `sizeof(int) * n` 被原子**最长匹配**判成 `sizeof((int) * n)`
    （应 `(sizeof(int)) * n`——标准 6.5.3.4 规定括号内是类型名即按类型名形式解析）。
    修法 = `pratt_level = "unary"`（`UnaryLevelExpr`）+ `sizeof` 操作数改**有序分派**
    （`SizeofOperand`：先试括号类型名 → 后缀 → 一元层级）。

  验证：`test_c_expressions.py` 新增 `TestCastAndCompoundLiteral`（19 例：8 转换形态 +
  嵌套 + 一元优先级 + 作操作数 + 4 复合字面量 + **4 对照负样本**（`(a)*b` 等不得判成转换）
  + 1b 边界 `(myint)x` 仍被拒）与 `TestSizeofPrecedence`（6 例：两处偏差各带判据）；
  引擎侧 `test_pratt_parser.py::TestPrattLevel`（4 例）+
  `test_rule_schema.py`（`pratt_level` 合法字段/缺省）；反向守用例按纪律**转正向**
  （`TestCastIsNotSupportedYet` 删除）。`tools/c_acceptance.py`：
  **接受 23 → 25 / 空洞 4 → 2**（只剩预处理两项）；**全量 2618 passed / 7 skipped**。

- **前导点浮点：`[[number.based]] lead_dot` 键**（引擎数字 schema 扩一项；C 包消费）：

  - 语义：该形态额外接受**以小数点开头**的浮点（C99 §6.4.4.3 `fractional-constant` 的
    `digit-sequence? . digit-sequence` 分支）：`.5` / `.25` / `.5e3` / `.5E-3` / `.5f`。
  - **点后必须有数字**：`.` 本身仍归符号表（`a.b` / `p.b.c` 的成员访问不受影响）；
    "已吃点未吃数字"的状态**不是**接受态，故 `.` 不会变成 `literal.number`。
  - 声明面 fail-fast：非布尔、或声明在**有前缀**形态上（小数点没有"开头"位置）即报错。
  - **lexer 侧"先试数字扫描"只对显式声明的形态生效**（`starts_at_declared_non_digit`）：
    ⚠ 实测教训——先按"任何声明的起始字符都先试"实现，结果 yaml 的 `yaml_neg`
    （`-` 前缀形态）把序列指示符 `- 8080` 的 `-` 变成 `literal.number`（**18 处 yaml
    测试变红**）。故 C 的 `.5` 必须显式表态，未表态的形态行为零变化。
  - 顺带发现（已记档）：**yaml 的 `yaml_neg` 从未生效**——lexer 只在数字字符上进入
    数字扫描，`-5` 一直是 `symbol.base.minus` + `5`；该形态是不可达声明，待处理。

  验证：`tests/engine/lexer/test_number_suffix.py` 新增 `TestLeadDotConfig`（5 例，含
  两处 fail-fast）与 `TestLeadDotConsumption`（5 例，含 **`.`/`.b` 不吃** 的判据样本、
  含"未声明 lead_dot 的 `-` 形态不得进入先试路径"的 gated 反例）；C 侧
  `test_c_lexer.py::TestNumberForms` 扩到 24 例（含 `.5*` 4 例 + 成员访问对照），并把
  「前导点浮点」从 `TestRecordedLexicalGaps` 反向守**转为正向**——**该类已随最后一条
  缺口消失而删除**（三条缺口全部闭环）。`tools/c_acceptance.py`：
  **接受 22 → 23 / 空洞 5 → 4**（剩余空洞：强制转换、复合字面量 = 语义层；
  预处理两项 = 阶段 4）；**全量 2586 passed / 7 skipped**（本轮前 2568）。

- **C 包逗号运算符：`CommaExpr` + `FullExpr` 选择器（ISO C99 §6.5.17）**：

  - 形状：逗号**刻意不进 pratt 运算符表**——pratt 中缀项在任何 pratt 规则里都按整张表
    解析，`,` 一旦入表，`f(a, b)` 的实参分隔、`int a = 1, b` 的声明符分隔、
    `enum {A, B}` 的枚举项分隔、`int a[n], b` 的长度分隔**全被当成运算符吞掉**
    （实测：枚举体 3 项塌成 1 项）。故走**语法形态**：`CommaExpr`（显式 `,` 分隔 +
    逐项 pratt 子表达式）+ `FullExpr` 内联选择器（`@CommaExpr|@Expression`）。
  - **分层照标准**：只在标准允许 `expression` 的位点引 `@FullExpr`（表达式语句 /
    `return` 值 / `if`·`while`·`do`·`switch` 条件 / `for` 三段 / `( )` / `[ ]`）；
    分隔符位点（实参表 / 初始化器 / 数组长度 / 枚举值与位宽 / `case` 值）继续引
    `@Expression`——对应的正是标准的 assignment-expression / constant-expression 层级。
  - **无逗号不套壳**：`FullExpr` 的选择器让普通表达式仍返回 `Expression` 本体，只有真
    含逗号才出现 `CommaExpr`（若写成 `(...)*` 可选，每个表达式语句/条件/括号都会多一层，
    全局 AST 形状变脸——与 `PostfixExpr` 用 `+` 避开裸原子是同一取舍）。
  - 参照：`docs/references.md`「C 语言文法参照」新增第 4 节（标准分层 +
    tree-sitter-c 的 `comma_expression` 分立；并记一处本包**照标准、比 tree-sitter-c 宽**：
    下标 `[ expression ]` 允许逗号）。

  连带记录：`StructMember` 补一条**已知边界**——逐声明符位宽写不出来
  （`int a : 3, b : 4;` 解析失败，包内宽度绑在整个成员声明后），单声明符位域与匿名
  占位可用（记在包注释 + 缺口档接受域表）。

  验证：`tests/languages/c/test_c_expressions.py` 新增 `TestCommaExpr`（9 例：括号/语句/
  return/for 三段/四类条件/下标/三项/各项是完整表达式/**无逗号不套壳**）+
  `TestCommaSeparatorsNotSwallowed`（6 例：实参·声明符表·枚举体·初始化器·`case` 值·
  数组长度各自不塌）；`tools/c_acceptance.py`：**接受 21 → 22 / 空洞 6 → 5**；
  **全量 2551 passed / 7 skipped**（linter `phase-*` 缺口数保持 7——选择器没有扰动
  原子路径，与上一轮 `AtomExpr` 的教训对照）。

- **字符串/字符常量的段内转义：`[string] escape` 键**（引擎捕获层扩一项；C/c4/verilog 消费）：

  - 声明面：`[string] delimiters = ['"', "'"]` + `escape = "\\"`（可选**单字符**，段级；
    `[[capture]]` 条目同样可声明）。多字符转义（YAML 单引号的 `''` 双写）是**另一机制**，
    `_one_char` fail-fast 并注明，不硬塞本键。
  - 语义：捕获范围内 `<escape><任意字符>` 整体并入内容、**不参与终止判定**——
    `"say \"hi\""` 不再在 `\"` 处提前收尾（后续文本被切成新 token）；`\` + 换行按
    C99 §5.1.1.2 行拼接并入同一 token（调用方按内容里的换行记账行号，跨行捕获已支持）。
  - **不声明 = 无转义语义**（既有行为逐字不变）→ 加性扩展；yaml 因此**不动**
    （它的单引号转义是双写机制，双引号转义缺口仍在档）。
  - 参照：`docs/references.md`「C 语言文法参照」新增第 3 节（ISO C99 §6.4.4.4/§5.1.1.2 +
    tree-sitter-c 的 `string_literal`/`escape_sequence`：成熟实现都把转义放**捕获层**，
    而非留给后续阶段）。真实代码命中率高：`printf("say \"hi\"")` 这类必撞。

  验证：引擎门禁 `tests/engine/lexer/test_capture_runner.py::TestRunDelimEscape` **8 例**
  （转义收尾 / 转义反斜杠 / 转义符在结尾 / 转义换行 / **不声明即旧行为**对照 / 多字符
  fail-fast / `[[capture]]` 段同样支持）；C 词法 `TestEscapes` 补 5 例 + 行拼接与裸引号
  对照；反向守用例按纪律**转正向**（`TestRecordedLexicalGaps` 里"转义引号让捕获中断"
  删除）。`tools/c_acceptance.py`：**接受 20 → 21 / 空洞 7 → 6**。样本
  `ring_buffer.c` 加一条 `"say \"hi\""` 声明（`_TOP` 重记）；**全量 2551 passed / 7 skipped**
  （本轮前 2536）。三包（verilog/c4/c）声明 escape 后**零回归**——e2e 真实语料与
  差分门禁全绿。

- **C 包后缀链：`PostfixExpr{base, suffixes}`（链式后缀，ISO C99 §6.5.2）**：

  - 形状：旧实现是三个**单级**规则（`CallExpr` 的 base 只能是 `@Identifier`、`IndexExpr`
    用组量词勉强支持 `a[i][j]`、`MemberExpr` 单级），故 `a.b.c` / `f(x)[i]` / `p->a[i]` /
    `(*fp)(x)` 都不支持（旧测试把它们钉成"应报错"）。现按标准的六形态改为
    **原子 + 后缀+**：`PostfixExpr{base, suffixes}` + `IndexSuffix` / `CallSuffix` /
    `MemberSuffix`——与 clang 手写路径同形（先解析 leading part，再循环吃后缀，
    `ParsePostfixExpressionSuffix`）。三个旧规则与布局**已删**（不留并存）。
  - 两处引擎侧机制在实现中暴露并写进包注释（都是**取错就静默丢内容/整块失败**的坑）：
    ① **FOLLOW 由引用推出来**——`PostfixExpr` 若不被任何规则引用，其派生 FOLLOW 只剩
    pratt 注入的运算符族，`switch (p->key)` / `if (a.b)` 这类**后随 `)`** 的形态被 FOLLOW
    硬检查拦掉（实测 `ring_buffer.c` 的 `ring_scan` 整函数解析失败）；
    ② `+` 量词产生的是 **`plus` 包装节点**，而 normalizer 只消 `optional/repeat/seq`
    （`transform/normalizer.py::ELIMINATE_TYPES`）——直接绑 `$2` 会拿到无布局的包装节点、
    后缀静默渲染成空（实测 `r->head = 0;` 渲成 `r = 0;`，**token 序列判据当场抓到**）。
  - 另两处形状约束（记在包注释里防重踩）：链的 head 不能用含 pratt 入口的
    `PrimaryExpr`（`PostfixExpr → PrimaryExpr → UnaryExpr →` pratt 原子路径 → 回到
    `PostfixExpr` 会无限递归，实测每步撞 `maximum recursion depth exceeded`）；
    后缀用 `+` 而非 `*`（裸原子不该被包成链——`atomic_rules` 按 production 数降序、
    等长取先试者，`*` 会让 `x` 变成 `PostfixExpr(base=Identifier, [])`，全局 AST 变脸）。
  - 参照：`docs/references.md` 新增「C 语言文法参照」（ISO C99 §6.5.2 / clang
    `ParsePostfixExpressionSuffix` / tree-sitter-c 的 `prec` 与后缀规则），含借鉴点与
    "不实现 GLR 消歧"的理由。
  - 样本随能力**长回**自然写法：`samples/ring_buffer.c` 用 `r->items[i].key` 三级链并
    与头文件签名对齐（9 个函数）；保真度 **0.9907 → 0.9925 且有效行 117 = 源 117**。

  验证：`test_c_postfix.py` 重写为 **28 例**（链形/链长/嵌套/上下文/负样本；旧的
  "链式后缀应报错"用例按纪律转正向）；`tools/c_acceptance.py` **接受 18 → 20 / 空洞 9 → 7**；
  linter `phase-*` 缺口数**保持 7**（中途加过一层 `AtomExpr` 间接，实测在 `sizeof` 初值处
  多误报 1 条 → 7→8，故撤掉该间接、把原子清单写在两处并注明）；**全量 2536 passed / 7 skipped**。

- **C 包接受面盘点工具（`tools/c_acceptance.py`）——「空洞是无声的」**：27 条构造
  （词法 / 声明 / 类型 / 语句 / 表达式 / 预处理 / 增量）逐条试解析，报「进 AST /
  空 AST / 词法抛错」并给接受-空洞计数（`--only-gaps` 只看空洞）。动机与
  `render_coverage.py` 同源：**不属任何语句入口 FIRST 集的构造会被整体跳过、
  既不解析也不诊断**——只跑测试套件看不出还差哪一族。C 包的强制转换 / 复合字面量 /
  链式后缀 / 转义引号**都是这么量出来的**，不是靠想。

  工具首跑：接受 **18 / 空洞 9**，直接定出后续补洞清单（每补一族就重记一次计数，
  所以本节多条条目都带「接受 → 空洞」的迁移数字）。

  验证：工具按**构造清单**驱动（27 条，逐条给判据：进 AST 即接受）；清单口径与
  逐条状态记 `docs/gaps/gap-language-pack-scope.md`「C99 接受域清单」。

- **字面量尾随后缀：`[[number.based]] suffix` 键**（引擎 schema 扩一项；C 包消费）：

  - 声明面：`suffix = { chars = "uUlL", max = 2 }`——**可选后缀字符集 + 长度上限**。
    形态非法（非表 / 空字符集 / `max < 1` / `max` 类型错）**fail-fast**，不静默降级。
  - 实现取向：后缀是 **DFA 之后的声明式尾段**，由 `number_runner` 在最新接受位之后
    消费；**不做成 DFA 转移**——字符→类别映射是全局的，而 `f`/`F` 已是十六进制 digit
    类别（`hex_value_abc`），按类别加后缀边会与 hex 值自环**撞键**（覆盖后十六进制
    数字解析崩）。门禁用 `0x1FF` 把这条判据钉死。未声明 `suffix` 的形态（verilog）
    行为逐字不变。
  - C 包补上 C99 §6.4.4.1 的整型/浮点后缀：`42u` / `10L` / `1ULL` / `1LLU` /
    `0xFFu` / `017UL` / `1.5f` / `1e3L`。此前被切成"数字 + 标识符"（`[[number.based]]`
    没有后缀位），是 C 真实代码里遍地都是的形态。
  - **组合合法性不在词法层判定**（`1UL` 合法、`1ff` 非法）——C 的 pp-number 本就宽进，
    约束归语义层；与本包"语法层只判'这是一个数字 token'"的既有口径一致。
  - 反向守用例按纪律**转正向**：`tests/languages/c/test_c_lexer.py::TestRecordedLexicalGaps`
    里的"整型后缀仍被切开"4 例删除，改为 `TestNumberForms` 的 21 例正向断言。

  验证：新增 `tests/engine/lexer/test_number_suffix.py` **26 例**（声明面 9 + 消费面 17，
  含 `0x1FF` 撞键判据、`max` 封顶、未声明形态零变化）；C 词法改写为 21 例正向断言
  （原 4 例"仍被切开"的反向守删除）；**缺陷态变异复验**（删掉 `_consume_suffix` 调用 →
  32 例变红 → 还原）。**全量 2521 passed / 7 skipped**。

- **C99 函数说明符 `inline` 与 `_Complex`——两处接受面空洞**（由草稿探针
  `_drafts/scan_c_gaps.py`（25 条常见 C99 构造逐条试解析）量出，非推测；该探针后来升为
  正式工具 `tools/c_acceptance.py`）：`inline` 缺席说明符规则——C99 §6.7.4 的**函数
  说明符**是与存储类 / 类型限定符**并列的第三类**，而 `static inline int f(void)` 在真实
  C 头文件里极常见；`_Complex` 缺席基础类型表。两处症状相同——**整条声明被整体跳过**
  （关键字不入任何语句入口 FIRST 集 ⇒ 出空 AST，既不解析也不诊断）。

  一处刻意的宽度选择：`FuncSpec` 只接 `Declaration` / `FuncDef` 的说明符位，**不接**
  `MemberSpec` / `ParamSpec`——`struct { inline int x; }` 是**语法错误**而非"语义约束"，
  不该留给语义层兜（与 `@TypedefName` 的宽进口径不同）。

  验证：`tests/languages/c/test_c_declarations.py::TestC99Specifiers` 3 例，断言
  **规则身份**而非"没报错"（`FuncSpec` 进 AST / `static` 在前、`inline` 进 rest /
  `_Complex` 进 rest）；同批仍不支持的 7 条逐条记入缺口档接受域清单
  （整数后缀 / 前导点浮点 / 转义引号 / 强制转换 / 链式后缀 / 逗号运算符 / 复合字面量
  ——**这就是后续补洞清单的来源**）。

- **C 包声明渲染风格：页宽 80 列**（`grammar/c/base/_style.toml` + `[renderer] style`）：
  此前用引擎默认 40 列（`renderer/loader.py` 的兜底值），把正常声明与调用折成多行
  ——`int ring_pop(struct ring_item *items, unsigned int head, …)` 被拆成 5 行。
  页宽是渲染页宽（Doc IR 布局的宽度预算），C 社区惯例 80 列（K&R / Linux / LLVM）。
  连带清单同步：`[engine] uses` 补 `renderer.doc_ir.v1`（`[renderer]` 段由能力清单
  机械推导，门禁 `tests/policy/test_engine_capabilities.py` 查漏声明——协商机制在起作用）。
  实测（三样本 `difflib`）：`ring_buffer.h` 0.9842 → **0.9926**（有效行 33 = 源 33）、
  `ring_buffer.c` 0.9867 → **0.9907**、`edge_comments.c` 0.9822（持平）。
  验证：C 包 231 passed；**全量 2477 passed / 7 skipped**。

- **`when` 布局原语 + 保真度判据 7（token 序列）**（承接同轮 C 包保真度闭环）：

  - **`when` 属性分发布局**（`renderer/primitives/when.py`）：同一节点名承载多形态时
    按属性值选支——`when = { attr, eq|ne|in|startswith|exists }` + `then`/`else`
    两支（可省）。此前布局原语没有"按属性值换序"能力，只能二选一。
  - **修 C 包语义级缺陷**：pratt `UnaryOp` 前缀/后缀同名（`position` 区分），
    旧布局固定前缀序 → `i++`/`p--` 被渲成 `++i`/`--p`（token 齐全但**顺序反了**；
    C 里 `i++` 与 `++i` 语义不同）。改用 `when` 后前缀/后缀各取一支。
  - **判据 7：显著 token 序列逐项相同**（`(type, content)`，trivia 与注释除外）——
    内容级对拍，比 `difflib` 强得多：`i++`→`++i` 只差 3 个字符（比值 0.99+），
    difflib 与行数判据都抓不到，序列判据一眼看出。样本 `ring_buffer.c` 本就含 6 处
    `i++`/`p++`——**旧判据一直是绿的**，正是本判据补的盲区。
  - **认不出的布局键改为 fail-fast**（`renderer/primitives/__init__.py::eval_expr`）：
    此前静默返回 None → 整块布局**无声消失**（"缺布局静默丢内容"的同一根因），
    现直接报 `ConfigError` 并点名牌出的键与已知原语。全量测试证明现有四包无一处
    依赖旧行为（零回归）。`when` 的声明形态非法同样 fail-fast。
  - 配套：`tools/config_sites.py` 词汇表补 `when` 的键（`then/else/eq/ne/in/exists`），
    门禁 `tests/policy/test_config_sites.py` 复绿。

  验证：新增引擎门禁 **11 条**（`TestWhenPrimitive` 8 + `TestUnknownPrimitiveKeyFailsFast` 3）；
  C 包闭环 **20 → 29 例**（判据 7 token 序列 6 例 + 后缀序 3 例）；`when` 的缺陷态变异
  复验（把 C 包 `UnaryOp` 布局改回固定前缀序 → `TestTokenSequence` 与 `TestPostfixOrder`
  变红 → 还原）。样本再记录：`ring_buffer.c` 0.9780 → **0.9867**（`i++` 修好的直接结果）。
  **全量 2474 passed / 7 skipped**（判据 7 与 `when` 之前是 2457）。

### Fixed

- **渲染/解析：注释落位四处缺陷**（在 C 包保真度闭环上暴露，**成因都在引擎**，非语言包）：

  1. **列表项前的独占行注释整条丢失**：首注释由 `_claim_head_comments` 领到行首规则的
     **最内层**节点（列表项以标识符开头时是项内的 `Identifier`），join 取用端只认项自身
     `sub_node` 首位 → 注释静默丢弃（实测 `enum e { // c` + 首项丢掉整条）。取用端改为沿
     项**首脊线**下钻（`renderer/primitives/join.py::_hoist_head_comments`）。
  2. **多条首注释顺序倒置**：`_insert_gap_comments` 按行升序遍历却逐条 `insert(0, …)`
     → 注释进 AST 就是倒序，渲染出「后一行在前」；产物再解析又回到源序 ⇒ 不幂等。
     改为整段前插（`subs[:0] = nodes`）。
  3. **分隔符后的行中注释多一个空格**：join 组装在注释后又补 `Text(" ")`，与紧随的
     SoftLine 叠加 → `int a, /* mid */  b;`（flat 双空格；broken 形态则是行尾空白），
     二次渲染逐字不同。verilog 端口表同缺陷（`input wire clk, /* port comment */ `）。
     删去该补格（间距由 SoftLine 给）。
  4. **硬拼列表（`join=""`）首项即注释时注释粘在代码上**：`_asm_comment_item` 把
     「换行分隔」与「硬拼」混为一谈，硬拼列表首项即注释时不补首 Break → `//` 注释随即
     吞掉后续片段（实测 `int f(\n// c\nint a);` → `int f// c` + 换行 + `(int a);`，二次
     渲染整段被吃进注释 ⇒ **输出非法 C**）。补首 Break。

  验证：新增引擎门禁 4 条（`tests/engine/renderer/test_renderer_primitives.py::
  TestJoinCommentPlacementRegressions`）；C 包保真度闭环加**注释清单**与**首注释源序**
  两条判据（`tests/languages/c/test_c_render_fidelity.py` 18 → 20 例），样本
  `samples/edge_comments.c` 扩入枚举体首项前独占注释与声明符间行中块注释。
  四条门禁**逐条做缺陷态变异复验**（改回缺陷 → 对应门变红 → 还原）。
  **全量 2452 passed / 7 skipped**（与改动前持平，无回归）。

- **C 包保真度渲染闭环（原文打印的起点）**：先量出「缺布局是无声的」——引擎对
  无渲染配置的规则**静默输出空串**，故加 `tools/render_coverage.py`（某包多少条
  规则带 `layout`/`body`、哪些没有，附 node 字段与叶子 / 非叶子标记便于从叶子补起）。
  实测本包 **70 条规则 / 1 条有渲染配置（1%）**，两样本全渲染为空串。

  补齐后闭环成立（`tests/languages/c/test_c_render_fidelity.py`，3 个样本
  `ring_buffer.h` / `ring_buffer.c` / `edge_comments.c`）：源文本 → tokenize → parse
  → render → 与源比对，判据逐条加硬——**非空**（缺配置时静默空串，只断言「没报错」
  抓不到）→ **行数覆盖 ≥ 80%** → **`difflib` ≥ 0.80** → **幂等** → **注释清单**
  （源里**每一条**注释正文都必须在输出里出现——比抽样锚点强，能抓「某一条被静默
  吞掉」）→ **首注释源序**（只守幂等时「倒序但恰好往返一致」的实现仍可能漏过）。

  实测：覆盖率 **1% → 100%**（分母 70 → 80 是因为补了真规则 `Comment`、pratt 产物
  `BinaryOp`/`UnaryOp`/`TernaryOp` 与 6 个 `bracket.*` token 节点——后两类**不补布局
  就静默丢内容**，实测 `a[i]` 会渲染成 `ai`）；两样本 ratio 0.984 / 0.978，
  有效行数与源一致。⚠ **分母变大必须给理由**——补的是真节点，不是把阈值调绿。

- **C 包标准增量插件族三档齐备（c11 ⊂ c17 ⊂ c23）+ 档位对照实测**：这是 ROADMAP
  「核心基线 + 标准增量插件」形态的**首次落地验证**，也是「按版本号做增量插件」
  这一设想的可执行证据（**零引擎新机制**）。

  - `plugins/c11/`：`_Static_assert`（C11 §6.7.4，文件与块作用域均合法）+ **C11 全部**
    新关键字的词法声明（`_Generic`/`_Alignas`/`_Alignof`/`_Noreturn`/`_Thread_local`/
    `_Atomic`；规则只引用已落地子集，未引用的关键字会被 linter 当「未期望 token」
    ——**这正是负样本判据**）。
  - `plugins/c17/`：**不带语法文件**——C17 是缺陷修正版，相对 C11 无新增语法。
    「有的标准只贡献包含关系、不贡献语法面」这条反例就此落进包结构。
  - `plugins/c23/`：小写 `static_assert` 正式关键字化（N3096 §6.4.1）——
    **只靠插件自己**即可加（文件作用域语句规则 + `is_statement`，不动核心 `Stmt`
    选替）。需要「改」核心规则的那一类（`typeof`/`constexpr`/`[[属性]]`/`nullptr`）
    **明确未做**并写明原因，前置是 ROADMAP「注入机制：四类注入面，按需实现」（③/④）。
  - **包含关系在加载期可执行**：组件级 `requires`（c23→c17→c11→核心基线）——
    只启用 c17 而不启用 c11 会**响亮失败**，而不是静默少加载。本插件是**组件级
    requires 的首个实例**（此前只有 `[[analyzer.postpasses]]` 链内时点依赖用过）。
  - ⚠ **一处自我更正**：曾记「运行时没有启用入口、`[plugins] enabled` 只是打包面
    清单」——**该结论已被实测推翻**：加 `enabled = ["c11"]` 之前 `_Static_assert`
    是标识符（`_Static_assert(1, "x");` 解析成函数调用 `ExprStmt`，插件规则永不
    匹配），加之后即 `keyword._Static_assert` → `StaticAssertDecl`；对照证据是
    verilog 的 `nand` 无需任何 `ext_dirs` 就是关键字（其 `enabled` 列了 `gates`）。
    真正的入口 = `load_language` 时按 `enabled` 合并声明；`Lexer(ext_dirs=…)` 与
    `setup_grammar(ext_dirs=…)` 三种粒度**实测都无效**。

  验证：`test_c_increment_plugin.py` 按**扫描文件**的方式守「增量确实住在插件里、
  不碰基座」（`StaticAssertDecl` 不出现在核心基线 `0*_*.toml`）；
  `test_c_standard_tiers.py` 三档对照——同进程内三档各自可加载并解析出不同规则表，
  且「**未声明关键字 ≠ 拒绝**」（C23 关键字在 c99 档下仍可作标识符）。
  ⚠ 档位对照**当时**靠 **pack 副本**（引擎级 `enabled` 覆盖参数按逐处清单实施后**档位未按
  预期切换**，未经验证的改动已全部回退）。该参数已于 2026-09-26 落地并验证（见
  `[Unreleased]`）——两处静默失效点都是**缓存键**（`_ensure_entries_for` 只比目录、
  `_resolve` 的 key 无档位），各自都须含档位；归因与判据见
  `docs/gaps/gap-language-pack-scope.md`「运行时档位入口已落地」。

- **C 包真实语料：从声明面扩到实现面（并暴露三处真问题，各自登记而非绕过）**：
  `samples/ring_buffer.h`（声明面）+ `samples/ring_buffer.c`（实现面：控制流 /
  表达式 / 调用 / 指示符初始化 / `sizeof`），样本随能力**长回自然写法**——
  **不为了让测试好过而裁剪代码**。三个副产品都是真问题：

  - **跨语言检查规则泄漏**（可复现）：同一进程里**先跑过 verilog linter**，再
    `load_language("grammar/c")` 扫 C 源，结果多出 1 条 `ST003`（verilog 检查规则
    残留；C 包自身无 `rules/`）。症状 = **检查结果依赖测试顺序**。当前由反向守
    用例钉住（修复后该用例会失败并提醒复核文档），属 `core/global_state` 面。
  - **C 包 linter 误报归因**（合法头文件上 17 条误报，**解析侧正常**）：定位到两个
    **不同**机制——① `linter/checkers/matcher.py::_match_token` 严格逐 token 匹配
    **不回溯**，规则内部的可选分支（如 `StructSpecifier` 的 `@StructBody?`）不被
    尝试（覆盖 `{`/`[`/`(` 三类 15 条）；② `lookahead.classify()` 对 `enum` 开头
    返回空候选 → `discovery._record_unrecognized`（2 条）。
  - **两处语法缺口**：语料一上实现面就撞出来并修（不是靠推想），缺口数逐轮重记。

  验证：`test_c_corpus.py` / `test_c_corpus_impl.py`（真实语料 + linter 缺口反向守）；
  归因、修点与包侧兜底见 `docs/gaps/gap-parser-linter-approximation.md`。

- **C 包阶段 2b：初始化器 / 位域 / 数组长度常量表达式 / `for` 声明式初值 /
  `sizeof` / 指示符初始化**（C99 相对 C89 的新增面集中在这一段）：

  - 初始化器：标量表达式 + **递归初始化列表**（`{1, {2, 3}}`）；
  - **指示符初始化**（designated initializer，C99 §6.7.8）：`.field =` 与 `[i] =`；
  - 数组长度改吃**常量表达式**（此前只接受数字字面量）；
  - `for (int i = 0; …)` 声明式初值（C99 §6.8.5.3）；
  - 位域（`int a : 3;`）——⚠ **已知边界**：**逐声明符位宽**写不出来
    （`int a : 3, b : 4;` 解析失败），包内宽度绑在整个成员声明之后；标准里位宽属
    **声明符**，要支持需把宽度挪进声明符（形态改动）。记在
    `grammar/c/02_types.toml::StructMember` 注释 + 缺口档接受域表；
  - `sizeof` 两形态（`sizeof expr` / `sizeof(T)`）——⚠ 当时**记了「强制转换未支持」**，
    该反向守用例已随切片 1a 按纪律**转正向**（守缺口的用例不许在能力落地后继续绿）。

  验证：`test_c_expressions.py`（`TestSizeof*`）、`test_c_types.py`（位域与边界）、
  `test_c_statements.py`、`test_c_declarations.py` 逐族扩例；
  `tools/c_acceptance.py` 同步重记接受面。

- **C 包词法收官：浮点可用 + 三处配置表达力缺口记档**：接上浮点字面量后，词法面
  暴露**三条「配置表达不了」**的缺口——整型 / 浮点**后缀**（`42u` / `1ULL` / `1.5f`）、
  **前导点浮点**（`.5`）、字符串内**转义引号**（`"say \"hi\""`）。当轮只**记档**
  （每条都写清「为什么现机制表达不了」），随后三条**全部闭环**（各补一个声明键，
  见本节上方三条条目与缺口档表）——这就是「缺口先落档、再按档闭环」的走法。

  验证：`tests/languages/c/test_c_lexer.py`；缺口档
  `docs/gaps/gap-language-pack-scope.md`「C 包词法面：三条配置表达力缺口（已全部
  闭环）」。

- **C 包阶段 3 全层级（Layer A/B/B2/C）——表达式与语句族落地**：

  - **Layer A**：原子（`Number`/`StringLiteral`/`Identifier`/`ParenthesizedExpr`）
    + 选择器 `PrimaryExpr` + 表达式入口 + 最小语句（compound / 表达式 / 空 / `return`）
    + `FuncDef`（原型与定义靠 `{` vs `;` 区分）；
  - **Layer B**：运算符表 `base/_operator.toml`（40 项，C99 §6.5 优先级 / 结合性 /
    一元位置；**有意不含逗号运算符**——它在实参表与枚举体里是分隔符）+ `UnaryExpr`
    （前缀 first set）；
  - **Layer B2**：后缀链（另见本节上方 `PostfixExpr` 条目）；
  - **Layer C**：控制流全族（`if`/`else`/`switch`/`case`/`default`/`while`/`do`/`for`/
    `goto`/标号/`break`/`continue`/`return`），`Stmt` 选替扩到 15 分支。

  ✅ **关键形态约束（已记入 `grammar/c/00_expressions.toml` 头注）**：表达式环必须
  **同时**满足 ① 原子 `is_atom = true`；② 入口规则 `pratt = true`；③ 选择器
  `inline = true` 且 production 为**单条交替**——缺任一项即 `setup_grammar` 报
  `RecursionError`（FIRST/nullable 推导遇环溢出）。本条是**一次失败换来的**：
  上一轮委派尝试正是缺这些标记而失败（产物停在草稿区），照 c4 验证过的形态重做后
  **一次通过**。

  验证：`test_c_statements.py` 14 例 + `test_c_control_flow.py` 19 例（断言结构与
  **顺序**，不只「能解析」）+ `test_c_expressions.py` 22 例（断言**树形**：乘高于加、
  加减高于移位、相等高于按位与、`&&` 高于 `||`、赋值右结合、减法左结合、
  6 前缀 + 2 后缀一元、三目嵌赋值——只断言「解析成功」抓不到优先级错）。

- **功能散点治理（0.1.3 WS2）四步——从「度量先行」到「定案建 ADR」**：议题是「一处
  功能、N 处登记 + 上游契约耦合」。四步都按「先拿数字再收敛」走，**不先发明机制**：

  - **步 1 度量**：`tools/feature_sites.py` 按功能分族（加检查规则 / 语法构造 / 能力位 /
    配置键）枚举现存实例、扫出提及它的文件并按角色归类。判据**不是「文件多」**，而是
    **同一事实被写在 ≥2 个必须手工同步的位置**（测试 / 文档不计欠账）。四族基线：
    `check` 24 实例 / 散点 **56**（中位 2、最大 5）、`syntax` 7 / **0**、
    `capability` 3 / **30**（中位 9、最大 15 = formatter）、`config` 14 / **26**。
    **结论直接定出步 2 目标**：check 族的散点是同一批 6 个文件被每条规则反复登记
    → 由 `check_registry` 单一来源派生或校验。
  - **步 2 试点收敛**：单一来源提取抽成 `tests/_rule_codes.py`（两门禁共用一份实现），
    新增 `tests/policy/test_code_registry_sync.py` 校验变异注入器 / 评测基准映射 /
    真实语料基线的码引用；收敛账 `tools/feature_sites_converged.json` 须 reason+source
    指向门禁，并有**反向防滥用**门禁（路径真实存在、source 门禁存在、不得空转登记）。
    **预算 56 → 16**（中位 2→1、最大 5→3）；散文类登记为**有意接受的边界**。
  - **步 2b 变异门禁自校验**：`tests/policy/test_gate_efficacy_mutations.py`——每条
    变异载荷必须**仍可应用**（锚点漂了就红）。动机：门禁的「有效性抽查」若载荷本身
    已失效，抽查会静默变成空转（**门禁不该假装有效**）；同轮去掉一处码枚举。
  - **步 3 契约协商（P-C）**：`[engine].uses` 能力清单 + `core/engine_capabilities.py`
    能力表 + **精确缺项报错**（报「缺哪一项」而非「整条 API 线不匹配」）；旧的整条
    `api` 线**已删**（残留由「未知键」拦下）。`uses` 由包清单机械推导，门禁查漏
    声明 / 残留；**加性扩展不误伤**未被声明的能力（协商语义有专门用例）。
  - **步 4 定案建 ADR**：`docs/decisions/0020-feature-scatter-governance.md`
    （D1 度量先行 / D2 单一来源 / D3 校验·派生·接受三分 / D4 契约版本化到能力粒度 /
    D5 不留兼容且收敛声明可审计 / D6 断言分工 + **被拒绝的 5 个备选** + 三步验证证据），
    机制文档 `core/config_lifecycle.md` 与 `core/component_protocol.md` 同步。

  验证：`tests/policy/test_feature_sites.py`（判保持登记可审计，含反向防滥用）、
  `tests/policy/test_code_registry_sync.py`、`tests/policy/test_gate_efficacy_mutations.py`、
  `tests/policy/test_engine_capabilities.py`、`tests/engine/core/test_engine_compat.py`。
  ⚠ **未做完的**（留在 `TODO.md`「步 2」）：`eval_check_accuracy.py` docstring 枚举、
  `_check_test.py`、`check_gate_efficacy.py` 接同一门禁。

- **C 包阶段 1 与阶段 2a + 阶段 0 定界**（`grammar/c/` 从零到可解析声明）：

  - **阶段 0 定界**：分层草案 + **C99 接受域清单**（27 条逐条标注做 / 不做 / 延后）
    落 `docs/gaps/gap-language-pack-scope.md`——不先定界就开工，「还差哪一族」会失焦。
    结论之一：第一个可验收切片 = **词法 + 类型与声明符**（声明符递归是后续一切的
    地基，其形态决定 AST 形状），而不是「先把全部词法做完」。
  - **阶段 1**：`tpc.toml`（能力清单 + lexer/parser 入口）+ `base/_token.toml` /
    `_lexer.toml` / `_number.toml` + `token.toml`（**C99 全 37 关键字**）+
    `00_expressions.toml`（叶子 `Identifier`）+ `01_declarations.toml`（翻译单元 +
    声明 + 说明符序列 + 声明符：多级指针 / 数组 / 函数后缀 / 括号声明符 / 参数表）。
    ⚠ **根因教训（写包必看）**：`Identifier` 这类叶子规则**引擎不内置**，语言包必须
    自带（c4 / yaml / verilog 各一份）。漏定义时 `@Identifier` **匹配为空**，症状是
    `match_length 0` / `expected ';' got 'id'`——**看起来像规则形态问题**；本轮为此
    先后证伪了**五个形态假设**（带括号 token 组 / 说明符层级 / 后缀规则组 / 首元素带
    量词组 / `@Rule|@Rule` 交替）才定位到「规则缺失」。已入缺口档「包作者须知」。
  - **阶段 2a**：`02_types.toml`——`struct`/`union`（带标签与匿名）、`enum`（含带值
    枚举项）、成员声明、**typedef 名作类型**。两条实测坑：① **token 键重复定义**
    （`equal = "="` 与 `assign = "="` 同串两键，词法取后者 ⇒ 所有引用
    `symbol.base.equal` 的规则**静默失配**，报错方向完全看不出是命名问题）；
    ② **字面量正则过度转义**（TOML 里多转义一层，`\d` 变成字面反斜杠 + `d` ⇒
    数字**从不**被识别为 `literal.number`）——因当时数组长度与枚举值都写成可选，
    症状是「静默为空」而非报错：**可选位点会掩盖词法失效**，加可选捕获要配一条
    非空断言。

  验证：`test_c_declarations.py` 20 passed（正样本 15 含函数指针递归 `int (*fp)(int);`、
  逗号列表、多词说明符、`typedef`；负样本 5）、`test_c_types.py` 12 例。

## [0.1.2] - 2026-10-25

### Fixed

- **直出切片与注释槽双吐同一条行尾注释（每遍加倍、不收敛）**——fuzz 报的非幂等，实为
  渲染缺陷：语句含宏 ⇒ 挂 `_verbatim_text` = 该语句**展开切片原文**，而切片末尾**就含
  行尾注释**；同一条注释又在 `_comment_slots['trailing']` 里（**裸 str**）。
  `_render_verbatim` 按"附着注释在节点 span 之外"的假设把槽也输出 ⇒ 一条注释出两份；
  下一遍切片里已含两份 ⇒ **每遍加倍**（实测 `// i-type` 4→6→10、注释总数 731→733→737）。
  修法：**直出文本权威**——切片里已含的注释不再由槽输出，切片之外的槽照旧输出。
  判据见 `tests/engine/renderer/test_verbatim_node.py`（含"切片外仍输出"的对照）。
- **Python ≤3.13 上导入即 `NameError`**：`preprocessor/_expand.py` 与 `parser/_production.py`
  的注解用了**未导入**的 `Any`——本机 Python 3.14 的惰性注解（PEP 649）掩盖了它，而
  `requires-python = ">=3.11"` 与 CI 矩阵（3.11/3.12/3.13）会在 def/class 创建时立即求值。
  补导入并新增门禁 `tests/policy/test_eager_annotations.py`（此类缺陷本地 3.14 结构性测不出）。
- **`_fits_fixed_len` 读 `Text.s`（字段实为 `text`）⇒ `_fits` 遇含 `Text` 的 `Concat` 抛
  `AttributeError`**：重构 `3b9b113` 把原 `case Text(s): col += len(s)`（**位置捕获模式**）
  机械抽成谓词时把模式变量名当成了属性名。`layout` 主路径走 `_flat_w` 缓存、很少直接问
  `_fits`，故夹具与真实语料都没抓到。补 `TestFitsFixedWidthPath` 回归判据。
- **`check_hardcode --strict-doc`（R3）假红**：该规则只扫"文件前 2000 字符"，而
  `core/global_state.py` 的 `Doc:` 在**字符偏移 2597**（约定位置是"docstring 末行"）⇒
  合规文件永久红。改为按模块 docstring 判定（保留前 2000 字符作兼容退路）；另补
  `analyzer/elaboration/__init__.py` 真缺的 `Doc:`。
- **测试基础设施三处**（全新检出/同文件系统/CI 才现形）：① 3 个精化测试读 gitignore 的
  e2e 生成物 `samples/normal/gen/*.v` ⇒ 改指受版本控制的 `ref/` 同名样本；
  ② `check_test_isolation._normalize_id` 跨盘抛 `ValueError` 且仓外路径归一不到一起 ⇒
  补跨盘守卫 + 仓外压 basename（始终保留 `::用例名`）；③ `_abs_target` 只按"仓库根 + 目标
  目录"直拼，而同盘时 pytest 的 rootdir 是**共同祖先**（Linux 为 `/`）⇒ 支持逐级向上解析。

### Added

- **`tools/ci_rehearsal.py`：本地排练 `ci.yml` 全部门禁**（发布/打标前一条命令自查）——
  9 步（主回归+覆盖率 / 乱序 smoke / 两条 policy / pyright strict / edge / fuzz / CLI /
  wheel 安装冒烟），结论三态 **PASS / FAIL / INCOMPLETE**：**SKIP 与"一步都没跑"都不算绿**。
  ⚠ `ci.yml` 的触发是 `push.branches` + `pull_request`，**推 tag 不触发 CI**；本批 449 个
  提交从未推送 ⇒ 门禁从未运行 ⇒ 静默漂移到 4 类红（本轮逐项清零，见上）。

### Changed

- **P3-②c-3（上）：`param_override` 共享项落地 + 逐项对拍（ADR-0019）**：把各检查原先
  **各自一份**的"实例化点覆盖后参数表"合并逻辑上提为共享产物。

  - 新增项 `param_override`（`file` 作用域，`depends_on = ["param_default", "connections"]`）：
    `{文件路径: [{inst_name, module_name, inst_node, params, changed}]}`——三层合并
    **调用者参数（本文件各单元合并）→ 目标单元默认 → site 覆盖**；`changed` = 存在
    "覆盖值 ≠ 目标默认值"的项。
  - **与 `width_check` 自己的合并逐项对拍通过**：字面量覆盖下 `params` 与 `changed`
    全等；不空转（真实夹具里 `W` 由默认 4 变 16、`changed=True`）。
  - ⚠ **探明一处技法差异（迁移消费方前必须处理）**：`width_check._override_params` 用
    **自带的 `node_text` 渲染器**取覆盖值文本，本项用**服务渲染器**——字面量逐字一致，
    **表达式**覆盖（`#(.W(4*4))`）可能只差空白。数值等价，但 `_override_changes_params`
    的**文本比较**可能随之变脸。测试显式钉住"**去空白后一致**"这条不变量（连去空白都
    不一致即说明是语义差异而非技法差异，必须查清）。
  - ⚠ 本项的性质是**去重共享**，不是"把语言知识搬出引擎"——那段合并今天本来就在插件侧
    （`width_check` / `hier_check` 各一份），引擎里没有对应实现（ADR-0019 决策 4 更正节）。
    故**不影响终态判据**（`ROLES` 早已归零）。
  - **只新增**（消费方仍用各自那份）→ 行为零变化；删除消费方重复逻辑待做（先处理上面
    那个差异）。

  验证：新测试 **4 passed**；`tests/engine/analyzer` **328 passed**；`-m smoke`
  **424 passed**；`tests/policy` **125 passed**（含诊断基线门禁持平）；
  **全量 2189 passed / 7 skipped**；探针 **新变绿 4 项 / ✓ 无回归**（纯加性）。

- **P3-②c-2：端口提取迁出引擎 → 终态达成（`ROLES` 归零，ADR-0019）**：引擎侧最后一块
  语言知识（端口形态）清空，**引擎不再消费任何插件产物**。

  1. **c-2a 消费方迁移**（`b3a8521`）：3 个端口消费方改读精化产物 `port_decls`——
     `width_check`（位置连接按**声明序**取端口值 / 具名连接 / 宽度文本 / 目标模块宽度表）、
     `inst_check`（W102 端口存在性 / WC001 死值 / W104 未连接端口）、`hier_check`
     （层次端口宽度）；`latch_check` **不碰端口**（实测）。共用
     `_shared.port_table(context, unit_name)` 一份助手（含"插入序 = 声明序"的说明）。
     ⚠ 踩坑：`port.name`（f-string 里的诊断文案）不在"语义属性"grep 清单里 →
     `AttributeError`，由 8 个测试当场抓到——**迁形状时要搜所有属性访问，不只语义属性**。
  2. **c-2b 删引擎侧**（本批）：`_ModulePort` / `ModuleInfo.ports` / `_PortFields` /
     `ModuleExtractor` 的 ports 族（198 行）；`[structure]` 的端口/连接/赋值/过程/body
     声明**全部删除**（引擎只剩读 4 个标量 + 3 个方向集 + 1 个字段，并在文件里列明
     "已迁出、别搬回"）；`ROLE_UNIT_PORTS` 与 `ROLE_GEN_ACTIVITY` 退场（后者因层 3 已删、
     `ctx.gen_activity` 只剩写入无读取）→ **`ROLES` 为空**。
     `StructureCtx` 随之只剩 `memo` / `module_index` / `dir_module_files`；`ModuleInfo`
     只剩 `name` / `file` / `node`（**语言无关三项**）。
     ⚠ 踩坑：按锚点删 `ModuleExtractor` 方法族时，**多行签名的闭合行与 `def` 同缩进**，
     把"按缩进找块尾"骗到 → 留下半截签名（`SyntaxError`）→ 回滚后改用"**先跳过签名**
     再找块尾"的脚本（与"装饰器必须同块"并列为切块的两个陷阱）。

  **验证**：`tests/engine/analyzer` **324 passed**；`-m smoke` **423 passed**；
  `tests/policy` **125 passed**（含**诊断基线门禁持平**——端口换源后 W201/W102/W103/
  W104/WC001 逐项一致）；**全量 2185 passed / 7 skipped**；`tools/config_sites.py check`
  **PASS**（删声明后引擎读取面与语言包声明仍一致）。探针 3 项"回归"经 `--collect-only`
  核实**正是被删/改名的 3 个测试 id**（2 删 + 1 改名）→ 基线按"差异已逐条解释"重记（1184）。
  终态判据由测试机器守：`test_roles_are_empty_at_terminal_state`。

### Added

- **P3-②b：层 3 信号图移植进插件 + 逐条目对拍（ADR-0019）**：新增项 `signal_graph`
  （`scope = project`，`role = unit_signal_graph`）——`SignalGraphBuilder`（400 行 /
  22 方法）**逐字搬迁**到新文件 `grammar/verilog/plugins/elaboration/_graph.py`，算法不动。

  - **只换数据来源**：实例连接读自身产物 `connections`、端口方向读 `port_decls`、
    generate 活性读 `gen_activity`（三者经 `depends_on`，**插件内流通、不经引擎中转**）；
    文件/单元改经**服务面**（本次新开的 `files()` / `unit_node()` / `unit_file()`）；
    声明值（`AssignStmt` / `BlockingAssign` / `NonBlockingAssign` / `AlwaysStmt` /
    `InitialStmt` / 目标字段 / 方向集）由插件持有。**图形状保持不变**
    （`{(单元, 信号): {drivers, loads}}`，消费方迁移才是机械的）。
  - **对拍**：7 个夹具（6 个**专为信号图设计**的 `W105_*` / `W104_*` 样例 + 真实语料
    `gen_generate.v`）**逐条目一致**；并断言**不空转**——多驱动与 output **穿透**真的发生
    （驱动源里同时有 `file:assign#N` 与实例路径形态）、负载侧非空。
  - ⚠ 缺 `depends_on` 任一项结果就会与引擎不同——故本对拍同时验证依赖通道把三个自身
    产物按序备好了。
  - 分文件（`_graph.py` vs `_elaborator.py`）是刻意的：不让单文件过大（结构预算），
    且层 3 能单独对拍。
  - **顺带**：精化服务面扩展 `files` / `unit_node` / `unit_file`（语言无关面；层 3 的
    驱动穿透要按单元名取子树与定义文件）+ 3 例测试（含"`render` 确实**转交**引擎助手
    而非自实现"）。

  验证：新测试 **10 passed**（服务面另 3 例）；`tests/engine/analyzer` **329 passed**；
  `-m smoke` **423 passed**；`tests/policy` **125 passed**（含诊断基线门禁持平）；
  **全量 2190 passed / 7 skipped**；探针 **1189 仍绿（+26）/ ✓ 无回归**。

### Changed

- **P3-②c-1：层 2/3 整块迁出引擎，两个角色位同时退场（ADR-0019）**：引擎不再做端口连接
  展开与信号驱动/负载图——它们都是语言知识。

  - **先迁消费方**（这是本步的关键顺序）：`inst_check` 是 `connections` 的**唯一**消费方
    （实测 `width_check` 只用 `inst_sites`，不碰 `connections`）→ 它对 `connections` /
    `signal_graph` 的读取改为**读产物容器**，用引擎给的 `CTX_ANALYZED_FILE` 取按文件切片。
  - **再删引擎实现**（净减约 **600 行**）：`ConnectionElaborator`（176）+
    `SignalGraphBuilder`（416）+ `_SignalGraphCtx` / `_graph_entry` / `_append_ref` /
    `_is_signal_expr` / `_SIGNAL_RE` / `PortConnection` / `FileResult.connections` /
    `StructureCtx.fr_by_module_cache`（随之成死字段）；`FilePipeline` 不再组合层 2；
    `ProjectChecker` 不再注入 `connections` / `signal_graph`（**不留双路径**）。
  - **角色位退场**：`ROLE_UNIT_CONNECTIONS` 与 `ROLE_UNIT_SIGNAL_GRAPH` 删除——
    引擎不再消费它们，postpass 直接读容器。`ROLES` 从 4 项收到 **2 项**
    （`gen_activity` / `unit_ports`）。插件侧两项也摘掉 `role` 声明。
  - **不变量**：`structure.py` 的模块头改为"**文件层**：单元索引 + 依赖发现"——
    引擎唯一可视单位 = 文件（`ModuleExtractor` 只剩名字/文件/声明节点）。

  ⚠ **实测踩坑（file-anatomy 陷阱 1 的实例）**：用锚点切 `_SignalGraphCtx` 时只切了
  `class ...` 行、**留下了它的 `@dataclass(frozen=True)` 装饰器**——于是那个装饰器转去
  装饰 `StructureCtx`，把会话上下文冻住（`FrozenInstanceError: cannot assign to field
  'rules_dir'`）。跑一次部件测试立刻抓到并修回。**教训：按锚点删代码块必须把装饰器
  一起锚进去。**

  **测试同批调整**：`test_checker.py::TestElaborationConnections` 删除（主体随实现消失；
  覆盖由 `test_elaboration_connections.py` 承担）；层 3 直连测试改读产物容器；两个对拍
  测试退化为"**产物行为守卫 + 退场守卫**"（引擎侧类/属性不得复活——机器守"不留双路径"）。

  **验证**：全量 **2187 passed / 7 skipped**，其中 `tests/policy` **125 passed**——含
  **诊断基线门禁持平**，即 W104/W105 诊断与删除前**逐项一致**（这是 `inst_check` 换源
  正确性的关键证据）；`tests/engine/analyzer` **326 passed**；`-m smoke` **423 passed**。
  探针：5 项"回归"经 `--collect-only` 核实**正是被删/改名的 5 个测试 id**
  （4 删 + 1 改名），非行为回归 → 基线按"差异已逐条解释"重记（1186 仍绿）。

- **修复：精化产物原子键冲突**取先**——同名单元跨文件错配（ADR-0019 P3-②b 前置）**：
  产物按**原子键**（unit 作用域 = 单元名）归位，驱动器原为**后写覆盖**；而引擎
  `module_index` 是"**首个**定义者优先"。于是**同名单元在多个文件重复定义**时两边指向
  **不同文件**——引擎按单元名取参数表/端口表会拿到另一个定义的值，跨文件检查**静默错判**。
  该口径差自 P2 起就存在（夹具单元名唯一，未暴露），但 P3-② 切换后会从"潜伏"变"必然"，
  故先修：`_accept` 归位改 `setdefault`（**取先**，与 `module_index` 同口径；对 file /
  project 作用域是 no-op），口径写入契约模块头。
  守卫两层：**驱动器级**（同一原子键两份产物 → 取先）+ **跨文件集成级**（两文件都定义
  `dup`，断言 `module_index["dup"].file` 与 `param_default` / `port_decls` 两个产物都指向
  同一份定义）。验证：analyzer **316 passed**；全量 **2177 passed / 7 skipped**；
  探针 **1176 仍绿 / 无回归**。

- **P3-②b-prep：层 2 连接展开移植进插件 + 逐文件对拍（ADR-0019）**：新增项 `connections`
  （`scope = file`，`role = unit_connections`）——与引擎
  `ConnectionElaborator.elaborate_connections` **逐字对齐**：**命名连接** `.p(sig)` 进
  `connects[端口名]`，其余项按出现序进 `ordered`（值 = 连接表达式渲染文本）。

  - **只新增、无人消费**：引擎 `FileResult.connections` 仍在原位、仍是层 3 与 postpass 的
    输入。本阶段意义是与引擎产物**逐文件对拍**——夹具覆盖命名 / 位置 / **命名但值为空
    （`.a()`）** 三种连接形态，并断言"不空转"（三种形态都真的抽到）。
  - ✅ **排除一个时序风险**（结论：不存在）：引擎的层 2 是在**发现过程中逐文件**算的
    （`FilePipeline.parse_file` 内调），而精化 pass 在**发现之后**统一跑——若层 2 依赖
    `module_index`（彼时只填了一部分），搬迁后结果就会不同。实测读码：
    `elaborate_connections` **完全不读端口表**（不用 `module_index`/ports），只读**声明
    字段**（实例名 / 连接字段 / 端口名 / 值）并把表达式渲染成文本 → **无时序问题**。
    （这正是"先读码再动手"省下的一次返工——该风险若成立，P3-②b 的方案要重做。）
  - 登记引擎角色位 `unit_connections`（引擎**尚未切换**；声明面前置登记是 P3-②b 的前置）。

  验证：新测试 **5 passed**；`tests/engine/analyzer` **314 passed**；`-m smoke`
  **422 passed**；`tests/policy` **125 passed**（含诊断基线门禁持平）；
  **全量 2175 passed / 7 skipped**；探针 **1174 仍绿（+11）/ ✓ 无回归**。

- **P3-②a ports 抽取移植进插件 + 逐端口对拍（ADR-0019）**：新增项 `port_decls`
  （`scope = unit`，`role = unit_ports`）——三种声明形态合并（**ANSI 头部** /
  **裸名头部** / **体内旧式声明回填**，同名**头部优先**），与引擎
  `ModuleExtractor._fill_ports` **逐字对齐**（含"回填只补空字段"、"body 声明不带网络
  类型"、"跳过函数/任务子树"——后者是 2026-08-29 修过的 tv80 假阳性根因）。

  - **只新增、无人消费**：引擎侧 `ModuleInfo.ports` 仍在原位、仍是层 2/3 的输入。
    本阶段的存在意义是与引擎产物做**逐端口等价性对拍**——两个夹具：
    `gen_generate.v`（ANSI 头部，含参数化宽度与 `wire` 网络类型）与
    `EX001_non_ansi_header/top.sv`（裸名头部 + 体内 `input a;` → 走**回填**路径）。
  - 插件内 `_declarators_of` 并入 `_decl_name_nodes`（参数与端口共用"两层 `items` 取
    声明符"逻辑，避免结构重复族新增）。
  - 登记引擎角色位 `unit_ports`（形状 = `{端口名: {name, direction, width_expr,
    net_type, decl_node}}`）——引擎**尚未切换**；声明面前置登记是 P3-②b 的前置零件。
  - ✅ 顺带核实一条**终态判据**：**"收口时 `ROLES` 为空"可达**——引擎的**文件发现**
    阶段（`ModuleIndexer`）只用**声明**（单元/实例规则名、名字字段、扩展名、关键字）+
    通用 AST 操作（"取声明种类的节点"），**不需要任何插件产物**；故决策 1 的"引擎按
    语言包给出的单元名去找文件"**不引入新角色**。
  - ⚠ 记一个**待处理差异**（P3-②b 必须处理）：产物按**原子键（单元名）**归位，同名单元
    在多个文件重复定义时"**最后一个**原子赢"；而引擎 `module_index` 是"**首个**定义者
    优先"。当前夹具单元名唯一，故未暴露——但切换后层 2/3 按单元名取端口表会取错文件。

  验证：新测试 **6 passed**；`tests/engine/analyzer` **309 passed**；`-m smoke`
  **421 passed**；`tests/policy` **125 passed**（含诊断基线门禁持平）；
  **全量 2170 passed / 7 skipped**；探针 **1169 仍绿（+6）/ ✓ 无回归**。

- **P3-① gen 族迁出引擎（ADR-0019）：generate 条件求值归语言包**：引擎不再求值
  generate 条件，也不再声明它的形态。

  1. **P3-①a 移植**（`d8944bd`，只新增不接线）：插件项 `gen_activity`
     （`scope = file`，`role = gen_activity`，`depends_on = ["param_default"]`）+
     求解器——**逐字搬迁** `GenerateEvaluator` + `_GenFace` + 文本常量求值链。
     单元常量经 `ctx.products["param_default"]` 读，**不经引擎中转**（`depends_on`
     通道至此才真正被用上）。**与引擎旧实现逐节点对拍通过**后才动删除。
  2. **P3-①b 切换 + 删除**：`SignalGraphBuilder` 经**引擎角色位** `gen_activity` 取产物
     （`_in_active_generate`；产物缺失 → 视作全活跃，保守不过滤）；引擎侧
     `GenerateEvaluator` / `_GenFace` / `_tokenize_const` / `_ConstExprParser` /
     `_eval_const_expr` / `_CONST_TOK_RE` / `_CMP_OPS` / `StructureCtx.gen_face()` /
     `unit_constants` 字段与 `StructureCtx.refresh()` 的形态校验——**同批删除**；
     `[structure]` 的 3 个 gen 标量 + 3 个 gen 字段声明一并删除；
     `ROLE_UNIT_CONSTANTS` **退场**（现役角色只剩 `gen_activity`）。
     净减引擎侧约 **390 行**语言知识。

  **⚠ 搬迁未改技法**（据实记）：那条链仍是**文本模式**求值（先渲染条件子树再解析
  文本）——AST-first 改写的动机因此从"消除渗透"变为"插件代码质量"，作为**独立改进项**
  保留（需自己一套验证，故**不在搬迁里顺手改**）。TODO 相应改写。

  **测试**（`tests/engine/analyzer/test_elaboration_gen_activity.py`）：
  - 对拍用**两个夹具**——真实语料 `gen_generate.v`（generate-for + if/else）与可判合成
    夹具（裸参数 `if (EN)`）。**为什么必须两类**：求值器只认裸参数名 / 纯数字 / 纯常量
    表达式，**参数名与运算符混排**（`DATA_WIDTH > 8`）一律不可判 → 全 True；
    只用真实语料时"参数表丢失"与"正常"**都是全 True**，判据退化成**假等价**
    （第一版就这么写的，被"不空转"断言当场抓到）。
  - 已知边界锁 + 退场守卫（`GenerateEvaluator` 等**不得复活**、`[structure]` gen 声明为
    空、`unit_constants` 角色为 None）。
  - `test_gen_face.py` **删除**（其主体 = 引擎声明面，已不存在）；其中与**求值语义**
    有关的用例（literal / 参数真值 / `!` 前缀 / 常量算式中性子集）与
    `test_analyzer.py::TestConstExprEval` **整体搬迁**到插件侧测试，**覆盖不减**。

- **最小语言包探针：区分"真回归"与"测试重组"（用出来的缺陷）**：一次测试搬迁让探针报
  **27 进 / 27 出**（总数不变）——逐条核对全是自己挪的测试（删 `test_gen_face.py`、
  搬 `TestConstExprEval`），**引擎行为零变化**。处置：`_report` 增加**按模块聚合**
  （先看"回归"是否整块落在少数模块、且同名测试出现在"新变绿"里）；工具文档写明
  **基线与"测试 id 集合"绑定**——测试增删改名也会表现为成对差异，故测试重组后必须重记
  基线，且**重记前要能逐条解释差异**（解释不了就别重记，否则等于把真回归洗掉）。
  基线已按此重记并复跑验证（**1163 / 1163 逐项相同，✓ 无回归**）。

- **P3 开工：搬迁顺序更正 + 协议前置零件（ADR-0019）**：P3 按原计划"**按事实**分族"
  （ports → connections → gen → signal graph）开工时，清点引擎内部消费关系发现**该切法
  不成立**——除 gen 外，每个事实（`ports` / `inst_sites` / `connections`）的消费者都是
  **同一个簇**：`ConnectionElaborator`（层 2）+ `SignalGraphBuilder`（层 3）。而这个簇
  本身也在搬迁名单上，按事实切就会在每一步为**注定要消失的消费者**造临时 role
  （会堆到 3 个，全是脚手架）。

  实测依据（`grep in_active_generate` / `module_index` / `\.ports` / `inst_sites`）：
  `in_active_generate` 的调用点**全部在 `SignalGraphBuilder` 内**（5 处）→ 只有 **gen**
  能用**一个** role 桥接成立。故改**按消费簇**切：
  ① **gen 族**（消费簇只有层 3）② **层 2 + 层 3 + ports 一次性**（消费者是彼此）。
  终态判据 = **`ROLES` 为空**（引擎不消费任何插件产物）——可机械检查。已回写
  ADR-0019 P3 节与 `TODO.md`。

  同批落 P3-①的**前置零件**（**只新增不接线**，为让下一轮只剩"搬逻辑"）：
  - 登记 `ROLE_GEN_ACTIVITY`（寻址键 = **文件路径**，形状 = `{id(节点): bool}`）；
  - **放宽 role 的 `scope` 约束**（原要求 `role ⇒ scope == unit`，是把 `unit` 的实现细节
    错当通用约束；`gen_activity` 本就是 file 作用域）；
  - ADR 补**角色位契约表**：每个角色**同时**定义寻址键与产物形状——引擎要消费它，故与
    普通条目"形状归插件"不同；并写明**角色位一律是过渡面**、收口时应为空。

  验证：全量 **2166 passed / 7 skipped**；`tests/engine/analyzer` **305 passed**；
  `-m smoke` **434 passed**；`tests/policy` **125 passed**。

- **P2 纵向打穿 `param_default`：引擎侧参数抽取整体迁出（ADR-0019）**：引擎不再定义
  "参数有值文本"这个事实——它是语言知识，改为 verilog 语言包的精化项产物。

  1. **verilog 插件**（`grammar/verilog/plugins/elaboration/`，纯能力组件，
     `[capabilities] elaborator`）：`param_default` 项（`unit` 作用域）求解
     `{单元名: {参数名: 值表达式文本}}`，头部 `#(P=v)` 优先 + 体内 `parameter P=v;`
     补全——合并规则与搬迁前 `_fill_params` **逐字对齐**。
  2. **引擎接线**（`analyzer/elaboration/{atoms,service}.py` + `checker.py`）：
     `StructureAtomSource`（文件 / 单元 / 工程原子，单元判定走声明）；
     `ElaborationService`（语言无关服务句柄，P2 只开 `render`，转交既有
     `StructureCtx.render_subtree`，不新增异常处理点）；`check()` 在**信号图之前**
     跑精化（层 3 的 generate 活性要用单元常量绑定），产物容器注入
     `analyzer._external_extra` 供插件消费。
  3. **5 个消费方迁移**（原各自读引擎 `ModuleInfo.params`）：`width_check` /
     `hier_check` / `latch_check` / `inst_check`（W103 只要参数名集合）+ 引擎
     `GenerateEvaluator`。
  4. **同批删除**（不留双路径）：`ModuleParam`、`ModuleInfo.params`、
     `_register_header_param` / `_fill_header_params` / `_fill_params` /
     `_fill_body_params`，以及随之成死声明的 `[structure.fields]` 两键
     （`params` / `param_name`）。

  **搬迁前先做等价性对拍**：新实现落地后、删旧实现前，断言插件产物与引擎抽取
  **逐项相同**（实测通过）；删旧实现后该断言改为**冻结 golden 值**
  （`tests/engine/analyzer/test_elaboration_param_default.py`）。这是"先证后改"的落地形态。

  **P2 实测更正两处协议**（已回写 ADR-0019 决策 3）：
  - `locator` / `locator_fn` **都可省略**（省略 ⇒ 求解器收到 `hits = [原子根]`）。
    原设计要求"恰好声明一个"，但 `param_default` 的值分散在两种节点形态（头部字段 +
    体内 `ParamDeclStmt`），**单条规则名表达不了**——硬要表达就会长出字段投影小语言
    （＝已拒的"配置面膨胀"）。
  - 新增**引擎角色位 `role`**（封闭枚举，现役只有 `unit_constants`）：容器条目名由
    插件定 ⇒ 引擎无法按名寻址**自己也要用**的产物（过渡期 `GenerateEvaluator` 需要
    单元常量绑定）。⚠ 它是**过渡面**，gen 族迁入 P3 后应删除该角色。

  **分期更正**：`param_override` **不再与 P2 同批**。落地时读码发现它的三层合并逻辑
  （`#(.P(v))`）**今天已全在插件侧**（`width_check._override_params` /
  `hier_check._merged_params`）——**不是引擎侧渗透**，上提为协议项是**去重共享**而非
  "搬出引擎"。故改随 `inst_sites` / `connections` 族在 P3 落地（它是那两族产物的直接
  消费者，同批做才无中间态）。

  **验证**：`tests/engine/analyzer` **303 passed**、`-m smoke` **434 passed**、
  `tests/policy` **125 passed**（含诊断基线门禁持平）、最小语言包探针串行**无回归**
  （仍绿 1163 / 1163 逐项相同）。

- **最小语言包探针：修正为强制串行（P1b 的交付缺陷，实测暴露）**：原基线以并行建立，
  并声称"仍绿集合稳定"——**该结论是错的**。探针**故意让一个进程里混跑两种语言**
  （默认包 = 探针包，而大量引擎测试显式加载 verilog），而本仓已记载"多语言同进程有
  真实串味史"（`tests/README.md`），结果随 xdist 的 worker 分配漂移。实测（**同一份
  代码**）并行三次 **1126 / 1122 / 1120** 仍绿；**在基线提交 `141cf25` 上复跑也复现不出
  基线**（1120 + 6 项假回归）。改串行后同一子集两次逐项相同（351），全量串行两次
  **1163 / 1163 逐项相同**。
  处置：工具**默认补 `-n 0`**（`_serialize`，显式给并行参数则尊重但降级为"大致规模"）、
  比对前先出数（口径不符也看得到规模）、基线**串行重记**
  （`tests/engine` 串行 = 1163 仍绿 / 246 变红 / **0 报错**；串行下报错为 0，而并行
  130~155——又一佐证）。口径写入工具 docstring、`tools/README.md`、
  `docs/gaps/gap-language-penetration.md`（判据 1 节）。

- **精化协议骨架 + 行为面基线（ADR-0019 P1）**：分两批落地**机制**，P1 当时**未接线**
  （`ProjectChecker` / `pipeline` 不调用，对外行为零变化）——**P2 已接线**，见上。

  1. **P1a 契约与驱动器**（`analyzer/elaboration/`）：
     - `contract.py`：`Locator`（声明式定位 = 规则名）/ `ElaborationItem` /
       `ElaboratorSpec` + `parse_spec` 全字段 fail-fast（未知键 / 项重名 / 容器键跨项
       重复 / `depends_on` 自引用与成环 / `locator` 与 `locator_fn` 二选一 / 求解名
       未解析 / scope 非引擎枚举）；Kahn 拓扑排序（同层保持声明序，结果确定）。
     - `driver.py`：引擎侧**唯一执行体，语言无关**——按拓扑序驱动「原子枚举
       （file/unit/project）→ 定位 → 求解 → 归位 → 强方向核验」；`SolveCtx` 是跨文件
       传播通道（后声明项读先声明项产物）；含 `Atom` / `AtomSource`（原子供源协议，
       真实实现留 P2）。
     - `loader.py`：`load_elaborator_spec(rules_dir)`——与 `macro_policy` 同款能力位
       查找（按语言包作用域，切语言不串用）；未声明 → `None` = 降级。
     - `core/_protocol.py` 增 `CTX_ELABORATION`（产物容器键）。
     - **与 `schedule._verify_produced` 的刻意差异**（记入模块头）：那里双向核验
       （声明 = 物化，物化未声明也报错）；本处只做**强方向**（求解器返回未声明的键 →
       fail），**不**因"声明了但某原子无产物"报错——本处按原子出产物，"该原子无此类值"
       是常态（无参数的模块本就没有 `param_default`），双向核验会误报。另加"容器键
       跨项唯一"补住静默覆盖。
     - 新增 `tests/engine/analyzer/test_elaborator_protocol.py`（**37 例**：声明
       fail-fast / 拓扑序 / 定位归位 / 核验 / 降级五组）。

  2. **P1b 行为面基线**（gap 档判据 1「待做」项）：
     - 新增 `tools/min_pack_probe.py` + 基线 `tools/min_pack_baseline.json`。机制 =
       `$TPC_CONFIG`（官方支持的覆盖点）把**默认语言包**指向迷你包、**子进程**跑引擎
       测试——必须**进程级**隔离：`DEFAULT_RULES_DIR` 在 import 期已被各模块复制值，
       同进程 monkeypatch 无效。**零引擎改动**。
     - 首轮实测：`tests/engine` 共 1402 例 → **仍绿 1126** / 变红 146 / 报错 130。
       ⚠ **该并行口径与数字已被推翻**（下一批修正为强制串行：仍绿 1163 / 0 报错）——
       保留原文以留下"错在哪"的痕迹，**判据以串行口径为准**。
       判读：改动前后各跑一次，**仍绿集合缩小 = 回归**（曾有测试走引擎通用面，现开始
       依赖语言包声明）= P2–P3 逐族搬迁的回归护栏。
     - ⚠ 两个已知折扣（写在工具 docstring 与 gap 档）：① 只有**仍绿集合**稳定——
       `变红/报错` 边界会漂（两次 146/130 vs 141/135，总数不变），故基线只认仍绿集合；
       ② 探针包固定为 `grammar/yaml`（仓库既有"迷你语言包"，无插件、4 个 token 文件），
       它**仍是一门真语言**，故结论只在"相对该包"的意义上成立；换包须重记基线。
     - `tools/README.md` 登记；`docs/gaps/gap-language-penetration.md` 判据 1 状态
       改「已做」并记机制与实测。

  **验证**：P1a = `test_elaborator_protocol.py` **37 passed**、`tests/engine/analyzer`
  **296 passed**、`-m smoke` **433 passed**（与改动前一致 → 未接线，零行为变化）；
  P1b = 探针两次跑仍绿集合逐项相同（1126 / 1126，无回归、无新变绿）。
  ⚠ **静态检查未机器验证**：本会话 pylance MCP 工具不在可用工具集且 `pyright` CLI 未
  安装 → 已按 `pylance-cleanup` 判据手工自查并预修两处严格模式问题（未参数化的
  `Mapping` 注解；`item.locator_fn`（`str | None`）传入 `_solver(name: str)` 加断言
  收窄），据实记为 partial。

- **精化基座重构定案（设计先行，未实现）**：ADR-0019
  （`docs/decisions/0019-elaboration-plugin-protocol.md`）确立边界——引擎的最小可视
  单位 = **文件**（读源 / 宏展开 / 解析 / AST 缓存 / 行映射与宏区间 / 依赖发现编排）；
  精化协议 = 语言包 `[capabilities] elaborator` 返回的**可扩展项列表**（`name` /
  `locator` / `solver` / `scope` / `provides` / `depends_on` / `locator_fn`），
  **定位声明式为主、求解为插件函数**；产物**容器**由引擎定、**条目名与形状由插件定**。
  分期：P1 骨架 + 行为基线（只新增不接线）→ P2 纵向打穿 `param_default` +
  `param_override` → P3 逐族搬迁（每项落地即删旧实现）→ P4 文档收口。

  **为什么是"搬类型"而不只是"搬逻辑"**（本次勘察结论）：`width_check` 插件 1311 行
  逻辑早已在插件侧，却靠 `_ModulePort.width_expr` / `ModuleParam.value_expr`
  （`analyzer/structure.py:68-98` 的**引擎 dataclass**）喂饭——**引擎替插件决定了
  "世界由哪些事实构成"**（端口有宽度、参数有值文本、信号有驱动/负载），故"位宽比较"
  「跨文件参数值变更」观感上仍像在基座里；只要类型词汇表留在引擎，插件再怎么写都只是
  在填引擎的表格。同构先例 = ADR-0018（预处理器：引擎只做文本操作，策略走能力位）。
  `TODO.md` 原「精化部件化 + 插件化」的 E1–E4 执行面改 P1–P4，"产物模型与 `context.extra`
  键名（形状属引擎协议，不能由插件定义）"一条**推翻**（前提是"条目固定"，条目可扩展后
  不成立）——已同步。

- **Bifrost 外部审计收尾（主线收口）——能力族 ④ 变更差分接入 + 判保持登记表守卫**：

  审计修复主线（复杂度族 / 重复族 / in-loop 族 / 断言族）此前已逐项下结论，本次收尾
  补齐四件事，使"每个命中都有结论"**可被机器守、可被复读**：

  1. **B-C 结构重复族快照按 A–G 归位（结案）**：按 `tools/structural_score.py` **同口径**
     （`CLONE_CHUNK=30`、`min_score=90`、R3 + R6）重跑 = **102 对**（≤40 tok 83 对），
     逐对归位：A 10 / B 15 / C 68 / D 4 / F 1 / G 1 / U 3——**U 的 3 对正是已登记的
     「变体 / 同形不同源」→ 无新形态**；过 R3 的 4 对全部有 R6 结论，D = 0 与 S 自洽。
     C 从 B-D 分类期的 32 增至 68，正是复杂度批次（B-F 六~十）拆出的薄助手/桩（共性
     已抽、残留入口样板），不是新逻辑重复。⚠ 旧草稿脚本用 `CHUNK=60`，与 S 口径
     **不可比**（本次改为复用度量工具的机器，不另写一套）。
  2. **判保持登记表自足化 + 新增守卫**：`tools/structural_kept.json` 原有多条理由写成
     "见 `_drafts/bifrost/dispositions.md` 某节"——草稿销毁后即成**悬空引用**（"保持"
     退化成"没看"），全部内联为自足理由；补登记 1 项（`policy/check_doc_refs` 内 89 tok
     同类对，此前只被 R4"两侧都在 `policy/`"机械豁免、**无逐项结论**，而 R4 的理由写的
     是"两道门禁各自独立"，不覆盖同文件内情形）。新增
     `tests/policy/test_structural_kept.py` 守两件事：理由有实质长度、键能解析到真实
     定义——**结构性搬家后路径失效会当场变红**（精化基座重构的前哨）。
  3. **能力族 ④ 变更差分接入流程**（`score_diff` / `blast_radius` / `missing_tests`）：
     本仓现有三道证据（pytest、字节对拍、诊断基线）全是**行为面**，对"移文件 / 拆类 /
     改签名"无感，而下一项工作正是这类改动。用法、字段口径、以及**两套基线口径不可
     混用**的坑记入 `policy/bifrost_audit.md`「重构期用法」节；重构前锚点 = `c63c6bb`
     （S = 0 冻结于 `tools/structural_baseline.json`）。未用族归属一并判定（⑤/⑩/⑪ 按需，
     ⑥ 不纳入）。
  4. **审计结论分流**：跨项复用的**判据**（复杂度过阈三分类 / in-loop"形态 vs 病理" /
     测试断言的词法判据 / 重复对的体形态判据）固化进 `policy/bifrost_audit.md`「判据集」；
     `TODO.md` 的「外部审计修复」块（231 行，已 100% 完成）按"完成即删"移除；
     `_drafts/bifrost/`（findings + dispositions + raw 共 2.6 MB）在**无耐久引用复检后**
     销毁——结论先落正式位（登记表 / `structural_budget.md` / `bifrost_audit.md`）再删稿。
  5. **`bifrost.correctness.python-absent-member` 下边界判决**（此前是"结论缺失"，不是
     "跑了没发现"）：整仓单跑**两次独立实测均不收敛**（2026-09-18 3471s；2026-09-22
     复测 3652s/61min，RSS 1.7 GB → 5.1 GB 线性增长 = 组合爆炸）；而
     `--root . --sources <子集>` 可得 `complete`（`bifrost_probe` 0.6s / `analyzer` 146s），
     但 absence 分析要求声明面穷尽，**分片并集不等于整仓结论**。判决：整仓判不了 →
     登记为已知边界（含复现命令与耗时），替代面 = Pylance 诊断。要拿这个信号须先解决
     "声明面穷尽性"，不靠加预算硬跑。

  **验证**：`tests/policy` 125 passed（含新守卫 5 例）；`structural_score --compare` 仍
  S = 0（消除 0 / 新增 0 / 变大 0）；`check_doc_refs` / `check_hardcode` PASS。

### Changed

- **测试耗时：`_find_plugin_tpc` 目录遍历去重（全量并行 159s → 96s，-40%）**：
  `config_registry._find_plugin_tpc` 原按**组件名逐个** `os.walk` 全树搜索组件
  `tpc.toml`，而 `_load_meta_declarations` 在一次 check 里被反复调用——实测一个只含
  小样例的 `check()` 里该函数被调 **130 次**、`os.walk` **2740 次**（0.136s/次
  check），暖态 check 因此 0.256s、其中 `config_registry.resolve` ×10 独占 0.184s。
  改为**按 `plugins_dir` 建一次 名→(tpc 路径, 相对目录) 索引**后按名取（与 analyzer
  侧已验收的 `ModuleIndexer.dir_module_files` 同型；`setdefault` 保持"遍历序首个"
  语义）。索引登记在 `CONTENT_ADDRESSED`（键 = `plugins_dir`，纯字符串索引）。

  **实测**：暖态 `check()` 0.256s → **0.121s**（`resolve` 0.184s → 0.048s，函数调用
  -25%）；全量并行 `-n auto` 用例 2119 → 2120、**159.2s → 95.9s**；e2e
  `run_all_tests` 59.5s → 42.1s（FAIL 0 不变）。

  **验证**：全量 **2120 passed / 7 skipped / 0 failed**（shuffle seed 1/2 各再跑一次
  同样全绿）；`tools/check_test_isolation.py` 隔离档 **163 OK / 0 FAIL**；
  `eval_lint_accuracy` recall 100% / FP 0；`eval_diag_baseline` **5548 → 5548 无增长**
  （配置解析语义未变）；`check_doc_refs` / `check_hardcode` PASS。

  ⚠ **同批记一条被实测否掉的方案**（避免重走）：把 `_PIPELINE_SHARED` /
  `SharedComponents._CACHE` 从"每测试 clear"改成按内容寻址保留，**使全量 28–44 项
  失败**（语言切换三例、real_fidelity 六例、pipeline_idempotent、
  `test_shared_cache_key`、analyzer 多驱动/大小写/inout、case_check …；随机文件序下
  23–36 项）。根因：这两个缓存的**值是可变的引擎束**（lexer/parser/renderer/scanner
  实例，运行期写自身状态），不是纯值——"键控"只保证取到同一对象，不保证该对象可跨
  运行复用。真正的方向是把束里的**不可变装配**与**每次运行的可变态**分开（冷装载
  实测构成：语法后处理 ~0.5–0.6s、目录遍历 ~0.2s、TOML 解析 ~0.19s），属设计改动，
  结论记在 `core/global_state.py` 的设计取舍段。

- **行尾注释锚定改跨层推迟 + 按语言包声明分流两类注释（修分号被注释吃掉的既存缺陷）**：
  `LineSuffix` 原先只在**同一层 Concat 内**推迟，内层原子节点（`Number` / `SelectExpr` /
  `ParenthesizedExpr`）的 doc 常无尾换行点 → 后缀就地落地，父级同行后续内容（语句 `;`、
  `join` 的分隔符/闭括号）被印在注释之后，**落进注释里被吃掉**：
  `assign a = v[0] // note` + 换行 + `;` → 输出 `assign a = v[0] // note;`（分号消失，
  输出非法）。现按 Prettier lineSuffix 的全局缓冲语义**跨嵌套 Concat/Nest/Align/Prefix
  上提**（`Union` 两支后缀文本相同才上提，不同则各自就地落地；`Fill` 内不跨项）。
  同时把 `trailing`/`head_trailing` 槽里混着的两类注释分流——判类由语言包声明
  `Renderer.comment_ends_line` 驱动（引擎不硬编码标点），写入 `LineSuffix.line_ending`：
  行终止型（`//`）参与上提，块注释（`/* */`）**就地落地**（`a /* c */ + b` 不被搬到行尾；
  两类都保持 `LineSuffix` 类型，`join` 才能继续把项尾注释搬到分隔符之后，
  `clk, /* c */ output` 形态不变）。

  **验证**：全量 **2114 passed / 7 skipped**；真实语料 diag 5548 持平、lint 33/33 误报 0；
  格式化字节对拍 73 文件 0 diff；三门禁 PASS；`structural_score --compare` 无新增/变大。

- **删死规则 `BitWidthLiteral`（语言包 verilog，连带 6 处死面）**：完整数字字面量在
  lexer 阶段即作为单个 `literal.number` token 产出（`[[number.based]]` 声明），该规则的
  production（`literal.number` + `'` + `@Identifier`）实测六种形态（`8'hFF` / `8 'hFF` /
  `8'h FF` / `'hFF` / `8'shFF` / `4'b10_10`）均不产生节点 = **不可达**。删除范围：
  规则定义块（parser/node/renderer layout）、`PrimaryExpr` 候选、`AttrConstPrimary` 与
  `UdpInitial` 的候选、`inst_check` 的合成节点拼回分支与 `_is_literal` 名单、
  `width_check` 宽度分派表项，并同步四处文档举例。
  **删除一度受阻**，真因不是"规则被用到"：`(text, line)` 全局去重下，该规则的**失败尝试**
  残留 `current_node` → 行尾注释被挂到随后被丢弃的节点上（HEAD 行为），删规则后注释改挂
  真节点 `Number` → 触发上面那条分号缺陷 → 宏原文回填的自描述比较失败。上一条修完后
  删除直接通过（`test_macro_body_comment`、`test_real_corpus::svparser_interop[ref_darkriscv.v]`
  全绿，计数见上）。教训记在 `docs/gaps/gap-language-penetration.md`：**规则的"可达性"
  与"影响力"不等价**（不可达规则仍可经 `current_node` 残留 / 注释去重等间接通道改变行为）。

- **指令行切分收为单一实现（去 5 处关键字字面量 + 单空格假设）**：`define` /
  `undef` / `ifdef` / `ifndef` / `elsif` 五个处理器各自写 `stripped[len(prefix) +
  len("define ") :]`——关键字拼写重复了一遍（值与注册名由分派保证相同），
  且分隔符假定是**单个空格**：`` `define\tW 8 `` 会被扫成"宏调用行"（关键字比较
  不中 → 定义静默丢失）。现收为 `primitives/registry.py::split_directive`
  （前缀 + 关键字 + 空白 + 参数）：`scan_directives` 取关键字与 handler 取参数
  同源一份实现，关键字拼写只由声明候选提供、分隔空白按空白字符集切。
  语料实测：138 个样本里 TAB 分隔指令 **0 处**（本次属防御性修复 + 去重复表达）。
  测试：`tests/engine/preprocessor/test_primitives.py` 新增 `TestDirectiveSplit`
  （6 种切分形态 + TAB 分隔的 define/undef/ifdef）与
  `TestScanDirectiveSeparator`（TAB 分隔的 `` `define `` 能进宏表 = 分派级验证）。

  **验证**：worktree A/B 对拍 106 个共同样本输出逐文件一致（TAB 语料为 0 → 预期
  零差异）；预处理器目录 132 passed；单进程全量 **2072 passed / 7 skipped**；
  真实语料三工具持平（lint 33/33 / 误报 0、diag 5548、宏覆盖 86/135）；
  config_sites / doc_refs / hardcode 三门禁 PASS。

- **宏调用后随字面量后缀改声明驱动（删引擎硬编码正则）**：`` `W'd0 `` 的 `'d0`、
  `` `W'h1F `` 的 `'h1F` 原由 `_expand._LITERAL_SUFFIX_RE` 硬编码正则识别（展开时把
  后缀纳入**调用区间**，使替换结果与 token 边界对齐 → 还原按 token 区间回插；
  ADR-0017 决策 3/4）。现改为语言包声明形态模式：

  ```toml
  suffix_after_call = "'[sS]?[bBoOdDhH]?[0-9a-fA-FxXzZ_?]*"
  ```

  1. 新增 `macro_shape.load_macro_call_suffix`：读取模式 + 编译（fail-fast：非串 /
     空串 / 非法正则 / 可匹配空串）；与 `[literal] number` / `[id.id] id` 同款
     （形态模式写在语言包，引擎只编译不解释）。
  2. 未声明 → 不扩展（不猜语言字符）；`_extend_literal_suffix` /
     `_extend_macro_chain` 改收编译后的模式，段内不再引用任何字面字符集。
  3. 声明注释里写明它比 `[[number.based]]`（`base/_number.toml`）**宽一档**的理由：
     还要覆盖无进制字母的 SV 填充字面量 `` `W'0 `` / `` `W'1 ``，故不复用数字形态
     （否则丢还原区间——原先保守不改的正是这一条）。
  4. 新增 `tests/engine/preprocessor/test_macro_suffix.py`（9 例：声明解析 / 4 种
     非法声明 fail-fast / 区间扩展与不扩展 / 链合并）。

  ROADMAP P3.6「预处理器宏策略配置化」至此全项闭环（段已删）——预处理器引擎侧不再
  留任何宏相关的语言知识（前缀 / 名字位候选 / 实参形态 / 后随字面量后缀全声明驱动）。

  **验证**：worktree A/B 对拍 106 个共同样本输出逐文件一致；真实语料三工具持平
  （lint 33/33 / 误报 0、diag 5548、宏位置覆盖 86/135）；`test_macro_suffix.py` 9 例
   + 全量测试（多轮复跑见下）。

- **函数宏实参形态改声明驱动（删引擎硬编码 `(` / `)` / `,` / 嵌套 `[]`）**：
  带参宏的括号对、实参分隔符、配平用的嵌套括号对原先是 `_expand._match_paren_args`
  （认 `(`/`)`）、`_split_args`（认 `([`/`)]`/`,`）、`primitives/define.handle_define`
  （认 `(`/`)`/`,`）三处引擎硬编码。现统一由语言包 `[macro_recognition]` 声明：

  ```toml
  call_args     = "bracket.l_parentheses,args,bracket.r_parentheses"
  arg_separator = "symbol.base.comma"
  ```

  1. `call_args` 是与 `shape` 同款的**生产式**（token 名 + 实参槽占位符 `args`）；
     括号对文本取自 `[bracket].pairs`、分隔符文本取自 `[symbol.*]`（`macro_shape.
     _token_text`）——引擎不认识具体字符。定义侧（`` `define NAME(a, b) ``）与
     调用侧（`` `NAME(x, y) ``）同形，共用这一份声明。
  2. 配平与切分入 `macro_shape.MacroCallArgs`（`match_args` / `split`）：按声明
     括号对**整串**匹配（多字符括号对同样适用），配平括号对取语言包声明的**全部**
     括号对（旧实现只认 `(`/`)`、`([`/`)]`）。
  3. `_match_paren_args` / `_split_args` 删除；`handle_define` 从 ctx 取声明
     （由 `scan_directives` 放入）。
  4. 声明的名字写错 / 形状不对 / `call_args` 缺 `arg_separator` → fail-fast；
     **有待参宏却没声明实参形态** → `expand_tokens` fail-fast（不静默降级成
     "带参也不识别"）。
  5. 新增 `tests/engine/preprocessor/test_macro_call_args.py`（21 例：声明解析 /
     8 种非法声明 fail-fast / 配平（嵌套、多字符、未闭合）/ 顶层切分 / 定义侧与
     调用侧同源 / 缺声明 fail-fast）。

  ROADMAP P3.6「函数宏实参形态迁出」闭环；该阶段仅剩 `_LITERAL_SUFFIX_RE` 一项。

  **验证**：worktree A/B 对拍 106 个共同样本输出逐文件一致；全量测试 2053 passed /
  7 skipped；真实语料三工具持平（lint 33/33 / 误报 0、diag 5548、宏位置覆盖 86/135）；
  config_sites / doc_refs / hardcode 三门禁 PASS。

- **删非语义展开路径（token 锚 + 宏边界节点化死链），处置枚举收到三模式**：
  自查发现 `expand_tokens(semantic=False)` **无引擎调用方**（pipeline / analyzer /
  linter 三条路全走"宏体铺进流"），而该路径独占 token 锚产出——实测 138 样例：
  铺宏体路径产 `line` 32 + `inline` 259（token **0**），非语义路径才多出 `token` 124。
  其下游 `pipeline._stage_macro_nodes`（锚标识符 → MacroCall）锚表**恒空**
  （180 次调用全 0），最终 AST 里 MacroCall / `_macro_source_text` / `_src_span`
  全为 0——整条链是死代码（判据 A1：无消费者）。删除：

  1. `expand_tokens` 的 `semantic` 参数与 token 锚分支、`_call_site` 的 `semantic` 字段；
     `_bridge.restore_anchors` 的 `token` 分支（`line` / `inline` 两态保留）；
  2. 锚名协议 `core/token_protocol.py::RESERVED_PREFIX` / `ANCHOR_MARK` /
     `anchor_salt` / `anchor_name`（仅 token 锚使用）+ 其测试文件；
  3. 宏边界节点化整链：`pipeline._extract_macro_name` / `_attach_macro_meta` /
     `_rewrite_marker_nodes` / `_stage_macro_nodes` + 调用点，
     `Node._src_span` / `Node._macro_marker` 字段（`_macro_source_text` /
     `_macro_name` 保留——`parser_core` 在 `parse_raw` 路径挂载，仍在使用）；
     一并清掉 aefe313 遗漏的 `Node._macro_body` 字段声明（同属无写入者字段）；
  4. 处置枚举 `token` 与 `append`（语句尾补分号）知识整体消失：
     `macro_policy.py` 枚举收为 `splice` / `line` / `inline`，
     verilog 策略插件判定表同缩（`README.md` 重写判定依据与已知边界）。

  引擎侧语言知识因此再少一项（补分号不再需要——宏体铺进流后是真实文本，
  语法自己判），`preprocessor/README.md` 锚形态描述由三态改两态。
  依据与实测数据见 `docs/decisions/0018-preprocessor-plugin-policy.md`（后续收敛节）。

  **验证**：worktree A/B 对拍 106 个共同样本输出逐文件一致（成功标志 / 长度 /
  sha256 全同）；全量测试 2032 passed / 7 skipped；真实语料三工具持平
  （lint 33/33 / 误报 0、diag 5548、宏位置覆盖 86/135）。

- **预处理器展开策略迁出引擎 → 语言包能力 `macro_policy`（引擎只做文本操作）**：
  `preprocessor/_expand.expand_tokens` 原先内含 4 个硬编码策略分支（整行占位 /
  空体 inline 锚 / 独占一行补分号 / 语义替换）——判定条件是从 verilog 语料长出来的
  启发式。现改为引擎定义**处置枚举**（与锚条目 `mode` 同词）：
  `splice`（宏体铺进流 + 宏区间）/ `line`（整行占位）/ `inline`（行内注释锚）/
  `token`（唯一 token 锚，可带 `append` 追加文本）；"选哪一种"由语言包通过
  `[capabilities] macro_policy = "file.py:fn"` 声明（与 formatter 同款），引擎给
  通用文本事实（调用点上下文）、策略返回方案：

  ```toml
  # grammar/verilog/plugins/macro_policy/tpc.toml
  [capabilities]
  macro_policy = "_policy.py:build_macro_policy"
  ```

  1. 新增 `preprocessor/macro_policy.py`（契约 + 校验 + 默认方案）与
     `grammar/verilog/plugins/macro_policy/`（判定表 + 语料依据）；判定表与迁移前
     逐条等价（含优先序：空体宏形态先于 semantic 判定）。
  2. 新增 `core/plugin_loader.py::get_capability_in(name, rules_dir)`：能力按
     **语言包目录**限定查找（不依赖"当前装载语言"全局态）——预处理器按 rules_dir
     工作，同进程切语言不串用（c4 拿不到 verilog 的策略）。
  3. 未声明能力 → 默认 `splice`；方案非法（mode 未知 / `append` 非串 / `line`
     用于同行多调用）→ fail-fast。
  4. 顺带修掉 `expand_tokens` 里 `if "//" in tail` 的注释标点硬编码（改从
     `lexer/comment_syntax.py` 声明取——同族"注释标点声明驱动"的漏网项）。
  决策与边界见 `docs/decisions/0018-preprocessor-plugin-policy.md`。

  **验证**：worktree A/B 对拍 107 个样本输出逐文件一致；全量测试通过；真实语料
  三工具持平（lint 33/33 / 误报 0、diag 5548、宏位置覆盖 86/135）；新增
  `tests/engine/preprocessor/test_macro_policy.py`（13 例：默认方案 / 判定表落地 /
  非法方案 fail-fast / `line` 同行守卫 / 语言作用域）。

- **宏形态改由 `[macro_recognition]` 声明（`shape` 生产式 + 候选列表），`[directives]` 表删除**：
  原先每段宏形态用自造字段 `strategy` + `prefix` 描述（且只有 `strategy = "prefix"`
  被实现；文档宣称的 `suffix`/`none` 从未落地），另有一张手写的 `[directives]`
  表（关键字 → token 类型）与它并存——形态与指令集是两份手写副本。现改为用
  grammar rules 的**同一套生产式规则**写形状、候选集用 TOML 列表枚举，引擎只做
  通用解析：

  ```toml
  [macro_recognition]
  shape     = "symbol.base.backtick,name"        # 前缀 token 名 + 名字位占位符
  directive = ["macro.else", "macro.undef", "macro.define", ...]   # 名字位候选
  call      = []                                 # 空列表 = 任意标识符
  ```

  1. **用 token 名而不是字符**：`shape` 的前缀位写 token 名
     （`symbol.base.backtick`），符号文本取自 token 定义——`` ` `` 因此在
     `[symbol.base]` 里有了名字（新增 `backtick = "`"`）；`name` 是名字位占位符，
     **宏名与标识符共用同一扫描实现**（`core/token_protocol.IDENT_RE`：lexer 的
     id 分支与宏名扫描不再各写一份，文本层展开器也不再另写 `\w+`）。
  2. **指令集用候选列表枚举**（一串 `macro.<关键字>`）：命中哪个候选就产出哪个
     token 类型，`_expand.py` 的指令名集合也从同一处推导——`[directives]` 表与其
     三份手写副本（lexer / `_expand` 各读一遍）一并删除；空列表 = 名字位任意
     标识符，整段不声明 = 该形态不识别。
  3. **形态落地**（`preprocessor/macro_shape.py`，声明解析 + fail-fast）：
     `shape` 须是两位顺序 `symbol.<cat>.<name>,name`、候选须是 `macro.<关键字>`
     列表；未实现形态（后缀序 / 正则前缀 / 多于两位）与非列表候选直接报错，
     不静默降级。`[macro_recognition]` 按 **rules_dir** 解析
     （与 `Lexer(rules_dir=…)` 同源），修掉旧实现读顶层 `prefix`（TOML 里根本
     没有该键）→ 回退硬编码 `` "`" `` 的语言字符泄漏。
  4. **词法优先序**：`` ` `` 同时是 `symbol.base.backtick` 与宏前缀，symbol 分支
     让位——"前缀 + 名字"成立按宏识别，**裸 `` ` `` 落符号分支**（旧行为是吃成
     无名 `macro.call`）；实测全仓 238 个样例里裸反引号仅 4 处且都在注释文本里。
  5. 前缀为空（无形态声明的语言包，如 c4/yaml）不再拼出非法正则——文本层宏调用
     正则按声明前缀构造，空前缀 = 永不匹配。

  **验证**：全量 2034 passed / 7 skipped；**worktree A/B 对拍** 107 个样本输出
  逐文件一致（成功标志/长度/sha256 全同）；真实语料三工具持平（lint recall
  33/33 / 误报 0、diag 5548、宏位置覆盖 86/135 = 63.7%）；新增
  `tests/engine/preprocessor/test_macro_shape.py`（20 例：形状/候选解析 / fail-fast /
  前缀文本随 token 定义 / 语言切换不串味 / 词法落地）。

### Removed

- **无消费者的宏体形态分类链（判据 A1 无引用）**：`[macro_shape]` 的 `wrappers`
  （stmt/decl/expr/port 包裹模板 + `pick`/`skip_head`/`skip_tail`）与
  `continue_leads` 首 token 预过滤、`preprocessor/macro_shape.py` 的
  `classify_macro_body`/`build_parse_probe`/`build_parse_ast`/`extract_macro_body`、
  `pipeline._make_macro_body_provider`、`Node._macro_body` 字段与其 `iter_children`
  排除分支，全批删除（`wrappers.port` 更连引擎调用点都没有：`_PROBE_ORDER` /
  `key_of_kind` 只含 stmt/decl/expr，仅测试直调）。
  **实测根因**：pipeline 恒以 `semantic=True` 展开（非空体宏不建 token 锚）→
  `_stage_macro_nodes` 锚表恒空 → 该链永不触发；在真实管线上挂探针跑一遍：
  `classify_macro_body` 调用 **0 次**、`extract_macro_body` 请求过的 shape key
  为空、`_macro_body` 挂载 **0 个**——产物本就无任何读取者（全仓只有写入点 +
  遍历排除）。同批删除 `tests/engine/preprocessor/test_macro_body_extract.py`
  与 `test_macro_shape.py` 的分类用例。
  `[macro_shape]` 只留仍有消费者的 `suffix_leads`（`_expand.py` 锚形态选择，
  ice40 端口默认值宏；`test_suffix_lead_drives_anchor_mode` 继续锁定
  "声明 → 行为"链）：`grammar/verilog/base/_macro.toml` 的该段从 61 行缩到 8 行。
  后续若重做"形态判定 → 展开策略"，按 ROADMAP P3.6 以"声明 + 真实消费点"成型
  （见 `docs/decisions/0017-macro-in-syntax-position.md`）。

- **`[macro_shape]` 声明整体删除（含 `suffix_leads`）——前置：linter 改走语义展开**：
  上一项删完后只剩 `suffix_leads`（赋值后缀宏体前导集），它唯一的真消费者是
  **linter 的锚形态特判**（`linter/scanner.py` 的 `expand_tokens` 未传 `semantic`
  → 锚形态：`=` 开头 body 改走 inline 锚 + body 区间，否则 `input NAME `M`` 退化为
  `input NAME tpc_marker_N` 两个相邻 id）。现把 linter 也切到**语义展开**
  （宏体文本铺进流，与 pipeline 的 lint 输入、analyzer 的 `_expand_source`
  同一条路）——形态特判与其声明于是不再需要，整段删掉：
  `preprocessor/macro_shape.py`（模块删除）、`grammar/verilog/base/_macro.toml` 的
  `[macro_shape]` 段、`grammar/verilog/tpc.toml` 的加载项、`_expand.py` 的
  `_suffix_leads` 分支与 `get_suffix_leads` 导入、对应测试。
  **实测依据**：关掉 `suffix_leads`（其余不动）→ ice40 语料 linter **+34 条
  `phase-statement` 误报**（即当初 M1 的 34 错）；而把 linter 切成语义展开 →
  9 个真实语料的诊断**逐条 (行,列,码) 完全一致**（3359 条 ice40 含在内，数量与
  位置均不变）→ 语义展开既去掉特判又不改判定面。

### Fixed

- **引擎内硬编码注释标点（语言知识泄露）**：占位 marker（`tpc:<kind>:<seq>`）以
  注释形态穿过管线（parser 当 trivia、渲染端保留注释），但书写/识别处把 verilog
  的 `//` 与 `/* */` 写死在引擎里（`_expand` 的指令占位与宏锚、`ifdef` 的条件块
  占位、`_bridge` 的还原、`pipeline` 的 marker 行扫描、`renderer/inline_comment`
  的整行占位扫描——yaml/c4 这类语言包里这些标点不成立）。现全部改为**语言包声明
  驱动**：
  1. `lexer/comment_syntax.py`（新）：`CommentSyntax`（行注释起始 + 成对定界符）
     ——注释标点的唯一读取点，从 `[comment] pairs` / `[[capture]]` 归一化并按
     `rules_dir` 缓存；预处理器扫描用的标记面（跨行定界符对 + 行注释起始列表）
     同源。
  2. `preprocessor/_markers.py`（新）：marker 的两种书写形态（整行行注释占位 /
     行内块注释占位）与识别（整行形态正则、`tpc:` 编号提取），标点取自声明；
     语言包未声明所需形态而该形态又被需要 → fail-fast（不静默降级）。
  3. 还原侧按声明的标点定位（`_bridge.restore_anchors` / `_reverse` /
     `renderer/comment_restore` / `renderer/inline_comment`），`expand_tokens`
     新增 `rules_dir` 形参（锚的书写形态来源）。
  4. 同一泄漏的另一处：`analyzer/suppress.py` 的诊断豁免注释（区间对 / disable-line）
     也把 `/* … */` 与 `//` 写死，现按声明编译三种模式（未声明块注释的语言包 →
     区间形态不存在；未声明行注释 → 单行形态不存在；`tpc-check` 关键字是引擎侧
     工具名，不属于语言知识）。
  5. 宏体形态的最后一处硬编码：`_expand` 的赋值后缀宏判定写死 `=`（ice40 端口
     默认值宏），现由语言包 `[macro_shape] suffix_leads` 声明（与 `continue_leads`
     是两条独立事实：前者=赋值后缀处置，后者=残缺续段预过滤）。`preprocessor/README.md`
     新增「形态清单」：哪些形态是声明列表、哪些是引擎机制。
  验证：全量 2046 passed / 7 skipped；新增 `tests/engine/lexer/test_comment_syntax.py`
  （5 例，三语言包声明面 + 缓存）、`tests/engine/preprocessor/test_markers.py`
  （12 例，含 yaml `#` 形态的还原与缺形态 fail-fast）、`test_check_suppress.py`
  补 4 例（yaml 形态声明驱动）、`test_macro_shape.py` 补 3 例（suffix_leads 声明
  面 + 锚形态随声明走）；真实语料三工具与改动前
  一致（diag 5548 → 5548、宏覆盖 86/135 = 63.7%、lint recall 33/33 / 误报 0）。

- **注释文本里的"伪指令"与注释定界符识别（两起真实语料事故）**：
  1. **块注释内的指令文本**：`scan_directives` 按行首前缀判定指令 → 注释里写
     `` `ifdef `` / `` `endif `` / `` `define `` 这类文本时被当真指令，行被丢掉、
     注释被截断成未闭合（实测 picorv32 风格片段输出 `/* note\nendmodule`、lint 报
     125 错）。现扫描前按**语言包声明的注释标记**推到行内/跨行状态：`kind = marker`
     （`/* … */`）产生跨行状态，其内部行不作指令识别；`kind = line`（`// … 换行`）
     行内终止，但其文本须跳过——否则 `//* group x`（ref_simcells.v 第 31 行）里的
     `/*` 会被当成块注释开启，之后 3783 行全被当成注释内部、指令集体失效。标记全部
     来自 `[comment] pairs` / `[capture]`（`_load_comment_markers`，按 rules_dir 缓存
     并登记入 `core/global_state.py`）。已知近似：字符串里的定界符形态会被当作注释
     标记；注释后**同行**指令不识别（非回归，锁在测试里）。
  2. **跨行块注释内部行的缩进**：渲染端对注释逐字输出（首行随布局缩进、内部行仍是
     源缩进，相对偏移随环境变化），缩进 pass 又按 `scope_depth` 重算内部行 ⇒ ` *`
     前的对齐空格被吃掉（版权头退化为 `* ...`）。现内部段（`is_comment_cont`）按
     注释自身惯例规范化：`*` 开头行对齐到**块首行缩进 + 1**（`*/` 同理），其余自由
     文本行按块首行平移量整体平移；规范化幂等。
  验证：全量 2025 passed / 7 skipped；新增 `tests/engine/preprocessor/
  test_directive_in_comment.py`（9 例）、`tests/languages/verilog/
  test_block_comment_indent.py`（11 例）；`eval_diag_baseline` 5548 → 5548、
  `check_macro_coverage` 86/135 = 63.7%、`eval_lint_accuracy` recall 33/33 / 误报 0
  均与改动前一致。

### Added

- **注释改动集的验证侧收口（覆盖率/对拍/隔离）**：
  1. 删死代码：`pratt_parser._is_own_line`（判定已收敛到 `_comment_trivia`，该函数
     无调用者——覆盖率逐行比对发现）。
  2. 补齐新增行未覆盖分支：`_transfer_comment_slots`（字典槽合并/去重/非容器槽/
     空源与空目标）、`_strip_leading_hardbreak`（Nest/Align/Prefix 下钻与全空折叠）、
     pratt 入口注释三支（行尾型→`leading`、独占行→`leading_own_line`、非 Node 原子
     →仅 sink 兜底）。
  3. 验证结果（仓库自查工具，非日常门禁）：增量覆盖率逐行比对 **新增行未覆盖 = 0**
     （7 个改动文件）；`eval_diag_baseline` 真实语料诊断 **5548 → 5548 无增长**；
     `check_macro_coverage` **86/135 = 63.7%**，与改动前（`c3041fe~1`）对拍**完全一致**；
     `check_test_isolation` **155 块 OK / 0 FAIL**；`eval_lint_accuracy` **recall 100%
     （33/33）/ 误报 0**（pratt 与 linter 共用，需回门）。

### Changed

- **语句内部独占行注释按结构落位（表达式注释让位闸门 + pratt 三分类）**：表达式
  内部注释原只分“行中/行尾”两类（`inline_after` / `leading`），独占行的那种被当成
  行尾 → 落到操作符同行；而语句**内部**（`=` 与右操作数之间）的注释根本到不了
  表达式入口（被 `prepare_production` 当规则 trivia 吞掉）→ 只剩锚点插值，而锚是
  清洁流里的下一个显著 token，可隔着折叠区几十行 ⇒ 落点必偏。
  现两道：
  1. `prepare_production` 新增**让位闸门**（`_comment_inside_current_rule`）：元素是
     pratt 规则调用、且注释是独占行、且**本产生式已匹配过元素**
     （`context.production_pointer > 0`，复活原死字段）且**注释前 token 属本规则
     匹配范围**（新字段 `context.production_start_ptr`，两者均入回溯快照）→ 不吞掉，
     留给表达式入口。列表项间/语句间的注释其锚属上一项（`context.production_pointer
     == 0`）→ 不受影响，仍由容器上浮为 Comment 迭代项。
  2. pratt 注释三分类：行中 → `inline_after`；行尾 → 右操作数 `leading`；**独占行**
     → 新增槽 `leading_own_line`（`node_renderer` 前置：块首尾各一硬换行、注释间
     单换行；行终止型由语言包声明驱动 `Renderer.comment_ends_line`，引擎不硬编码
     注释语法）。
  效果（darkriscv 实测）：需回插的 marker **2 → 0**（含 `wire HLT =`、`RMDATA =`
  两处，以及同因的重形态——`RMDATA` 的 `__MEXT__` 块原先被抬到**相邻语句**
  `wire BMUX =` 之后，现归位本语句）；输出与基线差异 37 行，全为“条件块/独占行
  注释独立成行且保源序”，纯空白行数与基线持平（15）。
  渲染端配套：`layout` 的 Concat 分支带**行状态**——当前行只余缩进且由非硬断行结束
  时，挤掉子项开头的 HardBreak（`_strip_leading_hardbreak`，防“父断行 + 注释首断行”
  叠出空行）；显式空行惯例（连续 `Break`）不受影响（既有断言
  `test_consecutive_breaks_kept_for_blank_lines` 保持通过）。
  验证：全量 1971 passed / 7 skipped；新增 `tests/languages/verilog/
  test_expr_own_line_comments.py`（语句内条件块位置 / 不漂到相邻语句 / 行尾注释不误升
  独占行）、`tests/engine/renderer/test_comment_slots.py::TestLeadingOwnLineSlot`。

### Fixed

- **注释落在内联展开规则上被丢（两处既存缺陷，零丢失闭环）**：`Init` 声明
  `inline = true`，其规则节点会被内联展开丢弃（`_try_inline_rule`）——挂在它
  `_comment_slots` 上的注释随节点消失：
  1. `wire a = /* c */ b;`（行中块注释，挂 `inline_after`，锚不在替身节点布局里）；
  2. `wire a = // why\n b;`（行尾注释，挂 `trailing`）。
  同形的 `assign` 语句（非 inline 规则）一直正常，故既有断言未拦住。
  修：① `try_inline_rule` 展开前把注释槽**迁移到替身节点**（`_transfer_comment_slots`，
  逐条去重、与目标已有槽合并）；② 行中槽在 inline 规则下改用 `inline`（节点文本前
  同行前置）语义——替身节点布局里没有锚 token；③ 迁移时把 `trailing` 转 `leading`：
  LineSuffix 在替身节点 doc 末尾落地会排在父布局 `;` 之前（输出 `wire a = b // why;`，
  `;` 被注释吞掉、语法损坏）。
  另修一处同类：`try_inline_rule` 文档串声称已把 Comment 子节点转发给父节点，代码
  从未实现（文档漂移）——改为描述实际的槽迁移行为。

- **注释通道路由判据收敛（含让位闸门）**：`_comment_trivia.py` 现同时是位置判定与
  路由判据的单点实现（新增 `comment_leave_to_expression` 纯函数），模块 docstring 列
  **注释通道分工与优先级**表（行中 / 规则内部 / 列表项间 / 首元素前 / 其余独占行）。
  `_production` 里的 `_comment_leave_to_expression` / `_is_line_only_comment` 两个本地
  包装删除（直接调共享实现）。

### Fixed
  1. **宏调用作右操作数时条件块整块消失**（本轮闸门引入的回归，已回门禁）：
     marker 挂到 `_verbatim_text` 直出节点后，直出路径只输出 `head_trailing`/`trailing`
     槽 → 前置槽不进渲染文本 → preprocessor 侧的条件块原文永远没有回插时机。
     修：直出路径同样输出前置槽（`_leading_slot_docs` 抽出共享，布局/直出两路径同源）；
     并**恢复锚点通道兜底**（挂树成功也登记，restore 对已在场文本跳过——不双份）——
     挂树失败/未被渲染时 marker 仍可回插。
  2. 注释位置判定**收敛为单点实现**（`parser/_comment_trivia.py`）：原 `_starts_line` /
     `_is_line_only_comment` / `pratt_parser._is_own_line` 三处实现语义不一致
     （`space` 子类型匹配范围不同、是否跳过注释不同）——同一输入可因路径不同得到
     不同分类。现生产侧与表达式侧共用 `prev_significant_index` / `is_line_only` /
     `is_midline`。
  3. 让位闸门从“仅独占行”放宽到“**非行中**”（`_comment_leave_to_expression`）：
     行尾型注释同样交表达式入口 → 右操作数 `leading`（原就地吐掉后只有锚点通道，
     普通注释不会回插）。
  验证：全量 1982 passed / 7 skipped（本条目后为 1990+）；darkriscv 输出不变（差异
  37 行、两通道待回插 0、纯空白行与基线持平、注释文本零丢失零重复）；新增
  `tests/engine/parser/test_comment_trivia.py`（13：含路由判据与快照往返）、
  `tests/e2e/test_comment_accounting.py`（3：真实语料零丢失 / 规则内部恰好一次 /
  兜底通道登记）、宏 RHS 条件块保全 / 内联规则注释保全 / 尾注不被推离语句行断言、
  直出节点前置槽断言。

### Fixed

- **列表项间条件块占位位置（端口表内 `ifdef` 组漂移）**：`_lift_gap_comments`
  原显式排除 tpc marker（判据 `"tpc:" not in text`），使列表项间的 marker 只能走
  "时域回插"的插值/锚窗口——而它的锚是清洁流的**下一个显著 token**（可隔几十行）
  → 落点必偏（darkriscv 端口表内 `ifdef __INTERRUPT__` 组漂到 `output IDREQ`
  之后）。现 marker 同样上浮为 Comment 迭代项：位置由结构决定，渲染器原样输出在
  正确项间，restore 就地替换不再依赖插值。optional 单值槽（`@PortList?`）仍不上浮
  （上浮的 Comment 会挤占唯一内容槽 → 端口丢失）。实测：需回插的 marker 5 → 2，
  端口表顺序与源侧一致；全量 1965 passed / 7 skipped（零回退），新增断言
  `tests/languages/verilog/test_render_restore_boundary.py::test_port_list_condition_block_keeps_source_order`。

### Changed

- **换行三态化（soft / 条件断 / 强制断 + 向上传播）**：`{ soft }`→`Line`（可折叠）、
  `{ break }`→`LineBreak`（组断开时在此断）、`{ hard_break }`→`HardBreak`（新增：
  恒断**且强制所在组断开**）。机制：`group()` 见 `HardBreak` 不生成 Union（直接
  返回 broken 形态）且节点保留 → 嵌套外层同样被强制（Prettier `propagateBreaks`
  的构造期实现）；layout 入口 `_drop_break_after_hardbreak` 挤掉 HardBreak 之后
  紧邻的条件断（避免空行，不动 `tail_break` 的显式连续 `Break`）；
  `_resolve_line_suffix` / `_insert_before_trailing_break` 接上 HardBreak。
  配置同步用 `tools/config_sites.py` 机械完成：17 处 `break = true` →
  `hard_break = true`（零 churn），并清 2 处死配置（module head 的 `ref` 遮蔽
  `group` → 端口表断行从未求值）。
  效果：项间/末项行注释吞码解决（声明驱动，引擎无语言知识）；端口表断开时收尾
  `);` 独占行（渲染器原生，不再依赖 formatter 补拆）。
  验证：全量 1965 passed / 7 skipped；`config_sites check` 0 漂移键 / 0 多键同层；
  改动 py 文件 Pylance 清零。

### Fixed

- **darkriscv 互操作回门禁（两条与条件块无关的真缺陷）**：sv-parser 接受原始
  源、拒 tpc 输出；探查（2026-09-17）证伪原归因「条件块嵌套位置精度」——实测
  157 个条件块占位中 118 个独占行精确命中 / 36 嵌套（多轮还原）/ 3 行内 /
  **0 丢失**，渲染文本原生 marker 116，仅 5 个被 production skip 吞掉需回插；
  关 formatter 后「还原文本 == 最终输出」（相似度 1.0000）。真因两条：
  ① **formatter 二次格式化还原原文**：`format_generated` 原在 restore **之后**
  跑，还原文本带回 `ifdef` 指令行与未展开宏引用，无预处理器的 Verilog
  formatter 把声明打散（`reg [31:0] IFPC [0:(2**`__THREADS__)-1];  // 注释` →
  `reg IFPC // 注释 [0:...]`，`;` 落进注释）。改为 restore **之前**格式化
  （此刻文本已把指令换成注释 marker，不含指令），还原原文按源侧原样输出。
  ② **收尾符被行尾注释吃掉**：renderer 把端口表收尾 `);` 与末项同行，末项
  行尾是行注释时 `);` 落入注释（`output [3:0] DEBUG // … :));` → 端口表未闭合）。
  join 原语改为：末项行尾注释属声明为「到行边界终止」型（语言包
  `[comment] pairs` 的 kind，经 `Lexer.line_terminating_comment_starts()`
  传入）时补硬换行——引擎不硬编码注释标点（`Renderer.comment_ends_line`）。
  ③ 同一批修的是 **column_align 尾注声明破坏**：插件内 ad-hoc 分词器把行注释
  按空白切词，`_parse_decl_parts` 取注释里最后一个标识符当 name → 重组出
  `reg  IFPC // … [31:0] state` 且丢 `;`（同组 ≥2 行触发对齐）。分词器改为
  注释（`//` 整行 / `/*…*/`）整段成单 token 并识别字符串字面量；单声明提取
  加尾注保护（保留原文，与多声明路径同约定）。
  验证：darkriscv tpc 输出被 sv-parser 接受（rc 1 → 0，format 开/关两种）；
  `_SVPARSER_INTEROP_SKIP` 取消 darkriscv 豁免；全量 1942 passed / 7 skipped；
  smoke 363；新增断言：`tests/languages/verilog/test_render_restore_boundary.py`
  （还原原文逐字/收尾符不被吞，两模式）、`tests/engine/renderer/
  test_comment_ends_line.py`（声明驱动判类）、`test_capture_runner.py` 两例
  （词表只来自声明）、`test_column_align.py` 六例（注释 token 化/尾注行跳过）。

### Changed

- **删除 `sync` 锚兼容路线（宏还原）**：锚 `mode` 现为三态（`line` / `inline` /
  `token`）。旧"同步词窗口消歧"（`mode="sync"`）只服务**无 `mode` 字段**的旧格式
  记录，而产出端（`_expand` 的三种锚 + `restore_condition_blocks` 的 cond 锚）
  **全部显式带 mode**——无产生者即删（判据 A3 过时 / A1 无引用）。连带删除：
  `_reverse._normalize_anchors` 旧格式包装、`_bridge._restore_sync_entry` 与
  `preprocessor.reverse` 配置声明、`grammar/verilog/base/_macro.toml [reverse]` 段、
  `grammar/verilog/tpc.toml` 的 `reverse = {...}` 声明、锚条目里已无消费者的
  `is_func` 字段（region 侧保留）。未知 `mode` 现在 **fail-fast**（静默跳过会让
  占位残留到输出——占位与原文的对应关系一旦错，输出就是错的）。
  背景：ADR-0017 决策 4 落地后，非空体宏已改走"宏区间 + 渲染 raw 拼接"，还原锚
  只剩空体宏/行级占位与条件块两支；本次清掉的是第三支的历史兼容壳。
  验证：全量 1925 passed / 8 skipped（含真实语料保真与宏还原门禁）；smoke 363。

- **草稿区能力提升为正式工具（`_drafts/` → `tools/`）**：把清理后仍被引用/仍可用的
  诊断能力从暂存区搬进正式位（草稿区随之为空，纪律仍见 `AGENTS.md` 文档放置速查）：
  ① `tools/dump_pipeline_state.py`（来自 `_drafts/probe_pipeline_state.py`）——打印
  管线语言状态（`_PIPELINE_SHARED` 条目里的 rules/mapping_cfg/schedules、
  `ConfigRegistry` 当前语言、已装载组件），`--pre grammar/c4` 复现"同进程先跑过别的
  语言"，是跨语言串味定案时的现场转储器。
  ② `tools/check_test_isolation.py` 增 `--hashseed-scan N`（吸收
  `_drafts/hashseed_probe.py`）：换 PYTHONHASHSEED 维度做"换跑法就变脸"检测；比对用
  **去计时**摘要，否则每个种子都因耗时不同被判漂移（实测踩过）。
  反之**未提升**（同能力已在 `tools/`，A2 双实现 → 草稿侧删除、引用统一）：
  `_drafts/probe_macro_anywhere.py` 对应 `tools/check_macro_coverage.py`（同一不变量
  与度量，ADR-0017 正文引用统一到后者）；`_drafts/probe_efficacy.py` 对应
  `check_gate_efficacy` 第 5 条变异。
  守护：`tests/policy/test_tools_diagnostics.py`（3 例，跑通 + 关键结论行）+
  `tests/policy/test_check_test_isolation.py` 扩到 16 例（含"必须能报出种子漂移"的
  正反例与去计时判据）；`docs/decisions/0017` 的引用路径同步为新工具。
  全量 1906 passed / 8 skipped；smoke 362；policy 109；两项门禁脚本全绿。
- **管线单元：语言包级声明 + verilog 显式时点编排（迁移第一步）**：单元机制
  （0.1.2 阶段 5-7）此前只有测试用过——声明只能放组件目录（**编排的归属错位**：
  组件是语言包的实现单元，不是编排单元，声明随组件目录存废而变），且文档写的
  `[[pipeline.units.x]]`
  形态与 loader 实际要求的 `[[pipeline.units]]` + `name` 不一致（照文档写即报错）。
  现：① 语言包根 `tpc.toml [pipeline] units` 与组件声明**两源合并**（同名 fail-fast；
  根 `[pipeline]` 段多余键不静默忽略）；② `grammar/verilog/tpc.toml` 声明 4 个单元
  （`analyze` → `slots` → `map` → `codegen`），与 transform 插件注册序**逐一对齐**
  （等价迁移）；③ `pipeline/README.md` 声明形态纠正为 loader 真实方言，并补
  "产物即数据路径"说明。验证：全量 1906 passed / 8 skipped（同基线）；
  `tpc trace` 可见 4 个显式时点（含产物/依赖回指）。
- **管线单元（阶段 2：c4 等价迁移 + 作用域校验）**：c4 语言包显式声明它**真跑**的
  单元（`analyze` → `asm`）——c4 无槽位声明、无 mapping 条目、规则无 `[X.transform]`
  配置，三个引擎插件单元在本语言下都是空跑（`slot_runner` 承接 0 槽位即不产出），
  故不声明；输出与迁移前**逐字节一致**（汇编 + `AsmProgram`）。另：插件单元加
  **语言作用域校验**（引用了不在当前语言作用域内的插件 → fail-fast；插件注册表
  进程级累积，按名字解析本身不区分语言）。守护：`test_language_units.py` 增至
  7 例（c4 声明 + 作用域违规）。
- **postpass 链收编进单元/契约体系（迁移阶段 3）**：analyzer 的 post-pass 链
  （typed_ports 展开、inst_check/width_check 等检查）此前是**第二套隐式顺序**
  ——顺序只由组件名排序碰巧成立，两条真实依赖仅写在注释里（`_expand_ports` →
  `_check`、`hier_check` → `width_check`）。现：
  ① 声明面改表形态 `[[analyzer.postpasses]] + run`，加可选 `produces`/`requires`
  （字符串列表形态撤销，9 个组件同步迁移，无双方言）；
  ② **链内契约**：`requires` 须由更早环节 `produces` / `scope` / 链启动时
  `context.extra` 提供，否则 fail-fast——两条真实依赖已声明（`resolved_ports`、
  `hier_member_table`），不再靠组件名排序碰巧对；
  ③ 每环执行进管线**单元轨迹**（`artifacts.postpasses`：名字 + 本轮诊断数，含链尾
  L1 规则执行器）——链也是时点，`tpc trace` 可见。
  与 transform 单元契约的区别：postpass 产物写在符号表/context 上，引擎不懂语义，
  故只校验**时点可达性**（不核实物化）。守护：`tests/engine/analyzer/test_postpass_chain.py`
  （8 例：真实契约与顺序、表形态与 fail-fast、契约违规/满足、轨迹记录）。

### Fixed

- **`setup_grammar` 静默吞掉组件装载失败**：`parser/__init__.py` 的组件装载段包在
  `except ImportError: pass` 里——装载期任何 ImportError（插件模块循环导入/部分
  初始化等）被静默吞掉，语言作用域停在上一语言、组件规则整段缺失。实测：全量
  并行跑时 `test_plugin_scope_excludes_other_language` 失败过一次（切到 verilog 后
  c4 的 `AsmGenPlugin` 仍在 `active_plugin_classes()` 内），复跑不复现——症状与该
  静默路径一致（未能证明因果，但该失败模式已被消除）。现改为 **fail-fast**
  （不吞异常），与「配置加载 fail-fast、不静默降级」硬约束一致。
  守护：`tests/engine/core/test_language_switch.py::
  test_component_load_failure_is_not_swallowed`（桩掉装载 → 异常须逃出）。
- **契约只是装饰：`produces`/`requires` 未真正成为数据路径**：`ConfigDrivenTransform`
  声明的 `requires=["mapping_tables"]` 由引擎校验，但它实际靠**扫同 transformer 的
  兄弟插件**拿映射表——按契约把 map/codegen 拆成两个时点（各自 transformer 实例）
  后映射表拿不到 → typed_ports 展开全丢（16 个测试红）。现：`note_produced` 登记的
  产物同时发布到调度累积的**产物通道**（`PassState.productions`），消费方按契约名
  取用（跨单元成立）——删掉兄弟插件扫描，单一数据路径。另：被开关跳过的单元不再
  参与契约校验/物化核验（跳过 = 无产物是预期，非配置错）。
  守护：`tests/engine/pipeline/test_language_units.py`（5 例）；
  `tests/languages/verilog/test_mapping_origin.py` 的 trace 断言改为按插件名聚合
  （不再假设只有一条 transform 条目）。
- **语言作用域跨语言串味（"幽灵 flake"的机制）**：同进程「先跑 c4 管线 → 再跑
  verilog」时 verilog 输出变**空**且 `success=True`（保真度 0.9925 → 0.0000），
  实测于 HEAD，不是历史遗留。三处语言作用域状态跨语言累积，任一处都能让别的
  语言的结果变样：
  ① `GrammarRulesRegister.get_default()` 只增不清 → 后一语言的 rules 字典混入
  前一语言规则**且顺序靠前**，而 `RuleSelector.get_block_rule()` 取"第一个匿名块
  规则" → **根规则被前一语言夺走**（verilog 源码按 c4 的 `Program` 解析）；
  ② `transform.engine._plugin_registry` 累积且 `AstTransformer` 会实例化并执行
  **全部**登记插件 → 别的语言的 transform 插件参与本语言管线（`AsmGenPlugin` 的
  根守卫恰好被 ① 造成的 `Program` 根通过 → AST 被换成 `AsmProgram`）；
  ③ `_PIPELINE_SHARED` 缓存组件后，切回**已缓存**语言时 `ConfigRegistry`（进程级
  "当前语言"）仍停在别的语言上 → 该语言的 token 类别/原子映射是别人家的
  （c4 → verilog → c4 时第二次 c4 解析截断）。
  修法（原则：语言切换 = 重建语言作用域）：`GrammarRulesRegister.begin_language()`
  切语言即重置规则表并按路径规范化去抖；`plugin_loader._active_components` 在装载
  时固化语言作用域 + `transform.engine.active_plugin_classes()` 按它过滤插件
  （引擎插件恒在）；`pipeline._ensure_language_config()` 每次确认配置停在当前语言。
  守护：`tests/engine/core/test_language_switch.py`（7 例：双向 + 来回切换的端到端
  保真度、规则表无残留、根规则归属、插件作用域、配置声明随语言）；门禁有效性进
  `tools/check_gate_efficacy.py` 清单（关掉重置即变红，实测 ratio 0.9925 → 0.0000）。
  订正：`core/global_state.py` 的 `ACCUMULATED` 表原写"跨语言多出来的条目不被引用"
  ——**已被证伪**（插件是全部实例化并执行），安全来自应用侧作用域过滤而非注册名限定。
  全量 1900 passed / 8 skipped；单进程串行全量 1900 passed / 8 skipped（443s，
  正是该 bug 赖以发作的"多语言同进程"场景）；`check_gate_efficacy --only 5`
  如期变红（关掉 `begin_language` 即红）。

### Changed

- **测试隔离 L4：进程级隔离对照**：新增 `tools/check_test_isolation.py`——把选中集
  切块（默认每文件一块）在**全新解释器**里各跑一遍，再与**单进程共享档**对照，
  把"换一种跑法就变脸"分成两类并指名到位：只在共享档失败 = 进程内状态泄漏/顺序
  污染（补 `core/global_state.py` 登记表或改 fixture 作用域）；只在隔离档失败 =
  该用例隐式依赖同进程里其它文件留下的状态。**不用 `pytest-forked`**：它走
  `os.fork`，Windows 没有（实测 `hasattr(os, "fork")` 为 False），CI 矩阵含
  windows-latest——故用子进程实现（跨平台、零新依赖）。附带 `--granularity
  file|test`（单用例一进程 = 最强隔离）、`--jobs`、`--random-hashseed`。
  nightly 加快速层对照档；工具不进日常门禁（全量要起上百个解释器）。
  自保用例 `tests/policy/test_check_test_isolation.py`（13 例，含"真能报出差异"
  的端到端负例与路径/省略形态判据）。验证（全量 1901 用例，两次独立跑一致）：
  隔离档 144 块 **0 失败（~2 分钟，jobs=16）**，单进程共享档 1893 passed /
  8 skipped（~9 分钟），两档一致——即全库已无进程内状态耦合（幽灵 flake 那一类）。
- **测试隔离 L3：顺序可控（把偶发变必现）**：①`pytest addopts` 显式
  `--dist loadfile`（一个文件固定在同一 worker，模块级 fixture 与"安装态按模块
  还原"语义绑定在同一进程）。②`tests/conftest.py` 新增零依赖的顺序随机化 hook
  ——`TPC_SHUFFLE_SEED=<int>` 做**文件级**乱序（种子固定 → 失败可复现；单用例级
  乱序不在范围：模块/session 级 fixture 在其作用域内合法拥有安装态）。③CI：日常档
  固定 `PYTHONHASHSEED=0`（PR 加乱序 smoke 档），nightly 加全量乱序档 + 哈希
  种子每进程随机的巡检档。守护：`tests/policy/test_order_shuffle.py`（同种子同序 /
  不拆散文件 / 未设环境变量不动序）。
- **顺序巡检当场拓出一条真实边界（登记表新增 `ACCUMULATED`）**：`--dist loadfile`
  下的默认序曾 5 例 c4 失败——语言注册面（插件/原语注册表）**不能**按模块还原：
  写入者是模块导入副作用，而 `plugin_loader` 缓存组件模块（sys.modules 命中即不重
  exec）→ 还原后缓存命中不重注册 → 已装载语言拿不到自己的插件（`AsmGenPlugin`
  不生效，transform 退化为 `Program`）。现登记为“只增不还原”表并写明理由；同时
  删掉随之失效的 `keywise`/`prefix` 还原策略（无使用即删）。全量默认序 1880
  passed / 8 skipped；乱序档 seed 1/2/3 均绿；串行+乱序（languages+engine）
  1665 passed。
- **测试隔离 L2：外部资源隔离**：①中间产物落盘改为**只认显式 `out_dir`**
  ——删掉 `pipeline` 里"input_path 含 samples 就写回样本目录"的嗅探：测试并行时
  多 worker 对同一样本并发写同名 gen/ast/symbols（撕裂读 → 偶发保真抖动），且把
  测试语料布局约定藏进了正式包；now 测试调用零仓内写入（实测 e2e 全跑后
  `tests/e2e/samples/**` 无新文件），samples 约定归 `tests/e2e/run_pipeline.py`
  测试 CLI。②`_PIPELINE_SHARED` 缓存键补 `ext_dirs`（原只键 rules_dir，同语言
  不同 ext_dirs 会静默复用组件与规则）。③保真度缓存条目改**内容键控**
  （`{sha, fidelity}`；样本源改过即不算基线），消除陈旧基线造成的幻影 drop。
  ④`check_hardcode` 新增规则 5 [gate]：测试文件禁 `os.chdir`（进程级 CWD 泄漏
  → 并行 worker 互踩相对路径；用 `monkeypatch.chdir`）。全量 1872 passed / 8 skipped。
- **测试隔离：全局态登记表 + 覆盖门禁 + 两层还原（L1）**：`core/global_state.py`
  的覆盖从手工表 → 五张登记表（`TRACKED` 测试级 / `INSTALL_STATE` 语言安装态 /
  `CONTENT_ADDRESSED` / `CONSTANT` / `COVERED_ELSEWHERE`）+ 自动发现模块级/类级
  可变容器，`tests/policy/test_global_state_coverage.py` 断言发现集 ⊆ 登记集
  （新增全局态不登记即红）。`restore()` 分两层：测试级每测试还原（派生缓存、
  共享上下文、深度计数器、注册表新增项），安装态每模块还原（pratt 安装态、
  插件/原语注册表——逐测试擦除会打断模块级 fixture 装载的语言）。每测试还原后
  立即 `assert_clean` 比对基线指纹。过程中的两处修正：keywise 还原改为
  "去掉新增 + 补回被删基线键"（原先只删不补，会把语言重注册清掉的基线项永久
  丢失）；快照前预热全部登记条目的按需导入（导入有注册副作用，否则快照内容
  依赖触发顺序，快照与还原读到不同集合）。全量 1862 passed / 8 skipped。
- **阶段 9 终验（0.1.2 收尾）**：覆盖率门禁 **86.81%**（≥ fail_under 80；
  串行 `-n 0` 全量 1851 passed / 8 skipped）；e2e 102 组 **FAIL 0**（66 OK /
  36 预期 ERR）；lint recall 33/33、零误报；eval_check_accuracy recall 100%
  （FP 0）；`check_hardcode --strict-doc --strict-import` 与 `check_doc_refs`
  全绿。终验抓到一处潜伏门禁违规并修复：`main.py` 的 `Doc:` 头在 api.md
  删除时遗漏重指（`R3` strict 升 gate 后暴露）——补 `Doc: README.md`。
- **自定义规则范例（0.1.2 阶段 8 / T2 收尾）**：新增 `grammar/verilog/plugins/
  checks/custom_rules_example/`——两条规则各走一条路径的可运行范例（EX001
  非 ANSI 端口声明=**postpass 路径** / EX002 parameter integer 类型提示=
  **handler 路径**），`default=false`（默认关，对默认诊断面零影响）；配套
  对照样本（pos×2 + neg×1）与 `focus` 条目（评测启用，recall/误报面纳入门禁）；
  目录 README 含照抄四步与启用方式；`checks/README.md` 双路径节加指引。防误报
  回归：函数/任务子树跳过（先例 `_fill_body_ports`——旧式函数参数与模块体
  端口同节点名）。测试 `test_custom_rules_example.py`（7）。
  \* T2 批判式吸收三态落定：排版卫生族已入（ST001-003）；空格规范族**不采纳**
  （与 formatter 列对齐协调成本 + 品味性强）；ANSI 头/参数 2-state 走范例
  路径（本条目）。
- **排版卫生族（ST001-003）+ 诊断阻断性（0.1.2 阶段 8 / T2 首项）**：linter 层
  解析前行级检查——尾随空白（ST001）/ 制表符（ST002）/ 行长超限（ST003，上限
  引用语言包 `[style_check].max_line_width`，与 formatter 折行阈值同值约定）；
  子检查各自开关，未声明该段语言包不注册。配套引入 `LintDiagnostic.blocking`
  （区分"语法阻断"与"卫生提示"）——ST 为 blocking=False/severity=2：**不跳过
  语义分析**（structure）、**不计失败退出**（checker / lint CLI） 、**不截断
  管线**（_stage_lint 按码汇总一行，不逐条）。真实语料基线显式更新（+5407 条
  ST，真诊断非误报；semantic 面持平）。测试：`test_linter_style.py`（11）+ 
  checker 非阻断语义用例（≥=2 退出码/语义不跳）。
- **trace 报告时间轴呈现（0.1.2 阶段 6 收尾切片）**：`tpc trace --html` 页面
  重排为"管道条 + 单列左轴"——顶部**执行管道条**（单元节点链，箭头标上游
  `produced` 流；节点/卡片锚链互通）；卡片区左侧一条轴 + 轴节点（按 kind
  着色）；卡片新增**依赖行**：`requires` 名机械回指上游产出该名的单元（名字
  等值匹配，纯数据不认识语义；无上游记录时只显名字）。trace 条目补
  `requires` 字段（非空才带）。报告固定浅色皮肤（`color-scheme: light` + 显式
  body 底色）：此前深色模式浏览器会把背景/文字反转，与浅色设计的 badge/表格
  元素混搭。测试 `test_trace_report_html.py`（+4）。
- **pass 契约校验切片 2：物化核验 + 形状（0.1.2 阶段 7 收官）**：`produces`
  不再按声明空转——单元执行后核验**物化登记**（生产方在 `process` 内
  `note_produced(name, obj)`）：声明未物化 / 物化未声明均 fail-fast（声明 =
  物化，双向一致）；可用集按**实际登记**并入（来源核验）。可另声明**形状**
  （`register_plugin(shapes={"名": {"type": "dict"|"list", "non_empty": bool}})`
  ——注册期 fail-fast 校验 spec，执行后机械核验对象）。trace 条目带 `produced`
  （文本与 HTML 报告同显）；跳过单元不再读到上一单元的 transformer
  （`_run_pass_transform` 入口重置，核验/自述来源可靠）。声明对齐：
  `asm_gen.codegen` 去除未物化的 `extra_asts` 声明（实际产出 = 替换 AST 主输出）。
  测试 `tests/engine/pipeline/test_contract_check.py`（+8，共 13）。
- **插件单元实例化参数（`params`，0.1.2 阶段 5b-3b）**：`[[pipeline.units.*]]`
  的 `params` 表 = 插件**构造器关键字参数**（执行层 `cls(**params)`）——同一插件
  可注册为多个实例（各自参数与时点，如 `SemanticMappingPlugin` 的 `raw_config`
  覆写）；加载期按构造器签名核验（`inspect.signature` bind），未知参数 / 缺必需
  参数 → fail-fast；槽位 / 内置 / handler 单元声明 `params` → fail-fast。trace
  条目带 `params`（可视化）。测试 `tests/engine/pipeline/test_unit_params.py`。
- **诊断行号回源（check 链，P3.3 (a)）**：`scan_directives` 新增第 7 返回值
  `clean_to_raw`（行+行号对账本：续行合并取段首行、条件压缩按实际归属、include
  拼接行 `None` 不可映射），与 `expand_tokens` 的展开级映射两级复合后经
  `FileResult.line_map` 进入 `_syntax_diag`/`_semantic_diag`（含 related）换算——
  宏/条件编译文件的诊断行号从“展开后行号”回到**原始源行号**；不可映射时保守
  回退展开行号（不给错误回填）。管线 lint 日志行号同步两级回源。实测：7 处
  调用点同步；`ifdef` 压缩/续行合并/include 三类形态断言全绿。
- **诊断宏归因（check 链，P3.3 (b)）**：`_expand_source` 把宏区间表
  （`expand_tokens` semantic 产出的字符区间）换算为**展开行区间**（+ 宏调用
  原始行）存 `FileResult.macro_regions`；`_syntax_diag`/`_semantic_diag` 对落在
  宏展开区间的诊断加 `"macro": "<NAME>"` 字段——宏体触发的诊断可按宏归类/
  抑制，调用行锚点供 IDE 跳转。未展开/顿路径无表 → 不产字段。
- **解析侧改吃真展开**（2026-09-13）：解析输入由保真锚形态切到 `expand_tokens(semantic=True)`
  的展开文本——语法结构直接由展开文本判定（类型位宏 `` input `NT d `` 不再需要任何
  语法槽位），宏调用原文由**区间表 + `_verbatim_text`** 挂在覆盖节点上供渲染还原
  （引擎级 raw 拼接，语言包零宏知识）；锚机制收缩为空体宏/行级占位，另保留
  `parse_raw=True` 可选路径。实测：曾失败的 4 个真实语料文件（ice40 / picorv32 /
  darkriscv / tv80）全部解析通过；宏位置覆盖 **37% → 63.7%**（`tools/check_macro_coverage.py`，
  86/135）；`test_macro_type_slot.py` 6 个 strict-xfail **全部翻正**；e2e 102 组 FAIL 0。
- **pratt 行首运算符续行**（`parser/pratt_parser.py` 中缀循环）：原“遇 newline 非运算符
  自然 break”把 `ALL0\n + ALL1` 截在 `ALL0` → linter 语句匹配要求 `;` 却遇 `+` →
  整句判不出（`phase-unrecognized`，无宏也触发）。修法：跳过 trivia 后若下一个显著
  token 是**中缀**运算符则续行（行首中缀运算符不可能是语句起点；不变量有专测
  `tests/engine/linter/test_multiline_continuation.py`）。实测：check 路径 darkriscv
  `syntax 26 → 0` 且**语义阶段首次跑通**（+9 条 UN001 真诊断，源码自带 `// unused`
  注释佐证；诊断基线 132 → 141，真诊断增长）。
- **linter 输入改真展开 + 诊断基线增计 syntax**：`ctx.lint_source`（语义展开）供 linter
  校验真语法结构；`eval_diag_baseline.py` 原先只统计 `semantic`，导致 linter 侧误报面
  无门禁（darkriscv 那 26 条长期无人统计即此因）。

### Removed

- **语法文件中的宏知识全部撤销**（ADR-0017 决策 2/3 推翻重定，2026-09-13）：
  `[Identifier.parser]` 的 `macro.call` 备选、`[MacroCall.parser]`/`.parser.node`、
  `TypeSpec`/`TypeSpecNoReg` 首元素的 `@MacroCall` 槽位，全部删除；
  展开锚形态回退为**普通标识符**（`__tpc_marker_<salt>_<n>`，保留命名空间 +
  盐 + 序号 + 还原唯一性守卫不变）。linter 的锚窗口拼接随之删除（锚不再是宏
  token，拼接已无对象）；`_stage_lint`/`_rewrite_marker_nodes` 回到单形态。

  **依据（实测）**：宏位置本质上是**文本任意**的，逐槽位声明补不齐——新增的
  位置覆盖自查不变量（任一 token 换成等价宏、格式化输出必须不变）：逐槽位声明
  **54/135 = 40%**，撤销语法声明后 **50/135 = 37%**，即整套槽位机制只买到 4 个
  位置；且 layout 自带字面量的槽位（如 range 子槽的 `[` `]`）会多套一对（静默
  错渲染）。新方向 = **外层展开 + 渲染侧 raw 拼接**（宏调用视为不可拆原子文本）。
  验收标尺 `tools/check_macro_coverage.py`；类型位需求以 6 个
  `xfail(strict=True)` 钉在 `tests/languages/verilog/test_macro_type_slot.py`。

### Fixed

- **多声明器重组漂移（formatter，P1.5 缺陷）**：`column_align` 重组多声明行时，
  后续声明符不再逐单元补 `width+1` 列前缀（`_join_semantic(pad_columns=False)`），
  改 `, ` 单分隔紧跟——名字列不再随上一单元长度累积漂移；首单元仍参与列对齐
  （ref 基准风格 `reg dout, din_0, din_1;`，与 Verible 单行多声明形态一致）。
  实测真实语料漂移（`,\s{4,}<ident>`）**226 → 0**（simcells 146 / cells_sim 46 /
  picorv32 28 / tv80 6；更严格的 `,\s{2,}` 同为 0）。门禁补
  `test_column_align.py` 重组输出断言（旧用例只测提取，e2e `_strip_all` 抹空白
  天然失明）；全量 1814 passed / e2e FAIL 0 / 差分 136 文件 0 findings。
- **linter choice 匹配的 trivia 泄漏**（`linter/checkers/matcher.py::_match_choice`）：
  试分支时起点会前移到首个非 trivia token，失败返回却沿用了这个**内部起点**，
  于是被跳过的 trivia 被上层当成"已消费"（`seq`/`repeat`/`optional` 的 `j > i`
  判据全部据此误判），下游 token 流错位。表现为：任一规则 production 含 token
  备选（如 `Identifier` 声明 `["id|macro.call"]`）后，真实代码在**宏无关**的端口
  列表上开始误报（`module m (input clk, output data);` → 2 条 `phase-statement`，
  块头匹配提前收尾、端口项被当语句）。修法：失败路径返回原位置。
  实测：536 例 linter+verilog 回归全绿；全量 1774 passed。

### Added

- **渲染器引擎级 raw 拼接钩子**（ADR-0017 决策 4 切片 ② 的一部分，已就位未启用）：
  节点带 `_verbatim_text`（引擎标记）时整体直出该文本——不走布局、不遍历子节点，
  宏调用于是成为不可拆的原子文本；**语言包对宏零知识**（规则在引擎）。
  另修：语义展开时宏体**末行含行注释**则拼接末尾补一个换行——不补的话宏调用
  **同行的后续 token**（`;`）落进注释被吞，语句丢分号（darkriscv 实测 81 条
  `phase-unrecognized` 的同一根因）。
  测试 `tests/engine/renderer/test_verbatim_node.py`（3 断言）+
  `test_macro_regions.py::test_body_trailing_comment_gets_newline`。

- **宏区间表**（ADR-0017 决策 3 切片 ①）：`expand_tokens(..., semantic=True)` 第三
  返回值 = 每条被铺进文本的宏调用一项，含**源区间**（`src_line`/`src_col`/
  `src_end_col`）与**展开结果字符区间**（`offset`/`end_offset`，含宏体、名字、
  是否带参）。它是外层处理宏的单一事实源：渲染侧 raw 拼接与诊断宏归因都靠它
  定位"哪些内容来自哪条宏"。用字符偏移而非行/列——宏体含换行会让展开结果行数
  变化，偏移天然稳定。默认（渲染路径）为空表，与锚还原不混。
  三处调用面同步改为三返回值。测试
  `tests/engine/preprocessor/test_macro_regions.py`（单行/类型位/含换行体/带参宏/
  同行双宏偏移累加/非语义模式空表/非活跃分支不登记，10 断言）。

- **宏展开锚名协议**（`core/token_protocol.py`）：锚名 = 保留前缀 `__tpc_` +
  `marker` + **源文本 sha256 盐** + 序号（不用内置 `hash()`：PYTHONHASHSEED 会
  破坏跨进程可复现）；还原侧加**唯一性守卫**（命中次数 ≠ 1 则不回插，保留占位
  可见，不静默错还原）。锚仍是**普通标识符**形态（语言包不认识宏）。
  测试 `tests/engine/preprocessor/test_anchor_protocol.py`。

- **`tools/check_macro_coverage.py`（宏位置覆盖自查）**：不变量 = "把任一 token
  换成等价宏（`` `define M <原 token 原文> ``），格式化输出必须不变（宏调用原文
  原样保留、不被展开/重排）"，输出覆盖率 + 失败面（按 token 类型）。把"宏的位置
  支持"从"声明了哪些槽位"变成可测数字（ADR-0017 决策 3/4 的验收标尺）；不进
  日常门禁，人工/按需跑。

- **语言包↔引擎契约（`[engine] api`，缺口队列 ⑤）**：`grammar/<lang>/tpc.toml`
  可声明 `[engine] api = "0.1"`（该包构建所依据的引擎 API 线）；引擎 major.minor
  不匹配即**加载 fail-fast**（`ConfigError`），替掉"升级引擎后包静默坏掉"的隐式
  契约。未声明 = 不校验（纯增量）。双入口校验（`_load_meta_declarations` 的
  `load_all`/`resolve` 路径 + `core/define.py::_load_tpc_meta` 的 import 期默认包）；
  该段不进配置中心。内置 verilog/c4/yaml 三包均声明；引擎 minor 变更时
  `test_engine_compat.py` 的"三包声明当前线"断言会失败（故意，逼一次复核）。
  实现 `core/engine_compat.py`，契约文档 `core/config_lifecycle.md`。

- **parser token span 绑定（P3.1 / 0.1.2 阶段 0）**：解析成功的规则节点/块节点挂
  `_tok_span`（半开 `[start, end)` token 流索引；`core/define.py` 声明 +
  `parser/_production.py` try_plain_rule / try_block_rule 成功返回前写入），供
  增量重解析（P3.2）结构对齐定位。下划线前缀 = 引擎元数据，不进 dump/序列化。
  测试 `tests/languages/verilog/test_tok_span.py`（区间合法 / 父子包含 /
  dump 排除 / 回溯确定，4 断言，标 smoke）。

- **宏体形态分类器（0.1.2 阶段 1）**：`preprocessor/macro_shape.py` —— 宏体放进
  语言包声明的四类最小语法上下文（`[macro_shape].wrappers`：stmt/decl/expr/port）
  包裹解析：能完整解析 → 完整单元（语句/声明/表达式）；全失败 → 残缺片段；另配
  `continue_leads` 首 token 续接预过滤（防 `= 1'b1` 被端口模板误收）。模板与续接集
  是**语言语法知识**（进 grammar TOML），引擎只做通用包裹解析。本阶段只产出分类，
  不接消费点（阶段 2 由 MacroCall 节点消费）。测试
  `tests/engine/preprocessor/test_macro_shape.py`（16 样本 + 配置驱动断言，标 smoke）。
  原型 `tests/_proto_macro_hygiene.py` 已转正删除（验证使命完成）。

- **宏边界节点化（0.1.2 阶段 2）**：parse 后按锚表把宏调用的 `tpc_marker_N`
  标识符改写为 **MacroCall 节点**（带 `_macro_name` / `_macro_marker` 元数据），
  宏边界在 AST 中结构化可见——P3.2 增量 diff / P3.3 双向映射的前提。语言包声明
  `[MacroCall.renderer.layout]` + `[MacroCall.analyzer]` 与 Identifier 对齐，
  渲染与分析**行为零变化**（输出逐字节不变）。测试
  `tests/languages/verilog/test_macro_call_node.py`（4 断言，标 smoke）。
  注：宏体子树进节点 + 渲染改源区间还原 = ADR-0016 终态，归阶段 4。

- **宏处理单一来源门禁（0.1.2 阶段 3）**：侦察确认 linter（`linter/scanner.py`）
  与管线（`pipeline/__init__.py`）调用**同一**
  `preprocessor._expand.expand_tokens`，形态配置由 `preprocessor/macro_shape.py`
  单一读取语言包 `[macro_shape]`——无第二实现/副本。新增
  `tests/engine/linter/test_macro_sync.py` 锁定（函数对象同一 + 配置单源 +
  已定义宏不误报 / 未定义仍报），防未来路径私自复制实现（标 smoke）。

- **宏调用源区间元数据（0.1.2 阶段 4a）**：展开阶段记录宏调用在**源文本**中的
  位置（`_expand.py` token 锚加 `line`/`col`/`end_col`），宏边界节点化时挂到
  MacroCall 节点 `_src_span`（`core/define.py` 声明）。与 `_tok_span`（展开后
  token 流区间）互补 = ADR-0016「raw 源区间权威」的节点级表达（P3.3 双向映射
  基础）。测试加“源文本切片 == `` `NAME ``”强校验。

- **宏体子树提取器（0.1.2 阶段 4b-1）**：`preprocessor/macro_shape.py` 新增
  `build_parse_ast` + `extract_macro_body`——按语言包
  `[macro_shape.wrappers.<key>]` 的 `pick`（节点名路径）+ `skip_head`/`skip_tail`
  钻取宏体对应节点，合成 `MacroBody` 包装节点；wrapper 配置升级为嵌套表
  （`tpl` + 提取路径），提取路径属语言语法知识（进配置），引擎只做通用钻取。
  测试 `tests/engine/preprocessor/test_macro_body_extract.py`（4 形态 + 多单元 +
  残缺回退，标 smoke）。**尚未接入管线**（挂载到 MacroCall 节点 = 4b-2）。

- **宏体子树挂载 + 探测静默（0.1.2 阶段 4b-2）**：完整单元宏的展开体子树
  （`MacroBody`）挂到 `MacroCall._macro_body`——**不占 children**（`Node.iter_children`
  显式排除）→ 渲染与语义遍历均不进入，**行为面零变化**（全量逐字节不变）。
  `Parser` 新增 `silent` 开关（签名末位，向后兼容）：探测性解析（形态分类 /
  宏体提取）全静默（含失败报告），不污染宿主日志与“真实语料无 WARN”门禁。
  测试加“子树已挂 + 不占 children”断言。剩 4c：渲染改区间/源区间还原。

- **宏渲染走 raw 源区间（0.1.2 阶段 4c，阶段 4 收口）**：`MacroCall` 挂
  `_macro_fragment`（= 源区间切片，与 `_src_span` 对应），渲染声明改为节点直接
  输出该字段——替代“marker 占位 + 事后文本替换”（ADR-0016「渲染直接走源区间」）。
  事后替换**保留为安全网**（对已节点化的 token 锚找不到 marker → 静默跳过；
  未节点化场景仍可救回）。全量 1611 逐字节不变。**阶段 4（管线后端适配）完成**。

- **加工单元实例 + 统一时点生成（0.1.2 阶段 5a）**：新增 `pipeline/units.py`——
  `UnitInstance`（`type`/`impl`/`after|order`/`params` 显式带参数配置品类，
  ADR-0015 §1）+ `parse_units`（fail-fast 校验）+ `assign_points`（**时点由调度器
  统一生成**：order 钉号 / after 推导 / 声明序填空，与 pass 级同构；冲突 / 环 /
  未知引用→诊断）。支持同变换多实例（不同时点/参数）。**纯新增，零执行变化**
  （执行接入 = 5b）。测试 `tests/engine/pipeline/test_units.py`（14 断言，标 smoke）。
  连带：`check_hardcode` TOKEN_ALLOWLIST 加 `impl`（配置字段名，非语言知识）。

- **加工单元声明面（`[pipeline] units`，0.1.2 阶段 5b-1）**：`core/plugin_loader`
  新增 `pipeline.units` 声明加载（项 = `{name, type, impl, after|order, params}`，
  显式 + 带参数；缺 name / 非表 → fail-fast）+ `get_pipeline_units()` 汇总；
  `pipeline/units.py` 新增 `build_unit_sequence`（声明 → 有序单元序列，时点由
  调度器统一生成）。**执行接入（替代 pass 序列）= 5b-2**。

- **单元序列接入调度（0.1.2 阶段 5b-2，粗粒度）**：`schedule.build_unit_schedule`
  把 `[pipeline] units` 声明构建为**可执行单元序列**（`PassDecl`——与 pass 执行层
  同构，直接复用 `_run_schedule` 分派）；`impl` 约定 `builtin.analyze` /
  `builtin.transform` → 内置执行器，其余 → 加载时解析的 handler（check 类）。
  `_ensure_shared` 接入：units 声明存在时**替代默认 schedule 的 pass 序列**
  （统一调度：analyze / transform / check 同列）。**粗粒度限定**：
  `analyze`/`transform` 单元各至多 1 个（内置黑盒执行器不可重复跑），多实例限
  `check` 类——同一变换多时点需细粒度拆解（5b-3）。无声明时走原路径（零回归）。

- **单元执行轨迹（0.1.2 阶段 6 可视化切片）**：`PassState.trace` 逐单元记录
  `{index, name, kind, extra_added, extra_keys}`（谁在哪个时点跑了、向黑板
  `extra` 写了哪些键）→ `ctx.result["trace"]`；`sym_json` 指定时同目录落
  `trace.json`。ADR-0015 §2「时点 = 可视化断点」首项落地（配对隐式，但产物可视）。

- **映射表来源追踪（0.1.2 阶段 6 可视化）**：`resolved_ports` 行携带 `origin`
  （展开链 + 源端口锚点，`spi.slave > invert(spi.master) > #miso`；嵌套叠加
  `nested(实例:类型.角色)`/`rename(实例)`/`opposite(...)` 段）→ SemanticMappingPlugin
  旁路收集 → 插件 `describe()` 自述 → trace 条目 `artifacts`（落 `trace.json`）。
  回答「这行从哪来」；引擎只认协议字段名与自述容器（`TransformPlugin.describe()`
  默认空 = 可选能力），不解析段语义。测试 `tests/languages/verilog/test_mapping_origin.py`。

- **插件身份面 + 插件级单元（0.1.2 阶段 5b-3a）**：插件以限定名注册（引擎插件 =
  类名，语言插件 = `<组件名>.<单元名>`，如 `typed_ports.bridge`）；
  `transform.engine.get_plugin_index()` 查询，索引同名首胜（`_plugin_registry`
  执行序语义不变）。`[pipeline.units.*].impl` 新增第三形态**插件限定名** → 该单元
  只跑该插件（同一变换可多时点）；未知插件 / 非 transform 类型 / `params` 非空
  均 fail-fast。序列限定改为：`analyze` ≤1；`transform` 要么单个
  `builtin.transform`，要么全为插件单元（混用重复执行 → fail-fast）。未声明
  units 的语言包零行为变化。测试 `tests/engine/transform/test_plugin_index.py`、
  `tests/engine/pipeline/test_unit_plugin_schedule.py`。

- **插件契约校验（0.1.2 阶段 7 切片）**：插件注册时声明 `produces` / `requires`
  （显式平铺名列表，**不含时点**——时点归管线配置，ADR-0015 §1/§3 2026-09-11
  作者定调）；调度层在**时点边界**（单元执行前）核验 requires 是否已被前面的
  单元满足 → 未满足 fail-fast（列缺失名 + 当前可用集），通过后并入 produces。
  真实声明：`SemanticMappingPlugin` 产 `mapping_tables`、`ConfigDrivenTransform`
  依赖它、`typed_ports.bridge`/`asm_gen.codegen` 依赖 `scope`；内置执行器契约在
  `_BUILTIN_UNIT_CONTRACTS`。**无声明 = 不校验**（可选、附加）。测试
  `tests/engine/pipeline/test_contract_check.py`。

- **槽位契约声明面（0.1.2 阶段 5b-3c-1）**：`[[transform.slots]]` 从「无人读的
  名字列表」变为**槽位契约声明**——每槽位声明触发节点（`on`）/ 遍历形态
  （`walk` = top|recursive）/ ctx 来源（`ctx`，`$node` = 触发节点）/ 结果接回
  （`result` = extra|none|replace|remove）；**时点不在此声明**（归
  `[pipeline.units.*]`）。加载期 fail-fast：槽位名未注册 / 取值非法 → 报错。
  typed_ports 四个槽位已按此声明（`tpc.toml`），执行仍由 `_bridge.py` 调用
  （遍历/接回的通用执行器见 5b-3c-2）。另：删死槽位 `expand_typed_port`
  （no-op，A1/A3）。测试 `tests/engine/core/test_transform_slot_decls.py`。

- **槽位执行面（0.1.2 阶段 5b-3c-2）**：新增引擎通用槽位执行器
  `transform/slot_runner.py`（限定名 `slot_runner`；契约 `requires=["scope"]` /
  `produces=["slot_transforms"]`）——按 `[[transform.slots]]` 声明机械执行：遍历
  （`walk`）→ 触发（`on`）→ ctx（声明 + 固有通道 `root_scope` +
  `[transform.ctx_channels]` 派生通道）→ 调 handler → 按 `result` 接回
  （extra / none / replace（1:1 替换 + 注释迁移）/ remove）。新配置品类
  `[transform.ctx_channels]`：通道构造声明式（如 `type_map = { symbol_kind =
  "typed_port", attr = "type_name" }`），引擎不认识 kind/attr 语义。
  **typed_ports 桥插件 `_bridge.py` 退役删除**（`handlers = ["_transform.py"]`），
  不留双路径。等价判据：typed_ports 全组 54 + e2e 122（保真/互操作）+ 全量 1678
  全绿。测试 `tests/engine/core/test_transform_slot_decls.py`（含 ctx 通道校验）。

- **槽位级单元（0.1.2 阶段 5b-3c-3）**：槽位可各自声明时点——
  `[[pipeline.units.<name>]] slot = "<槽位名>"`（与 `impl` 互斥）→ 该单元只跑该
  槽位（`SlotRunnerPlugin(only_slot=...)`）；未知槽位 / 非 transform 类型 /
  `slot`·`impl` 并存 → fail-fast。槽位单元的契约沿用承担它的插件（`slot_runner`：
  `requires=["scope"]` / `produces=["slot_transforms"]`）。未声明槽位单元的
  语言包仍走整包槽位执行（现行为零变化）。测试
  `tests/engine/pipeline/test_unit_slot_schedule.py`。

- **修复：模块体首注释被渲染到 `module` 声明之前（渲染层）**：
  `renderer/primitives/join.py` 的"容器首部 Comment 拆段"（ADR-0013 B1.3）
  会把 item `sub_node` 首部 Comment 摘出前置——对 `ModuleDecl` 这类**分段节点**
  （有 head/body/tail）则漂到 head 之前（顶格）。修：拆段只作用于**非分段节点**
  （列表项）；分段节点的 body 首注释归 `render_node` 的 body 段渲染。
  触发条件：模块体**首个元素**是注释。最小复现 12 行（与宏/typed_ports 无关）；
  `ref_spi_inf` 展开路径注释回到 ref 位置（第 11 行）。回归
  `tests/languages/verilog/test_comment_body_head.py`；记录
  `docs/gaps/gap-renderer-comment-fidelity.md`。

- **时点轨迹 HTML 报告（`tpc trace --html`）**：新增 `pipeline/report_html.py`
  （`render_trace_html`）——吃 `ctx.result["trace"]`（ADR-0015 §2 可视化产物），
  渲染单文件 HTML（内联 CSS、零依赖）；与 `tpc check --html` 同一视觉语言
  （`analyzer/report_html.REPORT_CSS` 提为共享常量，单一样式来源）。页面 =
  每单元卡片（时点/`kind` 徽标/`impl`/黑板键）+ **artifacts** 自述
  （槽位调用计数、映射表行来源链）。新增 CLI 子命令 `tpc trace FILE
  [--html OUT] [--json OUT]`。渲染器只做通用值树渲染（不认识具体键名，
  不引入插件知识）。测试 `tests/engine/pipeline/test_trace_report_html.py`。

- **检查精度评测扩面（0.1.2 阶段 8 / T1）**：`eval_check_accuracy` 的 focus
  补入已实现但未入评测的码——inst 族 `W101`/`W102`/`W103`/`WC001`（跨文件）
  与 always 族 `AW001`/`AW002`（默认关，评测显式启用）。样本 26 → **56 case**
  （35 正 / 21 负），recall **100%**（40 期望码全命中）+ FP **0** + parse_err 0。
  顺带修正 `UN001_used_signal` 样本（时序块阻塞赋值 → 非阻塞，避免顺带触发
  新启用的 AW001）。
- **修复：组件 handler 注册面失同步（补注册）**：模块体已 exec 过（`sys.modules`
  缓存不重跑）但注册表被外部清理（测试隔离还原 `/` 热重载）时，`[[transform.slots]]`
  的加载期校验会误报"槽位未注册"。修：校验缺名时**补注册一次**（重新 exec 本组件
  handlers），并把 `register_primitive` 改为**同名同函数幂等**（不同函数仍报冲突）。

- **修复（5b-3c-2 回归）**：`slot_runner` 的 `result = "extra"` 误将 handler
  返回值接回 AST → `build_wrapper` 的 wrapper 模块被内联进主输出
  （`ref_spi_inf` 展开保真 0.43）。现改为**不接回**（额外产物由 handler 侧
  `mark_extra` 自出，同桥时代语义）；补单测锁 `extra` 不重接 / `none` 接回返回值。
  由 0.1.2 阶段 9 真实语料终验（`tests/e2e/run_all_tests.py`）抓到，测试
  `tests/engine/pipeline/test_unit_slot_schedule.py`。

- **检查精度评测扩面（0.1.2 阶段 8 / T1 续）**：NC 族（命名风格）入评测——
  `NC001`-`NC011` 按 kind 合并为 5 个正样例（module/信号/参数/实例/子程序）+
  2 个负样例，样本 56 → **63 case**（40 正 / 23 负），focus 23 → **34 码**，
  recall **100%**（51 期望码全命中）+ FP **0** + parse_err 0。

- **修复：GenvarDecl 符号从未注册（NC008 形同死配置）**：`name_attr` 误配
  `genvar_names.name`——该列表元素是裸 `Identifier` 节点（名字在 `content`，
  无 `name` 字段），`_walk_path` 取不到即丢弃，符号静默不注册，导致 `genvar`
  命名检查永不触发（既有测试只断言“大写合规零诊断”，未覆盖违规检出）。
  修为 `genvar_names.content`；补回归测试 `test_genvar_lowercase_nc008`
  （已回退验证：修复前精准失败）。

- **检查精度评测补全命名族（0.1.2 阶段 8 / T1 完）**：NC014-016（前后缀语义
  约定：方向后缀防接反 / 类型后缀防混淆，handler 判定）入评测——1 正样例 +
  1 负样例，样本 63 → **67 case**（44 正 / 24 负），focus 34 → **37 码**，
  recall **100%**（54 期望码全命中）+ FP **0**。至此全部命名族 NC001-NC016
  均在强检面内。样本用模块内 `reg` 声明而非 ANSI 端口 reg——后者符号 kind 归
  `port`（由 NC005 覆盖），评测描述已注明分界。

- **宏/指令卫生族（MH 族，0.1.2 阶段 8 / T1 完）**：`linter/checkers/macro_hygiene.py`
  在解析前扫**原始源码行**（指令行已被预处理剥离，不进 token 流）——`MH001`
  nettype 指令未复位（对标 svlint `default_nettype_wire_at_end`：文件末尾生效值
  非 `wire` 即报，防跨文件泄漏）、`MH002` 宏以**不同值**重定义未先 `undef`
  （对标 Verilator `REDEFMACRO`：值相同不报）。关键字/前缀/复位值/续行符全部
  来自语言包 `[linter.macro_hygiene]`，未声明该段的语言包（如 c4）不注册检查器
  （零开销零误报）；多行宏体因值不确定不参与比较（保守优先）。linter 准确度
  评测样本 31 正 / 5 负 → **33 正 / 7 负**（负样本锁"已复位"与"同值重定义"
  两个边界），recall 100% + 误报 0。测试
  `tests/engine/linter/test_linter_macro_hygiene.py`（13 项）。

- **规则可达性门禁（门禁体系改进，2026-09-12）**：`tests/policy/test_rule_coverage.py`
  —— 自动枚举"已定义码"（声明式规则表 ∪ 插件 handler 源码的 `code=` 关键字
  实参，**ast 提取**）与"已入样本码"（评测 focus），断言差集为空。动机：
  `NC008` 曾长期是死规则（符号从未注册 → 判定永不触发），而原评测只覆盖
  "正样本能检出 / 负样本不误报"两侧，**不覆盖"某规则根本没进正样本"**。
  门禁上线即暴露两个真实缺口——`TP002`（role+invert 悬空）与 `TP006`
  （invert 自反）已实现但无样本，同批补齐：样本 67 → **69 case**（45 正 /
  24 负），focus 37 → **39 码**（= 全部已定义码）
  + FP 0。门禁自带免疫设计：豁免数上限（照 linter `MAX_KNOWN_MISS` 防滥用
  思路，当前 0）、反向核验（样本码须能找到定义，防拼错后"看着在跑其实
  没测到"）、枚举源非空下限（防提取失效假绿）。
  注：首版用正则提取漏掉单字母前缀码（W101/W201 等 8 个），把"枚举不全"
  误报成样本问题——提取本身也要经得起检验，故改 ast。
- **易漂移数字单一来源化（门禁体系改进）**：样本规模数字（case 总数 / 正负
  样例数 / focus 码数 / 期望码数）不再写死在文档里——由
  `tests/e2e/eval_check_accuracy.sample_stats()` 从 `expected.json` 现算，
  文档只引用来源或改述为定性描述（docstring / TODO 现状段 / ROADMAP 已同步）。
  新增门禁 `tests/policy/test_doc_stats.py`：纳管清单（docstring + TODO 正文，
  跳过 `>` 引用块——按文档纪律引用块不沉淀数字）出现硬编码规模数字即失败。
  门禁自带两向自检：该匹配的必须匹配（防模式失效假绿）、规则码含数字的表述
  不得误报（首版真实发生 `CC001 case 无 default` 被当成 case 总数——误报比
  漏报更伤，会诱发无谓改写进而让人想加豁免）；另校验单一来源自身正确
  （现算值 == 实跑评测统计）。动机：同一轮内 case 数/期望码数在三个文件各写
  一遍，**错了三次**，全靠实测输出发现。

- **增量覆盖率自查（门禁体系改进）**：`tools/check_coverage_delta.py` —— 只统计
  本次改动的引擎源码文件，自动定位其所在包对应的测试目录（找不到才回退 smoke
  层），几十秒给出每文件覆盖率与缺失行；统计范围取自 `pyproject.toml` 的
  `[tool.coverage.run].source`（新增引擎包自动跟上，不硬编码包名）。
  动机：全量 `--cov` 串行 ~32min 只在发布时跑 → 平时新增代码的覆盖率是盲区。
  开发中即验出价值：新写的 MH 检查器在只看 smoke 时是 75.3%（其单测未标
  smoke），跑对应测试目录才是真实的 95.9%。两处细节是实测修正的——coverage
  的 `--cov=` 只认模块名不认文件路径（传路径报 "never imported"）、pyproject
  的全局 `fail_under=80` 会把"只统计改动文件"误判为失败（须显式
  `--cov-fail-under=0`，是否达标改由脚本按文件判定）。默认只报告不失败：
  smoke/局部测试未必走到改动文件的全部路径，硬卡会误伤，要卡用 `--fail-under`。

- **真实语料误报基线（门禁体系改进）**：`tests/e2e/eval_diag_baseline.py` +
  `tests/e2e/samples/real/diag_baseline.json` —— 把真实语料（9 个工程，分组口径
  复用 `eval_benchmark._GROUPS`）上的诊断**按码计条数**固化成基线，新增门禁
  `tests/policy/test_diag_baseline.py` 卡"只许减不许增"。动机：规则默认开/关是
  数据决策，但真实语料的误报面此前只有人工量化、无留痕——规则改动引发的误报
  增长只能靠人偶然发现。基线**不依赖 oracle**（"增长即需解释"与判定对错无关；
  查证哪些是误报仍用 `eval_benchmark.py`，它需外部工具故不进日常门禁）。
  门禁另含两项自洽校验：`total` 必须等于 `counts` 之和（防手改漂移）、基线
  非空（防清空后静默通过）。首个基线：**132 条 / 7 个码**
  （CC001 22 / LC001 25 / UN001 22 / W101 13 / W104 10 / W105 2 / W201 38）。
  代价：全量测试 +约 33s（真实语料必须实跑；smoke 层不含 policy，不受影响）。
  门禁有效性已回退验证：把基线调小模拟增长后，精准报出 `W105: 0 → 2 (+2)`。

- **门禁有效性抽查（门禁体系改进）**：`tools/check_gate_efficacy.py` —— 把"回退
  验证"从手工一次性动作变成清单化抽查。清单里每条变异都**来自真实发生过的事故**
  （NC008 死规则的 `name_attr`、`slot_runner` 的 `extra` 接回、MH002 续行保守、
  误报基线改小），逐条执行：备份 → 施加文本变异 → 跑相关测试 → **期望失败** →
  还原；若测试仍然通过则报错（门禁已失效，或被削弱的测试掩盖了变异）。
  **首轮 4/4 如期变红**。设计要点：锚点找不到就报错而不静默跳过（防抽查慢
  慢变成空转）、要求工作区干净（防还原掩盖未提交改动）、`finally` + 回读校验
  保证还原。不进日常门禁（一轮约一分钟）。

- **文档纠错 + `W101` 根因定位**：先前把"跨文件语料基座"记为"待 elaboration 底座
  （P2.7）"，实际底座（ADR-0008 三层）早已完成于 `3acae77`——`analyzer/checker.py`
  的 `_discover` 已能按实例化链递归发现定义文件（层 1 模块注册表 + 层 2 端口连接
  展开 + 层 3 信号驱动/负载图）。真实缺口是两点：①**入口只有单个**
  （`check(entry_path)`），多文件工程只喂 entry 时同工程其它文件里的模块成为未知
  模块；②定义文件查找按"模块名 ↔ 文件名"匹配。误报基线里 `W101=13`（未知模块）
  即由此而来：语料文件名带 `ref_` 前缀而模块名不带（真实工程通常靠命名约定满足，
  属语料人为偏差）。ROADMAP 与 gap 描述已同步修正。

  **同日实测更正**：上述"`W101` 由文件名不匹配导致"的判断**不成立**。逐条
  打印诊断后，13 条 `W101` 全部来自 `ref_serv_top.v`，报的是 `serv_alu` /
  `serv_csr` 等 SERV 子模块——它们的定义文件**根本不在语料里**，是真未知、
  不是误报。且 `_find_module_file` 早有"同名文件 → 目录内关键字文本扫描"
  **两级**策略，同目录下的文件名不符不成问题（"同目录扫描"本来就已具备）。
  真实缺口只剩：入口曾是单个（已补：`check(paths)` 多入口，跨目录工程需要）、
  以及语料侧缺文件。教训：根因必须落到实测（逐条打印诊断），不能停在
  "看代码猜机制"——本轮因未验证连下了两次错结论。

### Fixed

- **块结束符/模块头行尾注释漂移**（renderer + parser，缺口队列 ④）：语句行尾
  注释能原位渲染，但 `end // c` / `endmodule // c` 被挪到下一行、`module m; // c`
  更漂过 `endmodule` 落到文件末尾（AST 侧本已正确挂上 `_comment_slots`，问题全在
  渲染顺序）：① `render_node` 把 `trailing` 的 LineSuffix 追加在 tail 的
  `tail_break` 空行 break **之后**——LineSuffix 只在下一个换行点前落地，故掉到
  下一行；② 模块头注释挂在 `ModuleDecl.trailing`，而它的 tail 是 `endmodule`，
  且 head 布局自身以 `{ break = true }` 收尾并被 group 包成 `Union`。修法：parser
  在块体解析前把块头那行的 trailing 迁到 `head_trailing`；renderer 把 trailing
  输出在 tail 尾随 break 之前、`head_trailing` 经新增 `_insert_before_trailing_break`
  （Doc 小工具，递归进 `Union` 两支）插到 head 末尾换行点之前。回归
  `tests/engine/parser/test_comment_attachment.py::TestBlockEndTrailing`（3 例，
  **逐行位置敏感**）——e2e 保真度用 `_strip_all` 抹掉空白与换行，对该缺陷天然
  失明，故须单独锁。

- **`delim` 类多字符定界符静默失效**（`lexer/capture_runner.py`）：终止判定原为
  `ch == rule.end` 单字符比较，而配置层只校验"非空字符串"（即声称支持任意长度）
  ——配 `"""` 会永不匹配、静默吞到行尾/EOF（把后续 token 一起吞进字符串）。改为
  按长度比较（与 `marker`/`line_match` 同构）：同起同止多字符（`"""`）与起止
  不同形态（`[[capture]] kind="delim"` + `r#"`/`"#`）均可用。顺带删除
  `lexer/main_lexer.py` 中不可达的"字符串分支" + `_string_delims`（A1 死码；
  清空该集合后 verilog/c4/yaml 三包字符串 token 完全不变，已实测）。回归
  `tests/engine/lexer/test_capture_runner.py`（+4 用例）；全量 1739 passed。

### Changed

- **结构提取底座独立（`analyzer/structure.py`）**：原 `analyzer/checker.py`
  （1375 行）三重职责拆分——结构提取底座（elaboration 三层，33 方法 / 995 行）
  移入 `analyzer/structure.py` 的 `_StructureBase`；`checker.py` 只留检查门面
  （`ProjectChecker(_StructureBase)`，6 方法 / 238 行）。收益：① 语言包
  `[structure] protocol` 的**声明点**随底座迁出，门面不再声明结构协议
  （注册点分离）；② 文件名不再暗示"分析器必然实现检查插件"。外部 API 与行为
  零变化（`from analyzer.checker import ProjectChecker` 全部调用方未动；全量
  1735 passed + 8 skipped）。本轮用继承实现文件级分离，**组合式依赖注入推迟**
  到出现第二个真实消费方时再做。
- **验证体系强化（本版）**：规则覆盖门禁（声明码 vs 采样码，含反向校验）、
  数字单源门禁（文档禁止硬编码样本统计）、真实语料误报基线（只许降不许升）、
  增量覆盖率工具、门禁有效性变异抽查（4/4 期望变红）。

### Fixed

- **插件来源表按下标配对被注册表截断打乱（幽灵 flake 根因）**：`transform.engine`
  的插件来源表 `_plugin_origins` 原先是与 `_plugin_registry` **平行的 list**，靠
  `zip(registry, origins)` 配对。但测试侧清理惯用 `del _plugin_registry[order:]`
  （5 处）——**只截注册表**；两表一旦错位，"注册 → 截断 → 再注册"后新注册项就配到
  **前一项**的来源上：

  - 语言插件配到 `None`（= 引擎插件语义）→ **在任何语言下都生效**。这正是那条长期
    未定性的幽灵：`test_language_switch.py::test_plugin_scope_excludes_other_language`
    在并行全量下偶发失败（"切到 verilog 后 c4 的 `AsmGenPlugin` 仍在作用域内"）；
  - 反向配错则会把**引擎插件静默过滤掉**——插件缺失、行为降级，无任何报错。

  改为**按类键控**（`dict[type, str | None]`），截断注册表不再可能造成错配。

  **复现与验证**：定位时建了 6 秒确定性复现（`test_plugin_index` +
  `test_unit_params` + `test_unit_plugin_schedule` + `test_contract_check` +
  `tests/languages/c4` + `test_language_switch`，`-n 1`）——修前该序列 2 failed /
  修后 62 passed；诊断实测失配 3 条（`AsmGenPlugin` 配对 `None`、现算 `'asm_gen'`），
  两表长度 6 vs 94。新增回归测试
  `test_registry_truncation_does_not_misplace_plugin_origin` 构造"注册→截断→再注册"
  窗口，**反向验证过**：把实现临时还原成平行 list，该测试立刻变红
  （`'_LangProbe'` 与引擎插件并列）。

## [0.1.1] - 2026-09-09

注释还原体系闭环（ADR-0013 阶段 B1~B1.5/A2 + ADR-0014）+ typed_ports 语义
检查与清理（T3/invert/resolve_refs 链删除）+ 检查链收尾推进 + 测试 smoke
快速层（217 用例）与并发回归修复。基线：pytest 1575 全绿 / smoke 217 /
real 语料 9 文件 FAIL 0 / lint recall 31/31 零误报。

### Changed

- **删除一次性调试工具 debug_segment_parse.py**（分段解析 + 并树）：仅一次
  picorv32 大文件调试会话使用，无引用/无测试/未进正式管线（"并树"能力从未
  落地），git 历史 4 次提交全为被动清理。删除判据 A1。全项目同类审计（对照
  scaffold 判据：无真实使用/无测试/机制脱节）结论：其余候选均保留——
  run_all_tests（发布门禁，2026-09-09 靠它抓 TP003 误报）/ eval_benchmark
  （oracle 对拍工作流）/ _proto_macro_hygiene（ROADMAP 立项原型）/
  run_differential_svparser（全语料差分扫描，test_real_corpus 覆盖固定语料）。

- **删除 `new component` 脚手架（scaffold_component.py）**：CLI 子命令从未被
  真实组件使用（全部组件手写演进），无测试覆盖，且模板停在已删原语链时代
  （`[analyzer] primitives`），与当前组件协议（postpasses / 声明式 checks）
  脱节。删除判据 A1（无真实使用）+ A5（结构不一致）。连带删 main.py `new`
  子命令、README quick start 示例、pyproject py-modules、
  component_protocol §8 脚手架节。

- **测试分层：smoke 快速回归层 + 全量**：全量测试重（串行 ~32min / 并行
  ~6min），新增 `@pytest.mark.smoke` 分层（pyproject markers 注册）——每组
  功能域挑代表测试（engine 9 子系统 + verilog/c4/yaml + e2e + policy 门禁），
  `python -m pytest -m smoke` 217 用例 ~37s 做日常快速回归；全量留发布/大改后。
  real_corpus 抽 `ref_uart_rx` 做轻量真实语料代表（`_SMOKE_CORPUS` 参数级
  打标，module 缓存只跑 1 次全管线）。组别表与代表维护规约见 tests/README.md。
- **pytest timeout 60→120s，修复并行 worker crash**：并行（`-n auto`）CPU
  争抢使真实语料全管线慢 ~2.5x（tv80 单跑 24s → 并行 60.63s），越过 60s
  阈值触发 pytest-timeout → thread 方法与 xdist worker 交互崩溃
  （`Not properly terminated`；串行无争抢不触发，全量并行曾崩 3 个
  tv80/ice40 断言）。放宽到 120s 留争抢余量。
  验证：smoke 217 绿（37s）+ crash 高发组（real_corpus/real_fidelity/
  check_accuracy/mutation/comment_container）并行 60 passed + 8 skipped 无崩溃。

- **typed_ports resolve_refs 原语链整体移除（P1.5 step 2 A+B）**：role 端口展开
  统一走 postpass 递归（`_expand_ports` → `resolved_ports` → `_apply_entry` 直接
  注入）后，旧"analyze 即时 resolve"双实现链冗余，分两步删净：
  - A（组件内，69948f6）：typed_ports 停用 resolve_refs/flatten_ports/
    attach_invert_map 配置与 handler（删 `_flatten_ports.py`/`_invert_map.py`）、
    `_check`/`_transform` 去 `_ref_callbacks` 回退、删 collect_callbacks 能力与
    resolve_entries 声明
  - B（引擎级，本提交）：删引擎 resolve_refs built-in 原语
    （`analyzer/primitives/_resolve.py`）与其专属工具（`_utils.py` 整体）、
    `_semantic_mapping` 的 apply_refs 后处理链（_run_resolve/_apply_refs/
    _walk_refs/_merge_to_flat）、`_protocol` 冗余常量（ATTR_REF_CALLBACKS +
    3 原语名）、plugin_loader 的 resolve_entries 收集与 pipeline 组装简化
  - 文档同步：component_protocol 语义映射通道节改"已移除"、transform/README、
    引擎注册示例（已删 `_flatten_ports.py`）换真实 `check_name_call`
  验证：引擎专项 346 + 全量 pytest 1567 绿 + policy 双门禁 PASS + pylance 改动
  零诊断。

- **typed_ports invert 嵌套/后置定义修复（TODO P1.5 L2/L3）**：新增组件内
  analyzer postpass `_expand_ports.py`——analyze 遍历结束后（scope 完整）对
  每个 role 从 raw 声明递归展开完整端口集（nested 递归 + invert 取对侧角色），
  写 `sym.attrs["resolved_ports"]`。修复 L2（invert 含嵌套 role 时嵌套端口静默
  缺失——现取对侧角色展开，`inner_*` 方向反转 + 位宽保留）与 L3（invert 目标
  role 后置定义时单趟 DFS 取不到符号漏展开）。下游 `_semantic_mapping`：
  `_apply_entry` 对 attr==ports 且含 resolved_ports 的 role 直接注入扁平行，
  `_walk_refs` 跳过有 resolved_ports 的 role（避开 analyze 旧回调的坏 invert
  数据）。测试样本修正（`wrap.slave` 由混用重复 `spi.slave inner, invert
  master` 改干净 `invert master`，展开不再重 `inner_*`）+ 新增 L3 后置定义
  pos 测试（`test_backward_def_invert_expands`）。验证：typed_ports 相关 36 +
  全量 pytest 1566 绿 + policy 双门禁 PASS。

- **README top type-spi 示例修正（0.1.1 发布准备）**：示例原 `spi.slave
  spi_io` + `impl spi.master => spi_io` 混角色绑定会被 T3 检查（TP012 同角色 /
  TP003）拦为发布反例；改同角色 `spi.master spi_io` + `impl spi.master =>
  spi_io`，展开块方向同步，抽取验证可运行。

- **typed_ports 增强语法语义检查（T3，ADR-0013 三族）**：新增组件内 analyzer
  postpass `_check.py`（挂 typed_ports `[analyzer] postpasses`）——A 表述完整
  TP001 type 悬空 / TP002 role+invert 悬空 / TP003 显式端口 typo / TP004 role
  端口重名 / TP006 invert 自反；B 连接正确 TP010 impl `=>` 未命中端口实例
  （拦 `=> top` 历史错误写法）/ TP011 类型不匹配（spi 连 sci）/ TP012 role
  不同向（ref_spi_inf 同向基准）；C 单驱动 TP020 同一接口实例被多 impl 绑定
  （多驱动预检，对齐展开后 W105）。TP 恒开 error 级，analyze 报错即阻断展开
  （复用 schedule `_ScheduleStop`，坏输入不产出错误模块）。顺带修：TypedTypeSpec
  即时 identifier_ref 在 type 后置（合法前向引用）时误报 W001 → 移除，交 TP001
  postpass 全量核对；既有 `=> top` 错误样例修正（test_typed_ports/
  test_enhanced_render 删误导 impl 行保 TypedPortDecl 展开断言、
  test_comment_migrate/test_schedule 改同向 `=> 实例`）。验证：18 单测 +
  eval_check_accuracy 8 TP pos + 1 neg 样本（recall 100% + FP 0）+ 全量 pytest
  1566 绿 + policy 门禁零命中。

- **行尾注释统一为 `_comment_slots["trailing"]`（A2 双轨消除）**：parser
  `collect_following_comments` 行尾注释挂载从 `_attached_comments` 并入
  `_comment_slots["trailing"]`（renderer 同 LineSuffix 渲染）——消除
  "attachment 属性 + trailing 槽"双轨（ADR-0013 阶段 A 前遗留，读侧
  靠向后兼容分支 + transform 迁移双轨为代价）。删除：node_renderer
  attached 兼容分支、transform/engine `_collect_subtree_comments`/
  `migrate_comments` 的 acc_attached 通道、去重集合 `_attached_seen` 改名
  `_trailing_seen`、2 个 legacy 测试。`_comment_anchors` 记录保留（tpc
  marker 还原通道，不受影响）。验证：注释专项 94 + normal 32/32 + real
  9/9 保真不降 + 全量 pytest 1542 全绿。

- **pratt op 行尾注释挂 RHS leading（ADR-0014 ②方向 B）**：operator 间隙
  的行尾注释（`a || // bgeu\n b`）不再走 comment_sink（渲染重排后锚匹配
  失败 → 丢），`_skip_gap_comments` 返回 eol 注释并挂后续 RHS 子节点
  `_comment_slots["leading"]`——`//` 注释必处行尾、随操作数独立断行机械
  安全；BinaryOp 挂 right、Ternary 挂 true_val/false_val、Unary 前缀挂
  operand。darkriscv BMUX `|| // bgeu/bltu/bge/blt/bne` 5 条 + 全量
  保留不降（源/输出注释 403/403）。关键坑：操作数可来自外部 atom_parser
  （linter ExpressionChecker 返回 object() 占位）——挂载须 Node 守卫，
  否则 linter 表达式解析抛异常 → 语句 unrecognized 误报。

- **容器开括号同行 line comment 领为 head Comment（ADR-0014 ①）**：
  `sub u (//RF interface\n .port...` 与 `(` 同行非独占行，B1/B1.3 不收；
  `_claim_head_comments` 增第二来源（`_comment_anchors` 中紧前 token type
  以 `bracket.l_` 开头、line < 规则末行的条目）挂 Comment 子节点——
  serv_top 55/55（此前唯一丢的 `(//RF interface`）。

- **restore 函数清理为纯 tpc 通道（ADR-0013 阶段 B1.5）**：restore_comments /
  restore_line_comments 删除 only_tpc/only_midline 参数与普通注释分支
  （B1.2/B1.4 后无调用方，恒 tpc 语义）——函数只处理 tpc marker
  （`/*<tpc:*>` 宏 marker / `// <tpc:*>` 条件占位，宏/条件块还原依赖），
  普通注释条目直接跳过。tpc 还原面 101 测试 + run_all real 9/9 + 全量
  pytest 1540 全绿。

- **删除 inline 通道 midline 回插（ADR-0013 目标④达成，B1.4）**：
  行中注释回插兜底实测纯冗余（normal 组禁用前后输出一致，仅 join 分隔
  符形态 1 条需补渲染）——join 原语消费容器节点 inline_after 中锚=分隔
  符的行中注释（`clk, /* c */ output`）后，restore_all_comments 移除
  midline 分支、pipeline collect_inline_after_leftover 删除——普通注释
  restore_comments/restore_line_comments 回插通道全部删除（line B1.2 +
  inline B1.4），仅剩 tpc marker 独立 only_tpc 通道（宏/条件块还原依赖）。

- **容器首元素前独占注释进树（ADR-0013 阶段 B1.3）**：B1.2 删除 line
  通道后，容器**首元素前**独占注释（`module m (\n // head\n input a`）
  无兜底丢失——行首规则成功时领前置独占注释挂 Comment 子节点（sub_node
  首位），join 拆段独立行渲染（首注释段硬 Break）。repeat 迭代深度协调
  保证与 B1（迭代项间 Comment 迭代项）互斥不双份。门禁：
  tests/e2e/test_comment_container.py::TestContainerHeadComments。

- **删除 line 通道普通注释回插（ADR-0013 阶段 B1.2，目标④主体）**：
  B1/B1.1 后普通独占行注释全部进树（容器项间 Comment 迭代项 / 块结束符
  trailing / block body Comment 节点）——41 文件实测 restore 开/关输出差
  仅 1 条且为锚点错插缺陷，删除净改善。restore_all_comments 移除
  enable_line_comment_restore 参数与全量普通回插分支，line 通道恒
  only_tpc（宏/条件块 marker 还原依赖）；pipeline/run_all 同步删除。

- **块结束符行尾注释进树（ADR-0013 阶段 B1.1）**：块规则结束符
  （`end`/`endcase`）后的行尾注释（`end // case: x`）此前只记 inline
  anchor——restore 仅回 midline/tpc 不回行尾普通注释 → 丢失。现挂块
  规则节点 trailing 槽（LineSuffix 结构序渲染）。real 语料收益：tv80
  注释保留 509→670（eol 缺失 139→5）。门禁：
  tests/e2e/test_comment_container.py::TestBlockEndComments。

- **容器项间独占行注释进树（ADR-0013 阶段 B1）**：repeat 列表容器
  （PortList/NamedPortList/DeclaratorList/CaseItemList 等）迭代项间的独占
  行注释按**源行号窗口**上浮为 Comment 迭代项进容器 items（结构序），
  renderer join 独立行段渲染——替代宏展开场景（line 通道 only_tpc 不回
  普通注释）的注释丢失。real 语料收益：serv_top 26→54 保留、tv80 480→509。
  实现：parser 吞注释记录独占行标记 + `_repeat_loop` 行号窗口上浮 +
  绑定 list-spec 保留 Comment 项；tpc marker 与行内/行尾形态保持既有通道。
  门禁：tests/e2e/test_comment_container.py（5 测试）。

- **署名加入 AI 协作者（方案 A 定稿）**：主作者 biominescence（方向/决策/
  发布/维护）+ AI 协作者 `deepseek-v4-flash`（核心引擎、语法包与验证套件
  协作实现）——`packaging/attribution.py`（单一来源）`--credits` 输出
  `AI Co-author` + `Implementation` 行、`pyproject.toml` authors 两条目、
  PE 版权信息、README `Attribution` 段同步。披露充分但不越界：模型署名
  留在协作者/实现层，作者（责任人）仍为自然人。

## [0.1.0] - 2026-08-22

Alpha 发布——配置驱动语言管线首版：主包纯净可综合 + 仿真插件化 + 第二语言实证。
发布定义（2026-08-21 定）：0.1.0 = Alpha；语法剩项（门级/UDP/specify）后置非阻塞。

### 首版能力

- **配置驱动语言管线**：语言规则全部在 TOML（`grammar/<lang>/`），引擎为通用骨架；
  lex/parse/analyze/transform/render/lint/preprocessor 全阶段可配置、可 fork
- **两个语言包**：`grammar/verilog/`（可综合子集 + 增强语法 typed_ports、formatter、
  semantic_check、attributes、sim 插件）+ `grammar/c4/`（最小 C 子集 → c4 VM 汇编，
  语言无关性实证）
- **前置 token 级 linter**（反解析器，复用同一 TOML 语法，能检查坏代码）
- **增强语法 typed_ports**：`type` / `type.role` / `impl`（嵌套 / invert / 参数化 /
  端口位宽闭环），展开 / 保留双路径（expand_enhanced）
- **formatter 插件**：缩进 / 品类对齐 / 实例端口对齐 / 惩罚模型 wrap / 风格参数化 /
  幂等保持
- **预处理器**：宏展开 / 条件编译还原 / 指令原位回插（带参宏、`include 递归、循环检测）
- **仿真语法插件化（plugins/sim）**：可综合子集进主包、仿真语法进插件 → 主包纯净
  可综合 = 发布基线
- **CLI `tpc`**：format / lint / expand / config dump / new component / init /
  pipeline / --version；版本单一来源（core.__version__，pyproject 锁定一致）
- **工程化**：CI（Windows/Ubuntu × Python 3.11-3.13）、覆盖率门禁 80%、全局 profile
  层（`~/.tpc/config.json`，env > 工作区 > 全局 > 内建默认）、配置来源追踪
  （`tpc config dump`）、wheel 打包保留多语言包目录结构
- **边界诚实记录**：README Known limitations 4 组 22 条

### 首版内已修（Fixed）

- **role 端口 packed_range 位宽丢失**（接口位宽闭环）：展开路径保留 `[7:0]` 位宽
- **nested+invert SKIP 泄漏**（L1 防御）：不再向端口列表泄漏字面 `SKIP,`
- **linter `--json` 崩溃**：`to_dict` 死代码 → `lsp_diagnostic`
- **未定义 task/function 调用检测**（semantic_check 插件，W002，支持前向引用）
- **第二语言渗透修复**：7 处 core 单语言假设清理（见 docs/language_walkthrough.md §7）

### 验证基线

769 pytest + e2e 93 绿（FAIL 0）+ lint recall 31/31 零误报 + 覆盖率 ~83%
（fail_under 80）+ real 组（PicoRV32 / darkriscv / SERV / TV80）+
edge 门禁（12 边界语料）+ 差分对拍（124 合法文件 vs Verible，0 假拒）+
fuzz（~8000 轮，不崩溃 / token 保序 / 幂等不变量）。

### 2026-08-22 (发布准备：验证体系 + 独立 formatter + README 重写)

- **验证体系（tests/fuzz + tests/edge + tests/differential）**：语法驱动 +
  变异 fuzzing（不变量：不崩溃 / token 保序 / 幂等）；边缘构造门禁（clean 必须
  成功 / reject 必须失败）；与 verible-verilog-format 差分对拍（接受域 +
  互操作，二进制经 `tests/differential/fetch_verible.ps1` 获取，gitignored）。
  fuzz 直接从 grammar TOML 派生生成空间——配置即数据的验证红利。
- **fuzz 发现的 4 个真实缺陷（均已修复并沉淀 edge 回归）**：
  - 畸形输入过 lint → parser 截断 → 管线静默 `success=True` 且**丢内容**
    （`_stage_parse` 现检查 `_parse_truncated`，截断即失败）
  - `module name #()` 空参数表解析不了（`ParameterList` 的 `@ParamDecl` 改可选）
  - 畸形 ANSI 函数端口（缺端口名）→ parser `assert` 崩溃（改安全恢复，用户
    输入永不崩溃）
  - 自引用宏 → 宏体预展开指数膨胀 `MemoryError`（直接自引用跳过 + 体长上限）
- **README 全量重写**：按业界 README 结构（首屏定位 + 徽章 + 演示 + Why/
  when-not + Quick start + 文档分流 + 贡献指南 + 状态），559 → ~350 行；
  Known limitations 精简为摘要，完整版移入 `docs/known_limitations.md`。
- **功能切面打包管线（tpc-fmt.exe / tpc-lint.exe，Nuitka）**：按
  `packaging/facets.json` 切面规格打包单一文件 exe（内置 Python + 引擎 +
  语法包，~8.3 MB）；`packaging/build_pipeline.py` 生成入口（命令可裁剪，
  复用 `main._register_subparsers(allow)`）→ Nuitka onefile → SHA256；
  PE 元数据 + `--credits` + 二进制内嵌署名（`strings -el` 可扫）；
  文档 `docs/packaging.md`。
- **语义检查插槽设计落档**（未实现，设计先行）：`docs/decisions/0004-
  semantic-check-slot.md`（双层规则 + post-pass 链式检查）+ `docs/semantic_checks.md`
  + 前置调研 `docs/references/static_checkers_survey.md`。

### 2026-08-23 (发布收尾：GitHub 上线 + CI 首跑三修)

- **GitHub 上线**：仓库 `DogStraight/trans-paradigm-compiler`（public）——dev 分支
  推送 + tag `v0.1.0`（正式发布锚点）；旧版本 tag（v0.1/v0.11/v0.2.0）降级为
  milestone-* 里程碑（版本号伪装去除，指针保留）。提交邮箱已关联账号。
- **CI 首跑三修**（12 任务矩阵首跑暴露 3 类本地测不出的缺陷，均已修）：
  - `FileManager.get_full_path` 绝对路径 POSIX **翻倍拼接**：`lstrip("/")` 把
    绝对路径当相对路径拼 `_base_dir`（Windows 靠 Path 盘符替换碰巧正确，
    Linux 必炸）→ 绝对路径原样透传（normpath），新增 2 个回归测试
  - ci.yml wheel 冒烟 `cd /tmp` 后相对 `_venv/bin/tpc` 失效（exit 127）→
    `$GITHUB_WORKSPACE/_venv` 绝对路径
  - 测试硬编码本机绝对路径 4 处（`e:\project\tpc_compiler\...`，味道审查
    标记过的边界项）→ `FileManager.get_full_path` 可移植解析
- **CI 12 任务矩阵全绿**：test + wheel-install ×（3.11/3.12/3.13）×（ubuntu/
  windows）——含 wheel 安装后从任意目录运行 CLI 验证。
- **README 切片声明**："Sliceable — take only what you need"（format/lint/
  expand/全管线独立可用，切片自助、管道整体维护）。
- **注释味道审查 + 卫生清理**：rubric（`docs/comment_smell_rubric.md`）+
  前人调研（`docs/references/comment_smell_survey.md`），8 子代理 × ~211 文件
  全审（全部件"轻"味，人味 6-9/10）；正确性问题 + AI 味收紧 + grammar 卫生
  全部清理（TODO P2.4 清零），tests 引导样板抽公共模块 `tests/_bootstrap.py`。
- **注释正确性修复**：过时类名/失效路径/文档漂移/死 docstring/语言渗透措辞
  （"Verilog file" → "source file"）等 34 处。

### 2026-08-21 (typed_ports 接口位宽闭环)

- **role 端口 packed_range 携带（TODO P1.5 完成）**：typed_ports 展开路径不再丢
  端口位宽——`output [7:0] mosi` 写在 role 端口时展开为 `output [7:0] spi_io_mosi`
  （此前退化成 1 bit）。覆盖直接引用 / 参数引用（`[DATA_WIDTH-1:0]` 字面透传）/
  invert / 嵌套类型 / wrapper 模块端口。
- **nested+invert 组合 SKIP 泄漏防御（L1）**：`slave : spi.slave inner, invert
  master;` 展开不再向端口列表泄漏字面 `SKIP,`——映射表 `_merge_to_flat` 过滤
  无端口名空行 + `_expand_primitive` 过滤无产出结果（双保险）。语义缺口（invert
  对含嵌套引用 role 的嵌套展开端口不参与反转）与边界如实记录于 README Known
  limitations / TODO.md P1.5（L2-L3 未修）。
- **emit 原语扩展**（通用能力，引擎无语言知识）：`emit` 支持 `node_name` 键别名
  与 `{ref = "path"}` 原始值透传；捕获数据（node_name 形态 dict）可直接递归重建
  AST 节点（如 Range → msb/lsb 表达式树）。
- **`_process_items` 字段提取修正**：`{$....}` 字段源数据缺键时跳过该字段，
  不再把字面模板字符串塞进行数据（emit 端 ref 透传缺失 = 无此属性）。
- **测试**：新增 `tests/languages/verilog/test_typed_ports.py`（位宽场景 + nested+invert
  SKIP 防御，共 8 项）。
- **测试输出编码修复（Windows）**：`tests/conftest.py` 在收集前强制
  stdout/stderr 以 UTF-8 输出——本机活动代码页 GBK(936) 时 Python stdout 默认
  GBK 编码，中文测试输出（docstring/断言）在 UTF-8 解码侧乱码。

### 2026-08-18 (Engineering gaps)

- **Pipeline split**: `run_pipeline_on_source` 515 lines CC=98 → 173 lines CC=30
  (per-stage functions + `_PipelineContext`); matcher `_match_call_impl`
  151 lines CC=48 → 35 lines CC=7 (per-rule-type methods)
- **Doc: back-references**: 3 → 14, covering all 10 MODEL_INDEX entries
- **Unused imports**: cleaned 6 real issues (kept re-export compatibility)
- **Docs hygiene**: one-time plan docs removed after completion (results
  recorded in CHANGELOG)

### 2026-08-18 (Open-source readiness)

- **Config complexity management**: config source tracking (`_sources` /
  `resolve_with_sources`), `tpc config dump` debug command, declaration
  structure validation, GrammarRule field schema (fail-fast)
- **Lexer config dependency injection**: token/number configs now follow the
  language pack (no more cross-language contamination in one process)
- **Pipeline moved to `pipeline/` package**: `run_pipeline_on_source` shared by
  CLI and tests; wheel install works from any directory
- **Packaging fixed**: grammar TOML shipped as package-data (preserves
  verilog/c4 directory structure); IEEE Annex A docs and PDFs excluded from
  sdist (copyright)
- **Docs**: code quality audit, config complexity plan, open-source readiness plan

### 2026-08-13 (P2 engineering wrap-up)

- Documented P2.0 items: config_lifecycle / expression_conventions /
  component_protocol / c4 minimal language-pack template
- Install verification: `pip install -e ".[test]"` + CLI smoke test
- Coverage gate: .coveragerc (omit entry/fallback, fail_under=84, measured 84.57%)
- Restored CI: .github/workflows/ci.yml (Windows + Python 3.11/3.12/3.13)
- Fixed: linter `to_dict` dead code → `lsp_diagnostic` (`--json` crash bug)
- Removed dead code core/component_loader.py (superseded by plugin_loader)

### 2026-08-13 (P1 complete)

- formatter: width wrap pass, SV base coverage (logic/always_ff/always_comb),
  style parameterization (formatter.style)
- Preprocessor primitive-level unit tests (19)
- Enhanced render verification (nested/invert + TypeNestedPort layout)
- Number-shape configuration: declaration → FSM generator + language-pack
  declarations + signed `'s` + `0'b1` standard rejection

### 2026-08-12 (P0 second language)

- c4 full implementation (.c → c4 VM assembly), 6 integration tests — proof of
  language-agnosticism
- P0.3 penetration cleanup: boundary language penetration removed (ScopeKind
  rule derivation)
- Fixed 7 core penetrations / single-language assumptions (see
  docs/language_walkthrough.md §7)

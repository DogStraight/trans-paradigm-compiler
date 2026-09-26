# Changelog

All notable changes are listed in reverse chronological order.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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

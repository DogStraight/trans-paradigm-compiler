# ROADMAP（中长期目标 / backlog）

> 从 `TODO.md` 拆分而来（2026-08-27）：本文件承接中长期、非发布阻塞、
> backlog、v0.2 候选类条目；`TODO.md` 只留短期活跃待办。
> 维护纪律同 TODO.md：只列未完成项，**完成即删**（历史在 git log，决策在
> references.md/ADR）；立项启动的项移回 `TODO.md` 短期；调研结论落
> `docs/references.md`，不进本文件。
> P 编号沿用拆分前的原始编号（与 git 历史、交叉引用对应），不重新编号。

## 工具链定位 + 语言包战略（2026-08-29 定调）

> **工具链定位（市场面）**：面向**整个语言生态**，不限于硬件领域——两个用例：
> ① 在既有语言基础上做**递进式改进**（插件/增量机制即抓手，如 verilog2005
> → SV 核心 → 新构造）；② **完整实现新语言**（c4 已验证"从零搭语言"框架，
> 见 docs/language_walkthrough.md）。"语法即资产 + 语言知识不进代码"使引擎
> 不绑定任何领域——Verilog 是第一个应用实例，C 是第二个，未来可服务任意
> 语言的改进或创建。
>
> **语言包战略（内置资产范围）**：**主体语言包 = 两个**：Verilog-2005
> （已闭环，P1.8）+ C23（未来主体）。这两个是 tpc 自己深度投入的示范语言，
> 是**资产范围**而非**能力边界**——工具链能力面向整个语言生态，主体语言包
> 只是内置资产的选择。其他语言（如 SystemVerilog）按需以**核心 + 增量插件**
> 形态支持（个人需求只做核心，工作需求可插件族逐步全量——见 SV 条目）。
> c4 定位不变：第二语言验证（语言无关性）+ "从零搭语言"模板 +
> C 核心语法管线支持的子集起步（≠ C23——完整 C 是数量级更大的工程，见下）。

## C 语言包（远期主体，2026-08-29 登记；设计：标准插件族）

> 主体需求（见上"语言包战略"）。**设计定调（2026-08-29）：按语法插件包
> 形式逐步支持 C 各标准语法——开关语法插件组合等效某个标准的 C 语法**，
> 而非一次性做"某个标准全量"。核心洞察：C 标准演进 = 语法增量 + 关键字
> 增量 + 预处理指令增量的叠加，三者 tpc 均已配置驱动（token_ext /
> directive_handlers / [grammar] files + inject），requires 依赖链表达
> 标准包含关系（c11 包含 c99，c23 包含 c11）——**零引擎新机制**。
>
> 结构草案：
> ```
> grammar/c/
> ├── tpc.toml            # [plugins] enabled 默认 = c99 核心基线
> ├── 00_*.toml           # 核心语法（声明/表达式/语句/类型基础，≈c4 范畴 + 常用面）
> └── plugins/
>     ├── c11/            # 增量：_Generic/_Static_assert/匿名 struct/原子（requires 核心）
>     ├── c17/            # 增量：几乎无（bugfix 为主，requires c11）
>     └── c23/            # 增量：typeof/auto/属性/#elifdef/nullptr（requires c17）
> ```
> 启用"等效某标准" = `[plugins] enabled` 组合（requires 链自动带上基线）；
> 核心包战略自然落位——默认 c99 基线即"核心包"，需要时叠加 c11/c17/c23。
> **形态通用化（2026-08-29）**：核心 + 增量插件逐步叠加的形态对 SV 同样
> 适用（SV 核心基线 + class/constraint/SVA 增量插件，见 SV 条目）——这是
> "语言包 = 可组合插件集"的通用模式，C 标准插件族是其首个应用。
> **边界诚实**：语法层增量可完整等效；语义层（类型系统/推导）是渐进项，
> 与语法增量解耦（先语法后语义）。预处理器是最大难点（`#if` 表达式、
> 参数化宏、`#`/`##`、变参宏），darkriscv 嵌套位置精度教训（P1.5）在 C
> 条件编译上只会更严——作为独立阶段评估。
> 触发条件：C 核心基线（≈c4 范畴 + 常用面）立项启动后从本文件移回 TODO。

- [ ] C 核心基线：完整声明/表达式/语句（c4 基础上补全）、函数原型、
      struct/union/enum/typedef、指针运算、作用域语义（= 核心包范围）
- [ ] 预处理器扩展（引擎侧，独立评估）：`#if` 表达式求值、参数化宏、
      `#`/`##` 粘贴、变参宏 + 条件编译反向映射精度
- [ ] c11 插件：`_Generic`/`_Static_assert`/匿名 struct/union/原子（requires 核心）
- [ ] c17 插件：bugfix 增量（requires c11）
- [ ] c23 插件：`typeof`/`auto`/属性/`#elifdef`/`nullptr`（requires c17）
- [ ] 标准等效验证：enabled 组合 → 语法接受域断言（对标各标准语法规范）
- [ ] **注入机制补"改"路径**（C 标准插件族前置，研判见 references.md
      「注入 vs 替换机制研判」）：标准演进含"改"（如 C23 语义变化），现
      inject_replace_rule 是字符串子串补丁（仅 production、软失败）——统一
      `[inject]` 声明面（add/replace/remove），replace 升树层结构化 + fail-fast

## 用户标定打包入口（中长期，2026-08-29 登记；多语言分发前置）

> 语言包战略的兑现侧：用户把语法配置调试稳定、需求测试完成后编译打包的
> 优雅方案（forkable 主张的落地）。现状：facets.json 开发者硬编码 + 
> `_RULES_REL = "grammar/verilog"` 写死——**无"用户标定"声明面**，c4/未来
> C 语言包打包不了。设计方向（研判见 references.md「用户标定打包入口
> 研判」）：打包规格跟随语言包——`grammar/<lang>/tpc.toml` 新增
> `[packaging]` 段（target/description/facets，facets 缺省取 [commands]
> 键零重复）；build_pipeline 改为扫描语言包声明（无参=全部，--lang=单个），
> `_RULES_REL` 硬编码消失。与插件聚类/渲染插件同哲学：一切可声明、可组合、
> 用户标定。优先级低于 C 语言包（当前单语言硬编码还能撑）。
> 触发条件：C 核心基线立项（多语言共存）或出现"非 verilog 打包"需求。

- [ ] `[packaging]` 段声明（target/description/facets，缺省取 [commands] 键）
- [ ] `bundle` 方式可选：`embedded`（语法包打进 exe，自包含单文件）/
      `external`（语法包外置，引擎原生 + 语法可换，同一二进制多语言/版本）
- [ ] build_pipeline 扫描语言包声明（--lang / 无参=全部），去掉 `_RULES_REL` 硬编码
- [ ] 入口生成用该语言包 rules_dir（与调试时 main.py 行为一致）
- [ ] 多语言打包验证：verilog + c4 各自声明、各自出 exe（embedded + external 各验证）

## P2 — 工程化收尾（发布准备）

### P2.2 发布收尾

> 0.1.0 Alpha 已发布（2026-08-22，release_checklist 走完）；以下为软缺口。

- [ ] 覆盖率远期目标 ≥90%（当前 83.39%——source=引擎包真实基线，需补
      transform/renderer 等薄弱区）

### P2.3 验证吞吐优化（backlog，非发布阻塞，2026-08-22 记录）

> 动机：验证（fuzz/差分/edge）是"验证附着于配置驱动语言定义"的差异化能力；
> 快速验证层是"模型写配置 → 自动验证闭环"成立的前提。详见 tests/fuzz/README.md。
> 2026-08-27 更新：linter packrat 记忆化（bf8f782/db14e70，管线 -92%）后
> fuzz 实测吞吐 ~40 iter/s（800 轮 18-19s / 3000 轮 75-86s）——远超最初
> ~9 iter/s 基线（原测速含 linter 热点），三件套预期收益缩水，但缓存复用/
> 关幂等/multiprocessing 仍可再叠加 ~10x。
> 2026-08-29 更新：全量 pytest 回归并发化（pytest-xdist `-n auto`，test extra
> 已声明；global_state 进程内隔离天然兼容，实测 1386+8 与串行一致）——
> 300s → ~110s（~3x，16 逻辑核实测；瓶颈 = 大文件真实语料测试 + 每 worker
> 语法加载固定开销，进一步加速需语法表跨 worker 缓存，见 fuzz 三件套）。
> 2026-08-29 更新：渲染器 doc 布局记忆化（renderer/doc.py，per-layout 缓存
> _flat_w/_has_hardline/_has_break——无缓存时 _best 的 Concat 兄弟预算对同一
> 子树 O(n²) 重复全遍历，picorv32 实测 _flat_w 200 万次/_has_hardline 1000
> 万次调用）——单遍管线 10.15s → 4.37s（-57%，渲染占单遍比从 ~60% 降至
> ~36%），全量并发回归 110s → 78s。下一个热点 = parser（单遍 ~50%）；packrat
> 失败记忆化尝试已回退——rule_frame 的 sibling_counter 在失败尝试也递增，
> 缓存跳过失败子规则计数 → path 编号变化 → 渲染输出差异（picorv32 实测，
> 93 文件对拍；详见 references.md「parser packrat 记忆化尝试」），等价实现
> 需先重构 path 计数语义（改变现有输出，另行评估）。

- [ ] fuzz harness 吞吐三件套：
  - [ ] 语法表/parser 跨迭代缓存（不重建）→ ~2.5x
  - [ ] fuzz 模式关闭管线内部幂等复跑（oracle 自管）→ ~1.8x
  - [ ] multiprocessing 多 worker → ~8x（合计 ~30-40x：100k 轮 ~1 分钟）
- [ ] 随机合法程序 → 对拍 Verible：接受域从 124 人工语料推到统计意义
      （GrammarFuzzer 生成器已就绪，缺接线）
- [ ] 阶段级 fuzz（lexer/parser-only 不变量，比全管线再快 10-50x）
- [ ] CI 补强（PR 快速 fuzz ✅ / 夜间长跑 ✅ / edge 门禁 ✅ 已接入）：
      differential 门禁未接入——需 verible 二进制（nightly.yml 已留可选 job，
      接入时用 fetch 步骤或 VERIBLE_FORMAT）

### P2.6 tpc-check 外部 checker 插件协议（2026-08-25 记录，Veryl 调研触发，非发布阻塞）

> 拿来主义 + 声明场景：语言包 plugins/ 声明**外部 checker**（官方检查，如
> `veryl check`/verible/slang），tpc 只**声明自己的检查场景**（官方 checker 的
> 缺口：格式化保真/变换等价/语法资产一致性）。参考 hdl_checker
> "Repurposing existing HDL tools" 路线 + svlint 深调研（规则四件套/suppress
> 注释对/插件，均落 docs/references.md）。

- [ ] **插件声明协议**：`grammar/<lang>/plugins/checker/tpc.toml` 两段——
      `[checker.external]`（命令 + 输出解析声明，收口稳定接口：JSON 输出/稳定
      规则 ID，防"后端版本耦合"坑）与 `[checker.scenarios]`（tpc 自管场景：
      format_fidelity / transform_equivalence / 语法资产一致性）
- [ ] **诊断归一化**：外部 checker 输出（miette/JSON/文本）转 tpc 统一诊断模型——
      对齐 P1.9 稳定规则 ID + 机器可读输出结论（verible/slang/svlint 均有 JSON 实证）
- [ ] **场景声明语法**：检查场景 = TOML 数据（gate 引用 run_all/差分基线），
      延续"语言知识不进代码"哲学——引擎只做通用场景执行器
- [ ] 验证路径：`grammar/veryl/plugins/checker/` 先做 veryl 本体验证（官方检查
      直连 + 自管场景补缺口），再推广 verible/slang
- 关联：P1.9（诊断模型）为其前置；Veryl/svlint 调研落档 references.md（本地镜像
      `E:\research\veryl` / `E:\research\svlint`）

### P2.7 elaboration 底座（2026-08-29 登记 → 已实现，提交 3acae77）

> 触发：P1.10 主流 lint 调研结论——Verilator/slang/Spyglass 的跨文件检查
> （端口连接/未使用/多驱动/位宽）全是"**elaboration 后**"视角（全设计编译 +
> 实例树展开 + 驱动/负载图）；tpc 目前只有第一层雏形（ProjectChecker 的
> module_index 注册表 + inst_sites + inst_check W101/W102/W103），缺连接
> 关系展开 / 驱动负载图 / 层次展开。没有这个底座，P1.10 核心集合里的
> 未使用类/多驱动/端口完整性/位宽匹配全做不了。
>
> **状态（2026-08-29）**：层 1（module_index + 依赖发现，既有）+ 层 2
> （端口连接展开 _elaborate_connections）+ 层 3（信号驱动/负载图
> _build_signal_graph）已实现，ADR-0008 落档。跨文件规则已验证消费：
> W104 未连接端口（57d6e83）。
> **层 3 扩展（2026-08-31 已实现）**：实例树层次展开——实例 output
> 驱动源穿透到被实例化模块内部真实驱动源（模块内 assign/过程赋值目标
> = 端口 → "路径:assign#N"；更深实例 output → 递归穿透；悬空 output
> 不记驱动对齐 Verilator；黑盒模块未定义 → 原子源兜底）。verilog-
> ethernet 实测 17 模块 123 条穿透驱动源（两层路径如
> ip_inst/ip_eth_rx_inst:assign#29）。真实语料 7 工程对拍数字与基线
> 逐项一致（穿透零新增误报/漏报）；axis_fifo generate `!参数` 求值
> 缺口 9 条误报已修（见 references.md「generate `!参数` 条件求值」）。

- [x] ~~层 1 补全：design-unit 注册表 + 依赖拓扑排序~~（module_index 既有）
- [x] ~~层 2：端口连接关系展开（实例连接信号 → 端口 → 信号解析）~~（3acae77）
- [x] ~~层 3：驱动/负载图~~（3acae77，单层实例→信号）
- [x] ~~层 3 扩展：实例树层次展开（top→子→孙，MULTIDRIVEN 深层）~~（2026-08-31，
      驱动穿透 + 悬空/黑盒处置，见 references.md「实例树层次展开」）
- [x] ~~验证：接 P1.10 跨文件规则~~（W104 未连接端口已验证）

## P3 — 增量解析（v0.2 核心，非收尾）

### P3.1 前置：AST 节点 token span 绑定（解析期）

- [ ] `_production.py` 构造 `rule_node` 时记录 token 范围（起止 `token_pointer`），
      存为 `rule_node.tok_span`（`Node` 用 `**kwargs` 接受任意属性，不改 `core/define.py`）
- [ ] 回溯（snapshot/restore）时 tok_span 正确回滚
- [ ] 方案 B（可选）：`pratt_parser.py` 原子（Number/Identifier 等）也绑 token 位置，
      粒度细化到表达式层

### P3.2 失效判定 + 增量重解析

- [ ] token 级 diff：新旧 token 流对比，标记变更 token（复用 lexer）
- [ ] 变更 token → 延展到语法边界（沿 `is_statement`/`is_block` 规则向外，到完整可重解析单元）
- [ ] 仅重解析受影响单元（`ParseContext` 从边界起始 token 驱动）
- [ ] 并树：替换 AST 中对应子树（类似 `merge_segments`，下沉到语句级）

### P3.4 增量 check（语义失效传播，2026-08-29 登记）

> 用户需求（2026-08-29）：check 也需要类似增量解析的**激活等待机制**——对
> 激活区域（改动）和**被涉及的链上文件**（依赖链）做局部扫描，而非全量。
> 5 万行实测 check 45s（7k tok/s），全量在典型资产（1k-50k 行）上 5-45s，
> 增量是"编辑→亚秒反馈"的必经路径。
>
> 结构（非从零：**elaboration 底座（ADR-0008）的 module_index /
> connections / signal_graph 就是失效传播的图基础**）：
> 1. **激活**：编辑/保存激活改动区域（源文本 span）。部署形态 = 常驻
>    check 服务 + 文件监听（watch 等待触发，LSP 式），非单次命令。
> 2. **解析层增量**：复用 P3.1/P3.2——span → 增量重解析 → 新 AST。
> 3. **语义失效传播**（增量 check 核心）：改动文件的**影响面 = 三类链**：
>    a. 定义链——改的模块端口/参数/宽度 → 所有实例化它的文件
>       （module_index 反查 inst_sites）
>    b. 实例化链——改的实例化点 → 该文件自身（已增量重解析）+ 连接展开
>       /信号图局部更新
>    c. 信号链——信号图条目变化的信号 → 依赖它的规则（W105 多驱动 /
>       W104 未连接 / UN001）所在文件
>    失效集 = 受影响文件 × 受影响规则 → 只对失效集重跑（规则本身无状态，
>    重跑幂等；**规则声明失效键**——依赖的模块/信号/符号，改动按键传播）。
> 4. **边界诚实**：宏展开 span 映射（P3.3 坑，激活区域在源文本、解析在
>    展开后 token，复用 preprocessor/_bridge.py 锚+残片）；失效集正确性
>    （漏失效 = 漏报，增量最危险——不能精确定位的改动**保守降级**为
>    全量该文件/该规则）；小项目阈值（文件数少时全量重建更快，增量簿记
>    开销反超——自适应切换）。
>
> 前置：P3.1（span 绑定）→ P3.2（增量重解析）→ 本条目。与 P3.3（宏映射）
> 共享坑位；跨文件规则（W104/W105）的增量正确性需要信号图增量更新先验证。

- [ ] 规则失效键声明：每条规则声明依赖键（模块/信号/符号），改动→键→规则映射
- [ ] 三类链传播：定义链/实例化链/信号链 → 失效文件集
- [ ] 信号图增量更新：connects 变化 → signal_graph 局部更新（不重建全图）
- [ ] 保守降级：无法精确定位的改动 → 全量该文件/该规则（防漏报）
- [ ] 小项目阈值：文件数 < N 直接全量（增量簿记开销反超）
- [ ] 部署形态：常驻服务 + watch 激活（触发式，编辑→亚秒反馈）

### P3.5 Rust 热路径下沉（PyO3，远期 2026-08-29 登记）

> 破 Python 动态机制天花板的长期正道（Nuitka 3-5% / PyPy 短任务负收益 /
> 官方 JIT 未转正——均实测闭环，见 references.md）。**形态 = PyO3 热路径
> 下沉，不是全量重写**：Python 壳保留（配置驱动/插件/可模型性是差异化
> 资产），Rust 下沉**引擎通用算法**（lexer 扫描 / 解析器骨架 / doc 布局）——
> 语言知识仍在 TOML/插件层，`check_hardcode` 硬约束不破。
> 前置：P3.1 span 绑定先行（解析器接口稳定后才值得下沉，否则接口跟着
> 语义变白做）；算法层收益先吃干净（parser 记忆化 / P3.4 增量 check 是
> 零语言风险的收益，顺序不能反）。预期：热点下沉后 5-10x（C 级常数），
> 5 万行 check 45s → 5s 级。

- [ ] 解析器骨架下沉：_production token 循环 + pratt 原子匹配（单遍 ~50%）
- [ ] doc 布局下沉：_best/_flat_w 热循环（~36%，已记忆化仍 Python 常数）
- [ ] lexer 扫描下沉：token 化循环
- [ ] PyO3 接口契约：Node/AST 桥接 + span 映射（依赖 P3.1）

### P3.3 已知坑：宏展开下的双向映射

- [ ] **token span 对应的是"展开后"token，不是源文本**：源文本 → 预处理器（展开）→
      lexer → parser，AST 的 token 索引是展开后 token 流的索引
- [ ] 编辑 diff 在**源文本**上做，但 span 在**展开后 token**上——两边对不上，需映射层
- [ ] 预处理器已有反向资产：`preprocessor/_bridge.py`（锚 + 残片回插，marker 定位原文），
      renderer 靠它还原源码位置——增量需要**复用这套桥**，把"展开后 token → 源文本行"打通
- [ ] 条件编译（`ifdef/ifndef`）下编辑，会改变展开结果 → 整段缓存失效，需处理
- [ ] 宏定义本身的编辑（`define` 行改）→ 所有用到该宏的 token 全部失效，不是局部问题

### P3.6 宏体形态分类 + 宏节点进 AST（2026-08-29 登记，v0.2 候选）

> 现状：checker 宏展开是"一刀切全展开"（semantic=True 宏体替换，宏节点不入
> AST）。原意图带宏节点进 parse，但**残缺片段宏**（`= 1'b1`、`[3:0]`、
> `begin`/`end` 半截）会破坏语法边界让 parse 失败 → 只能全展开。方案：先做
> **宏体形态分类**（完整语法单元 vs 残缺片段），完整单元宏保留为 MacroCall
> AST 节点（宏调用 + 展开体子节点），残缺宏维持原位展开——宏边界不丢失
> （P3.3 行号反向映射也受益），展开量大幅下降。**可行性已原型验证 14/14**
> （包装解析法 + 首 token 续接预过滤，tests/_proto_macro_hygiene.py；
> 详案落 docs/references.md「不卫生宏体检测可行性」）。
> 设计约束：包装模板是语言语法知识，不能硬编码进 Python——按 proc_assign_
> rules 先例进 grammar TOML 协议字段（如 macro_hygiene_wrappers），引擎读配置。
> 与 P3.1（span 绑定）相关：宏节点入 AST 后 span 语义要区分"宏调用位"与
> "展开体位"。

- [ ] 宏体形态分类器：包装解析（stmt/decl/expr/port 四包裹）+ 首 token 续接
      预过滤 → 完整语句/完整声明/完整表达式/残缺片段
- [ ] 包装模板进 grammar TOML 协议字段（macro_hygiene_wrappers，语言知识
      不进代码）；引擎通用执行器读配置
- [ ] MacroCall 节点：完整单元宏 parse 时保留节点（宏调用 + 展开体子节点），
      语义检查穿透展开体
- [ ] 单测 + 真实语料验证（ice40/picorv32）分类准确率
- [ ] 与 P3.3 衔接：宏调用位 vs 展开体位的 span 双向映射
- [ ] **预处理器宏策略配置化**（形态分类收敛现 5 种硬编码分支，见
      references.md「不卫生宏体检测可行性·延伸」）：宏体形态（TOML
      包裹模板判定）→ 展开策略（TOML 声明，整行占位/inline 锚/区间
      还原/补分号/token 锚），预处理器变配置驱动策略执行器

## P4 — 多后端输出 + LLVM IR 前端桥（v0.2 商业向候选，非收尾）

### P4.1 多后端输出机制 + LLVM IR 目标插件

> 多后端输出（2026-08-28 立项，合并入 P4）：引擎级"换插件换目标"能力——
> 语言包声明**多个输出插件**（如 c4: asm_gen + llvm_ir），引擎按目标参数
> 选择后端、可并存输出。现状：c4 仅 asm_gen 一个 TransformPlugin
> （@register_plugin 注册、process 守卫根节点按语言区分），多后端 = 引擎
> 支持同语言多输出插件声明 + 目标选择/并存；LLVM IR 是第一个落地目标，
> 也是"同一语言多目标并存"的首个验证场景。

- [ ] **多后端输出机制（引擎级，设计定稿 2026-08-28）**：后端 = **同构渲染器
      实例**——插件系统实例化特定后端的渲染器（与主管线渲染器同一个 Renderer
      类，仅布局配置不同），语言配置留在插件目录，主管线渲染器只负责主 AST
      原样打印。引擎补丁 3 处：① `Renderer.__init__` 加 `layout_dirs` 参数
      （插件级布局目录后加载）；② plugin_loader 识别旁路后端插件（tpc.toml
      `[transform] target = "llvm"`）→ 实例化同构渲染器（布局=插件目录）；
      ③ 旁路插件 process 基于**源 AST**（transform 前，干净形态）→ 产物节点
      交自己的渲染器 → 独立文件输出（复用 mark_extra 通道）。配置复杂度
      = O(插件数)：主管线零改动（无旁路插件时行为与现状一致），新增后端 =
      一个自包含插件目录（transform handler + 布局声明 + target），不给主
      规则配后端布局（后端节点族节点名与主 AST 不重叠，布局天然隔离）
- [ ] **c4 增加 LLVM IR 输出插件**：类比 `_asm.py`（@register_plugin），
      c4 AST → LLVM IR 文本（define/load/store/br/icmp 等基础指令集）
- [ ] 与现有 c4 VM 汇编输出并存（同一语言多目标，验证"换插件换目标"）
- [ ] 验证：c4 小程序（if/while/函数调用）编译为 LLVM IR，`lli`/`clang` 可执行

### P4.2 对外证明能力（信任建立）

- [ ] 选一个垂直场景做端到端 demo（如 DSP 专有语言 / 硬件描述子集 → LLVM IR），
      配"配置驱动 vs 传统方案"的成本对比
- [ ] LLVM/MLIR 社区开源一个 tpc → LLVM IR 插件（技术背书路径）
- [ ] 技术博客/论文："配置驱动语言→IR"（可引用的专业形象）
- [ ] 从小而垂直的厂商切入（大厂有自研团队，小厂缺人决策快）

## 渲染器后续（原 P5 六项已全部闭环，2026-08-27 评估删组）

> P5 六项改进（统一缩进模型 / Doc IR 原语升级 / 布局意图声明化 / 世界 B
> 升级 / 保真度分级 / 兼容验收）全部落地：完成历史见 git log（4bc4b3f 起，
> ADR-0006 阶段 1-5 + 4a/4b；Veryl 渲染层深读闭环 13f29f1 Pad 三件套）。
> 残留缺口评估见 docs/renderer_architecture.md「功能缺口评估」——B2/B3/B4
> 部分解决项均明确"接受"（fits 贪心 / 锚点启发式 / indent_only 留待真实
> 需求驱动）。唯一未闭环后续：

- [ ] **Layout TOML schema 校验**（renderer_architecture.md 缺口 5）：布局
      表达式错误（拼错原语键/类型）静默降级为 None，与 ADR-0003 fail-fast
      精神相悖——可加布局 schema 校验（渲染增强侧，非配置加载主路径）

## SystemVerilog 语言包（远期 backlog，2026-08-27 评估；定位修正 2026-08-29）

> Verilog-2005 全量（P1.8 批次 1-6 + 审查修复）后的自然延伸；当前决策：
> **缓行**——先稳定/玩熟 verilog 全量。规模估算与分期依据见
> docs/references.md「SV 全量规模估算」：语法层全量对标 sv-parser
> （IEEE 1800-2017 Annex A）≈ 净增 800-900 条规则、8-12 个月；
> SV 核心子集（综合常用面）3-4 个月；SVA/class/constraint 是最大三块。
> **定位修正（2026-08-29）**：SV 不在**个人**主体需求内（个人主体 =
> verilog2005 + C 标准）——但**工作需求下会做**，形态为**核心 + 语法插件
> 逐步全量**（与 C 标准插件族同构：SV 核心基线 + class/constraint/SVA 等
> 增量插件叠加，需求驱动到哪叠到哪，而非一次性全量）。阶段 A 即核心包，
> B/C 是可选的增量插件不是"移出"。
> 触发条件：个人侧 = verilog 验证闭环稳定、P1.8 批次 7 候选缺口清完后
> 立项；工作侧 = 出现 SV 需求时按插件族启动核心，随需叠加。

- [ ] 阶段 A：SV 核心（= 核心包基线）——2-state/logic、struct/enum/typedef、
      always_comb/ff/latch、接口+modport、package+import、generate 增强、
      `.name`/`.*` 端口、尺寸字面量
- [ ] 阶段 B（增量插件）：OOP/约束——class、继承、constraint、rand
- [ ] 阶段 C（增量插件）：最长尾——SVA 断言、covergroup、checker、randsequence
      （+ pratt 运算符族/引擎扩展）
- [ ] 阶段 D：收尾——SV 预处理器扩展（宏带参/双反引号）、sv-parser 差分清零、
      lint 精度、渲染打磨

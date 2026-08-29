# ROADMAP（中长期目标 / backlog）

> 从 `TODO.md` 拆分而来（2026-08-27）：本文件承接中长期、非发布阻塞、
> backlog、v0.2 候选类条目；`TODO.md` 只留短期活跃待办。
> 维护纪律同 TODO.md：只列未完成项，**完成即删**（历史在 git log，决策在
> references.md/ADR）；立项启动的项移回 `TODO.md` 短期；调研结论落
> `docs/references.md`，不进本文件。
> P 编号沿用拆分前的原始编号（与 git 历史、交叉引用对应），不重新编号。

## 语言包战略（2026-08-29 定调）

> **主体语言包 = 两个**：Verilog-2005（已闭环，P1.8）+ C23（未来主体）。
> 这两个标准实现后无其他语言包主体需求；其他语言（如 SystemVerilog）
> 如需只做**核心包**（不追全量标准）。c4 定位不变：第二语言验证
> （语言无关性）+ "从零搭语言"模板 + C 核心语法管线支持的子集起步
> （≠ C23——完整 C 是数量级更大的工程，见下）。

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

### P3.3 已知坑：宏展开下的双向映射

- [ ] **token span 对应的是"展开后"token，不是源文本**：源文本 → 预处理器（展开）→
      lexer → parser，AST 的 token 索引是展开后 token 流的索引
- [ ] 编辑 diff 在**源文本**上做，但 span 在**展开后 token**上——两边对不上，需映射层
- [ ] 预处理器已有反向资产：`preprocessor/_bridge.py`（锚 + 残片回插，marker 定位原文），
      renderer 靠它还原源码位置——增量需要**复用这套桥**，把"展开后 token → 源文本行"打通
- [ ] 条件编译（`ifdef/ifndef`）下编辑，会改变展开结果 → 整段缓存失效，需处理
- [ ] 宏定义本身的编辑（`define` 行改）→ 所有用到该宏的 token 全部失效，不是局部问题

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

## SystemVerilog 语言包（远期 backlog，2026-08-27 评估；战略调整 2026-08-29）

> Verilog-2005 全量（P1.8 批次 1-6 + 审查修复）后的自然延伸；当前决策：
> **缓行**——先稳定/玩熟 verilog 全量。规模估算与分期依据见
> docs/references.md「SV 全量规模估算」：语法层全量对标 sv-parser
> （IEEE 1800-2017 Annex A）≈ 净增 800-900 条规则、8-12 个月；
> SV 核心子集（综合常用面）3-4 个月；SVA/class/constraint 是最大三块。
> **战略调整（2026-08-29）**：语言包主体收敛为 verilog2005 + C23，SV
> 不在主体需求内——如需只做**核心包**（阶段 A 综合常用面），不再追全量
> （SVA/class/constraint 等阶段 B/C 移出范围，除非未来需求驱动）。
> 触发条件：verilog 验证闭环稳定、P1.8 批次 7 候选缺口清完后立项；
> 立项时从本文件移回 TODO.md。

- [ ] 阶段 A：SV 核心（= 未来若做 SV 的核心包范围）——2-state/logic、
      struct/enum/typedef、always_comb/ff/latch、接口+modport、
      package+import、generate 增强、`.name`/`.*` 端口、尺寸字面量
- [ ] ~~阶段 B：OOP/约束——class、继承、constraint、rand~~（战略调整移出）
- [ ] ~~阶段 C：最长尾——SVA 断言、covergroup、checker、randsequence~~（战略调整移出）
- [ ] 阶段 D：收尾——SV 预处理器扩展（宏带参/双反引号）、sv-parser 差分清零、
      lint 精度、渲染打磨

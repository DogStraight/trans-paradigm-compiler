# ROADMAP（中长期目标 / backlog）

> 从 `TODO.md` 拆分而来（2026-08-27）：本文件承接中长期、非发布阻塞、
> backlog、v0.2 候选类条目；`TODO.md` 只留短期活跃待办。
> 维护纪律同 TODO.md：只列未完成项，**完成即删**（历史在 git log，决策在
> references.md/ADR）；立项启动的项移回 `TODO.md` 短期；调研结论落
> `docs/references.md`，不进本文件。
> P 编号沿用拆分前的原始编号（与 git 历史、交叉引用对应），不重新编号。

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
- [ ] CI 补强（未做）：PR 快速 fuzz（~500 轮）+ 夜间长跑 + edge/differential
      门禁接入

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

## P4 — LLVM IR 前端桥（v0.2 商业向候选，非收尾）

### P4.1 LLVM IR 目标插件

- [ ] c4 增加 LLVM IR 输出插件（类比 `_asm.py`，c4 AST → LLVM IR 文本：
      define/load/store/br/icmp 等基础指令集）
- [ ] 与现有 c4 VM 汇编输出并存（同一语言多目标，验证"换插件换目标"）
- [ ] 验证：c4 小程序（if/while/函数调用）编译为 LLVM IR，`lli`/`clang` 可执行

### P4.2 对外证明能力（信任建立）

- [ ] 选一个垂直场景做端到端 demo（如 DSP 专有语言 / 硬件描述子集 → LLVM IR），
      配"配置驱动 vs 传统方案"的成本对比
- [ ] LLVM/MLIR 社区开源一个 tpc → LLVM IR 插件（技术背书路径）
- [ ] 技术博客/论文："配置驱动语言→IR"（可引用的专业形象）
- [ ] 从小而垂直的厂商切入（大厂有自研团队，小厂缺人决策快）

## P5 — 渲染器改进（统一缩进模型 + Doc 原语升级 + 布局意图声明化）

> 来源：2026-08-25 renderer 审查 + 框架调研（topiary/dprint/prettier/verible/
> cmake-format，落 docs/references.md）。定性：**改进非重写**（Doc IR 内核正确、
> 160 处布局 TOML 是语言知识存量、门禁原样承接）。
> 已落地阶段（1-5 + 4a/4b，ADR-0006）：缩进参数收敛、align/fill/line_suffix
> 原语、intent 声明、多遍引擎 PassKind/criterion、注释 attachment、保真度分级
> ——完成历史见 git log（a1b29ed/023d939 起）与 ADR-0006，不在此复述。

- [ ] **统一缩进模型**：清理幽灵 indent 参数（原语协议签名内，只传递不生效）；
      缩进来源归一（style.indent_str / body_cfg["indent"] / expr indent）为
      单一缩进上下文，明确组合规则与优先级
- [ ] **Doc IR 原语升级**：补 align（对齐进 Doc 模型）/ fill（流式折行）/
      lineSuffix（尾注释锚定）+ 注释 attachment 机制（Prettier 生产验证过的
      原语集）；layout() 算法继承扩展
- [ ] **布局意图声明化**：语言包声明"结构 → 布局意图"（对齐/紧凑/折行/锚定），
      引擎推导具体 Doc，消灭手拼 Break/Nest（topiary 封闭式理念——但节点级
      注解到不了跨行对齐，需多遍引擎：对齐遍/折行遍/注释遍）
- [ ] **世界 B 升级**：column_align/inst_port/wrap 从手写文本 pass 升级为引擎
      内建遍（量化布局拒绝准则，cmake-format 借鉴）；"行 + 所属 AST 节点"的
      带结构行，根治 wrap 拆行后行号漂移。
      注（2026-08-27）：inst_port 注释行透明分组 + restore 锚定精确化已闭环
      （见 P1.5），消除端口组间注释导致的非幂等振荡；serv_top 畸形输入
      3 轮收敛已由 lexer 修复闭环（2861ce8，未闭合块注释吞换行）。
      "对齐进 Doc IR 参与 fits 判定"（Pad 三件套已落地 renderer，inst_port
      仍是渲染后文本 pass）的彻底收敛仍需本升级
- [ ] **保真度分级**：规范化程度显式可配（完全重排 / 保留空行 / 仅缩进），
      解决"规范化 vs 保真"方向矛盾（verible token 级保真为参照）
- [ ] **兼容与验收约束**：160 处布局 TOML 语义兼容（老语言包零改写）；验证
      门禁原样承接（real 保真度守卫 / vs Verible 差分 124 例 / 幂等 / e2e）

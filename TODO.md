# TODO（纯待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 当前验证基线（2026-08-27）：1098 pytest 全绿 + run_all 93（FAIL 0，real 组
> 保真度守卫）+ pyright strict 0 errors（1.1.413）+ lint recall 31/31 零误报 +
> 覆盖率 83.39%（fail_under 80）+ vs Verible 差分 124 例。

## P1 — Verilog 实例完善

### P1.8 Verilog 语法补全 + 仿真语法插件化（发布前置）

> 可综合子集进主包、仿真语法进插件（plugins/sim）；完成后主包纯净可综合 = 发布基线。
> 语法对照：docs/ieee1364_2005_annex_a.md（67 节）。已入 plugins/sim 的语法见
> docs/release_checklist.md（A.2.1.3 event / A.6.3 fork-join / A.6.4 force-release
> / A.6.5 时序控制）。

- [ ] **门级/开关原语**（A.3）：and/or/nand/nor/xor/xnor/buf/not + bufif0/bufif1/
      notif0/notif1 + pmos/nmos/tran 系列 —— 综合类，进主包
- [ ] **UDP**（A.5）：primitive/table/endprimitive —— 综合类（老设计），进主包
- [ ] **assign/deassign（过程连续赋值，A.6.4）**—— 未做：与模块级 assign 同
      keyword.assign 起始，会干扰 linter 的语句发现（assign 被误判为过程规则），
      低频构造不做（模块级 assign 已覆盖）
- [ ] **specify 块**（A.7）：specparam、$setup/$hold/$width 等时序检查 —— 时序分析，
      仿真/综合边界，评估放哪（可能单独 plugins/specify 或并入 sim）
- [ ] config/defparam（A.1.5 / A.2.4）—— 罕见，视需要

### P1.4 折行（wrap）完善

- [ ] 函数/任务声明类（FuncDecl/TaskDecl）折行特殊处理——函数体声明行以分号
      结尾但块以 endfunction 收，需确认折行时块内声明不截断
- [ ] picorv32 超宽行 75→73（其余无安全断点保留）——检查剩余 73 行是否需要
      更细断点（长标识符/括号内/块头条件行）
- [ ] 块头行（`if (...) begin` 超宽条件）折行——当前 wrap 只折分号行，块头不折，
      需 boundary 支持"块头条件续行"识别

### P1.6 wrap 升级：惩罚值驱动折行搜索（Verible 参考）

> 断点惩罚表（break_penalties）+ over_column_penalty 已配置化在
> [formatter.wrap]（tpc.toml），见 docs/known_limitations.md "Line wrapping
> is width-based"。以下为剩余待办。

- [ ] 分区策略概念对齐：tpc 的品类对齐 ≈ kTabularAlignment，但缺"参数列表/
      端口列表/声明"的独立策略——Verible 每种列表一个策略，tpc 可评估
      按规则类型区分 wrap/stack 策略
- [ ] 验证：折行结果对比现有贪心（picorv32 75 超宽行 → 惩罚搜索能否折更多、
      结构是否更稳）——已部分验证（65 行），完整对比待做

### P1.5 已知缺陷收尾

- [ ] **invert 嵌套引用遗留（typed_ports，L2/L3）**：L1 已防御
      （test_nested_invert_no_skip_leak）；L2 未修——invert 对含嵌套引用的 role，
      嵌套展开端口（inner_* 方向反转）不参与反转（invert 回调 resolve 期拿的是
      目标 role 原始端口数据，需用完整展开端口解析：普通端口拍平 + _ref_callbacks
      合并）；L3 未修——invert 引用的 role 定义在后时 _ref_callbacks 尚未构建
      （primitive 单遍 DFS，需两遍遍历/pending 重试）。README Known limitations
      已记录。
- [ ] **pratt 前缀吞注释（既有缺陷，2026-08-26 记录）**：pratt_parser 前缀
      位置把 COMMENT 当续行分隔跳过（`a + /* c */ b` 的注释静默丢失，不记录
      任何通道）——改动前即如此（非回归）。修法：pratt 跳注释时记录（挂
      当前表达式节点 inline_after 或 anchors），与 2b-2 的 token 标注机制衔接

### P1.7 命名约定检查（analyzer 层插件，Sigasi 借鉴）

> 放分析层插件（语义层 Symbol 才有 kind 可区分名字种类）；逻辑进引擎原语，
> pattern 是语言知识进 TOML。

- [ ] `analyzer/primitives/_naming.py`：`@register("naming_check")` 原语——
      复用 `_symbol._extract_names` 提取名字 → `re.fullmatch` 检查 →
      违规报诊断（`_context.report`，code N001，level warning）
- [ ] 触发零机制改动：声明规则 `[RuleName.analyzer]` 加
      `primitives = ["naming_check"]`（`_is_primitive_triggered` 对未知原语
      走 primitives 列表，已支持）
- [ ] 配置（Sigasi 式）：全局 pattern 表按 kind 分发——TOML 建议
      `[analyzer.naming]`（或插件 tpc.toml）下 `[analyzer.naming.rules.<kind>]`
      `pattern` + `match = "positive|negative"`；UI 预设 lowercase/uppercase/
      IGNORE 可做默认 pattern 快捷值（如 `case = "upper"` 自动展开为
      `^[A-Z][A-Z0-9_]*$`），RE2→Python re 语法兼容
- [ ] 30 类 kind 映射：Verilog 声明规则 symbol.kind 对齐 Sigasi 类别
      （module→MODULE_NAME、wire/reg→NET_NAME、var→VAR_NAME、port→PORT_NAME、
      parameter→PARAMETER_NAME 等），kind 未配置的规则跳过
- [ ] 注册：`analyzer/primitives/__init__.py` 加 `from . import _naming`
- [ ] 与 pre_scan 关系确认：pre_scan 是 lexer 期名字收集（parser 提示），
      naming_check 是语义层规范检查，互不冲突，文档注明

### P1.9 tpc-check 诊断模型升级（pylance 化，2026-08-25 研判入册）

> 来源：docs/references.md「Verilog 静态检查工具群」深调研（verible-lint / Verilator
> `--lint-only` / slang / svlint / hdl_checker）。目标场景：模型生成 v 文本 →
> tpc-check 当 pylance 用（即时诊断、机器可读、可豁免）。
> 节奏：开源初期做小而稳——只推第一步低成本项，大项（规则表配置化/LSP）积蓄。

- [ ] 第二步：检查规则表 + severity 配置（规则 ID → 描述 → 默认 severity → 用户覆盖，
      对齐 svlint `.svlint.toml` / verible rule-sets；tpc 配置驱动哲学在检查侧的落地），
      与 P1.7 naming_check 合并推进
- [ ] 路线观察（不立项）：LSP 服务化（hdl_checker「封装后端 → LSP Diagnostic」参照，
      零依赖 stdlib 手写 jsonrpc 可行但需编辑器接入需求驱动）；语义级警告
      （WIDTH/LATCH/MULTIDRIVEN 类需类型推断，超出浅层语义定位）

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
      （见 P1.5），消除端口组间注释导致的非幂等振荡；但"对齐进 Doc IR 参与
      fits 判定"（Pad 三件套已落地 renderer，inst_port 仍是渲染后文本 pass）
      的彻底收敛仍需本升级——当前剩余 serv_top 畸形输入 3 轮收敛即此根源
- [ ] **保真度分级**：规范化程度显式可配（完全重排 / 保留空行 / 仅缩进），
      解决"规范化 vs 保真"方向矛盾（verible token 级保真为参照）
- [ ] **兼容与验收约束**：160 处布局 TOML 语义兼容（老语言包零改写）；验证
      门禁原样承接（real 保真度守卫 / vs Verible 差分 124 例 / 幂等 / e2e）

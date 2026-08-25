# TODO（纯待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 当前验证基线（2026-08-25）：806 pytest 全绿 + e2e 93（FAIL 0，含 real 保真度守卫）+
> lint recall 31/31 零误报 + 覆盖率 83.39%（fail_under 80）+ vs Verible 差分 124 例。

## P1 — Verilog 实例完善

### P1.8 Verilog 语法补全 + 仿真语法插件化（发布前置）

> 可综合子集进主包、仿真语法进插件（plugins/sim）；完成后主包纯净可综合 = 发布基线。
> 语法对照：docs/ieee1364_2005_annex_a.md（67 节）。
> 已落地：A.2.1.3 event 声明 / A.6.3 fork-join / A.6.4 force-release、disable /
> A.6.5 时序控制（#delay、wait、@event、->）已入 plugins/sim（发布基线事实见
> docs/release_checklist.md）。

- [ ] **门级/开关原语**（A.3）：and/or/nand/nor/xor/xnor/buf/not + bufif0/bufif1/
      notif0/notif1 + pmos/nmos/tran 系列 —— 综合类，进主包
- [ ] **UDP**（A.5）：primitive/table/endprimitive —— 综合类（老设计），进主包
- [ ] **assign/deassign（过程连续赋值，A.6.4）**—— 未做：与模块级 assign 同
      keyword.assign 起始，会干扰 linter 的语句发现（assign 被误判为过程规则），
      低频构造不做（模块级 assign 已覆盖）
- [ ] **specify 块**（A.7）：specparam、$setup/$hold/$width 等时序检查 —— 时序分析，
      仿真/综合边界，评估放哪（可能单独 plugins/specify 或并入 sim）
- [ ] config/defparam（A.1.5 / A.2.4）—— 罕见，视需要
- [ ] 插件骨架验证：plugins/sim/tpc.toml + token_ext/规则，verilog tpc.toml
      [plugins] enabled 控制挂载；挂载/卸载无残留（插件机制已实证——typed_ports/
      semantic_check 即插拔模式，验证思路照此）
- [ ] 发布收尾联动：语法补全后跑全量回归 + real 组（SweRV dmi 样本）+ fidelity
      基线；仿真插件默认关闭不影响可综合子集纯净性

### P1.4 折行（wrap）完善

- [ ] 函数/任务声明类（FuncDecl/TaskDecl）折行特殊处理——函数体声明行以分号
      结尾但块以 endfunction 收，需确认折行时块内声明不截断
- [ ] wrap 断点：位选择 `[31:25]` 已修（[] 深度跟踪）；三目只断 `:` 后已修；
      concat `{a, b, ...}` 超宽不折（无顶层断点）——评估是否需要 concat 断点
- [ ] picorv32 超宽行 75→73（其余无安全断点保留）——检查剩余 73 行是否需要
      更细断点（长标识符/括号内/块头条件行）
- [ ] 块头行（`if (...) begin` 超宽条件）折行——当前 wrap 只折分号行，块头不折，
      需 boundary 支持"块头条件续行"识别
- [ ] wrap 幂等回归测试补强（现有 test_wrap/test_idempotent 覆盖折行场景）

### P1.6 wrap 升级：惩罚值驱动折行搜索（Verible 参考）

> 已落地：断点惩罚表（break_penalties）+ over_column_penalty 概念，配置化在
> [formatter.wrap]（tpc.toml），验证 picorv32 超宽行 75→73→65（见
> docs/known_limitations.md "Line wrapping is width-based"）。

- [ ] 分区策略概念对齐：tpc 的品类对齐 ≈ kTabularAlignment，但缺"参数列表/
      端口列表/声明"的独立策略——Verible 每种列表一个策略，tpc 可评估
      按规则类型区分 wrap/stack 策略
- [ ] 验证：折行结果对比现有贪心（picorv32 75 超宽行 → 惩罚搜索能否折更多、
      结构是否更稳）——已部分验证（65 行），完整对比待做

### P1.5 已知缺陷收尾

- [ ] **多声明品类对齐（Verible kDataDeclaration 参考）**：`reg [1:0] state, next;`
      被 `_is_multidecl` 跳过（多声明不参与列对齐），同组 `reg [3:0] bit_cnt;`
      按最大位宽列对齐——两行观感不一致。根因 = 语义列模型只支持单声明，
      多声明行直接 return None 保留原文。
      Verible 做法：声明 = 类型头 + 实例列表（kDataDeclaration → kRegisterVariable/
      kNetVariable 列表），每个实例（含 `state`/`next`）独立参与 kTabularAlignment
      列对齐，不跳过。tpc 已有对应结构（DeclaratorList.items = Declarator 列表），
      缺的是 _extract_semantic 对多声明的逐项列提取。
      方案：column_align 支持多声明——每行按 `,` 顶层分隔拆多个对齐单元，
      同组内所有单元的名字列对齐到同一基准；`reg a = 1, b = 2` 的 init 列也参与
      （Verible 的实例对齐含 init 列）。注意 fidelity：real 组（darkriscv
      `integer clocks=0, running=0, ...`、picorv32 `reg [63:0] next_rs1, ...`）会变，
      需重跑 real 组更新基线。
- [ ] **transform 实例名 hash 稳定性**：`u_spi_master_xxx` 的 salt 无法复现
      ref（spi_inf X 路径 ratio 0.9862 因 hash 差异）——期望 ratio 到 1.0，
      去掉"hash 可容忍"例外（判断 salt 逻辑是否与生成 ref 时漂移）
- [ ] **变换路径注释恢复**：当前禁用（only_tpc 只回插 tpc marker），普通注释
      在展开后丢失——长远应精确恢复而非禁用（锚点漂移的根本解决）
- [ ] **invert 嵌套引用遗留（typed_ports，L2/L3）**：L1 已防御
      （test_nested_invert_no_skip_leak）；L2 未修——invert 对含嵌套引用的 role，
      嵌套展开端口（inner_* 方向反转）不参与反转（invert 回调 resolve 期拿的是
      目标 role 原始端口数据，需用完整展开端口解析：普通端口拍平 + _ref_callbacks
      合并）；L3 未修——invert 引用的 role 定义在后时 _ref_callbacks 尚未构建
      （primitive 单遍 DFS，需两遍遍历/pending 重试）。README Known limitations
      已记录。
- [ ] **concat 无折行**：`{a, b, c, ...}` 超宽保持原样，评估加 concat 断点

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

## P2 — 工程化收尾（发布准备）

### P2.2 发布收尾

> 0.1.0 Alpha 已发布（2026-08-22，release_checklist 走完）；以下为软缺口。

- [ ] 覆盖率远期目标 ≥90%（当前 83.39%——source=引擎包真实基线，需补
      transform/renderer 等薄弱区）
- [ ] 用户视角文档增量：现有 docs/ 偏引擎作者视角（MODEL_INDEX/ADR/
      component_protocol）；发布只需 README Quick start 补齐，暂不新写用户手册。

### P2.3 验证吞吐优化（backlog，非发布阻塞，2026-08-22 记录）

> 动机：验证（fuzz/差分/edge）是"验证附着于配置驱动语言定义"的差异化能力，
> 但当前吞吐 ~9 iter/s（实测单次迭代 ~110ms：setup_grammar ~40% + 管线内部
> 幂等复跑 2x 冗余 + 单线程）。模型无机会手动跑大规模验证，快速验证层是
> "模型写配置 → 自动验证闭环"成立的前提。详见 tests/fuzz/README.md。
> CI 已接入（.github/workflows/ci.yml，3 Python × 2 OS 矩阵）。

- [ ] fuzz harness 吞吐三件套：
  - [ ] 语法表/parser 跨迭代缓存（不重建）→ ~2.5x
  - [ ] fuzz 模式关闭管线内部幂等复跑（oracle 自管）→ ~1.8x
  - [ ] multiprocessing 多 worker → ~8x（合计 ~30-40x：100k 轮 ~1 分钟）
- [ ] 随机合法程序 → 对拍 Verible：接受域从 124 人工语料推到统计意义
      （GrammarFuzzer 生成器已就绪，缺接线）
- [ ] 阶段级 fuzz（lexer/parser-only 不变量，比全管线再快 10-50x）
- [ ] 引擎编译提速评估（Nuitka 已实证 exe，编译引擎是后手）
- [ ] CI 补强（未做）：PR 快速 fuzz（~500 轮）+ 夜间长跑 + edge/differential
      门禁接入

### P2.5 引擎约定机器化（边界检查器，2026-08-24 记录，非发布阻塞）

> 把 AGENTS.md 硬约束（语言知识不进代码 / 路径规范 / Doc 反向引用）从"文档约定"
> 变成自动检查器（纯 Python 零依赖，挂 CI）；与 P2.3 的关系：P2.3 管验证吞吐，
> 本项管"约定即门禁"。

- [ ] **`tools/policy/check_hardcode.py`（第一优先，零整改成本预期）**：
  规则表驱动（编号规则，同 check_architecture 风格），os 扫描 + 正则，零依赖：
  - [ ] 规则 1（核心卖点机器化）：引擎目录 .py 不得出现语言具体 token（词表从
        grammar/ 实际 keyword 提取，防硬编码词表漂移）——"语言知识不进代码"
        从文档约定变成自动门禁
  - [ ] 规则 2：引擎 .py 不得硬编码 `grammar/verilog` 类相对路径（P2.4 修过的
        硬编码路径问题防复发）
  - [ ] 规则 3（可选）：文件头 `Doc:` 反向引用缺失检查（docs/README.md 约定）
  - [ ] 验证：先本地跑现状（应全干净）→ 零整改接入 CI（test 矩阵加一步
        `python tools/policy/check_hardcode.py`）

- [ ] **case 即文档轻量版（第二优先）**：关键用例整理成"每行为一个 case + 显式
      期望"的可读清单（input/expect 声明式组织，参考 e2e samples 目录风格）；
      tpc 差分/fuzz 已覆盖正确性，增量价值是"语义单例文档化"（docs/ 资产，
      配合切片哲学），不新建测试框架

- [ ] **阶段间契约文档评估（低优先）**：tpc 已有 MODEL_INDEX 跳转表，评估是否补
      "阶段间契约"文档（各管线阶段接口的层间边界描述）

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

> 来源：2026-08-25 renderer 审查（body_cfg["indent"] 死配置/幽灵参数/重复实现）
> + 框架调研（topiary/dprint/prettier/verible/cmake-format，落 docs/references.md）。
> 定性：**改进非重写**——Doc IR 内核（Wadler）正确、160 处布局 TOML 是语言知识
> 存量、验证门禁（real 保真度/差分/幂等）原样承接；缺的是原语丰富度与模型统一。
> 动手前先写 ADR-0006（边界分析 + 资产盘点 + 迁移策略作为输入文档）。
> 第一步已落地（a1b29ed）：body_cfg["indent"] 三态生效 + render_inline 合并 +
> tail_break 转换删除（测试 tests/engine/renderer/test_renderer_body_indent.py）。
> 阶段 1 已落地（ADR-0006）：幽灵 indent 参数从原语协议签名/渲染回调链
> 全部移除（render_node/render_inline/render_body/eval_expr/各原语 handler/
> Renderer._render_*），缩进换算收敛为 Renderer._indent(level) 唯一换算点
> （body_cfg["indent"] 与 expr {indent: N} 均以其为单位）；806 pytest +
> e2e 全绿 + pyright renderer 0 errors。

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
      带结构行，根治 wrap 拆行后行号漂移
- [ ] **保真度分级**：规范化程度显式可配（完全重排 / 保留空行 / 仅缩进），
      解决"规范化 vs 保真"方向矛盾（verible token 级保真为参照）
- [ ] **兼容与验收约束**：160 处布局 TOML 语义兼容（老语言包零改写）；验证
      门禁原样承接（real 保真度守卫 / vs Verible 差分 124 例 / 幂等 / e2e）

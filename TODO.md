# TODO（纯待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 完成基线（当前验证过的事实）：
> - 613 测试全过；PicoRV32 token 完整硬基线（format 不改 token）
> - c4 第二语言完成（.c → c4 VM 汇编，6 集成测试）——语言无关主张实证
> - formatter 接入管线 + 幂等 + 品类对齐 + 风格参数化 + **wrap 折行恢复**
>   （end_case 分号化试点 6 条：assign 3 + wire/reg/integer 3，折行幂等 + 管线 0 错）
> - 后置 lint → 幂等检查（非展开路径第二遍 parse truncated 即 FAIL）+ transform
>   两条路径（P 保留对比输入 / X 展开对比 ref）+ lint_err 命名统一 ref_ 前缀
> - 预处理器宏相关完成（带参宏/条件编译还原/指令原位回插 + primitives 单测 19 项）
> - typed_ports 增强渲染双路径（展开/保留，expand_enhanced）+ nested/invert 验证
> - 数字形态配置化完成（声明→FSM 生成器 + 语言包声明 + signed 's + 0'b1 标准拒绝）

## P1 — Verilog 实例完善

### P1.3 SV 插件化（SV 语法做成插件，插拔动态适配）

> 来源：2026-08-13 方向——SV 基础已内嵌（logic/always_ff/always_comb 在
> verilog 语言包），但 SV 特性会持续增长（interface/class/struct/assertion 等），
> 内嵌会让 verilog 语言包膨胀。做成**独立插件**（如 plugins/sv）：
> 插拔动态适配——verilog 包按需挂载 SV 插件，接口/class 等新特性进插件不进主包。
>
> **2026-08-16 更新（方向修正）**：SV 产生式量大（1800 Annex A 有 400+ 条
> vs 1364 的 200 条），插件形式不划算——**开独立语法实例**（grammar/sv/ 类似
> c4 的语言包）。已先行摘除 verilog 主包内嵌的 SV 特性（见下），SV 实例落地后
> 从实例恢复。

- [x] **SV 特性摘除（已完成，647 全过 + run_all 93 全绿）**：
      - token.toml 删 12 个孤儿 SV/非标准 token（import/from/as/break/continue/
        in/interface/al_ff/al_comb/param/pass）——零引用零破坏
      - 删有引用的 4 个：logic/always_ff/always_comb/property（RegDecl/AlwaysStmt/
        CallStmt/InstStmt 规则引用同步改纯 Verilog；PropertyStmt 规则保留为占位注释）
      - pre_scan 删 interface decl 段 + context_keywords 删 logic
      - 删 tests/formatter/test_sv.py（SV 专项）；test_linter_slicer 断言改纯 always
      - picorv32 样本 `restrict property` 注释化（SVA→等效 Verilog），fidelity 缓存重建
- [ ] SV 实例骨架：grammar/sv/tpc.toml + 语法文件（token_ext/规则），
      verilog tpc.toml [plugins] enabled 控制挂载（或独立语言包单语言选择）
- [ ] 恢复已摘除的 4 特性到 SV 实例：logic/always_ff/always_comb/property
- [ ] 补充 SV 主要特性：package/interface/class/typedef/struct/enum/import
- [ ] 验收语料（Sigasi demo，E:\test）：swerv_types.sv（package/typedef/struct/
      enum）、lsu_bus_intf.sv（interface/import）、tutorial class_*.svh（class）
- [ ] 验证：挂载/卸载 SV 插件后 verilog 包行为正确（插拔无残留）

> **语法蓝本就绪（2026-08-16）**：IEEE 1800-2023 PDF 在项目根目录，
> Annex A 已提取为 `docs/ieee1800_2023_annex_a.md`（86 节、2557 行，
> A.1 源文本 / A.2 数据类型 / A.6 语句 / A.8 表达式 / A.9 其他，完整 BNF）。
> `scripts/ieee_grammar_to_md.py` 已参数化（--title/--source），可重跑刷新。
> SV 实例的产生式按此 Annex A 切片，逐特性落地（先 package/interface/class）。

### P1.8 Verilog 语法补全 + 仿真语法插件化（路线 1，发布前置）

> 来源：2026-08-16 决策。两条路权衡后选路线 1：
> ①补全 1364-2005 剩余语法（可综合子集进主包）
> ②仿真语法拆成独立插件（plugins/sim，按需动态挂载）
> ③完成后 Verilog 主包纯净可综合 → **发布基线**。
> 路线 2（完整 SV + UVM）记入 P1.3 后续，不在发布前置。
> 语法对照：docs/ieee1364_2005_annex_a.md（67 节）。

- [ ] **门级/开关原语**（A.3）：and/or/nand/nor/xor/xnor/buf/not + bufif0/bufif1/
      notif0/notif1 + pmos/nmos/tran 系列 —— 综合类，进主包
- [ ] **UDP**（A.5）：primitive/table/endprimitive —— 综合类（老设计），进主包
- [ ] **时序控制**（A.6.5）：#delay、wait、@event、-> 事件触发 —— 仿真，进插件
- [ ] **fork/join 并行块**（A.6.3）：fork/join/join_any/join_none —— 仿真，进插件
- [ ] **force/release、assign/deassign**（A.6.4）—— 仿真，进插件
- [ ] **specify 块**（A.7）：specparam、$setup/$hold/$width 等时序检查 —— 时序分析，
      仿真/综合边界，评估放哪（可能单独 plugins/specify 或并入 sim）
- [ ] config/defparam（A.1.5 / A.2.4）—— 罕见，视需要
- [ ] 插件骨架验证：plugins/sim/tpc.toml + token_ext/规则，verilog tpc.toml
      [plugins] enabled 控制挂载；挂载/卸载无残留（复用 P1.3 插拔验证思路）
- [ ] 发布收尾联动：语法补全后跑全量回归 + real 组（SweRV dmi 样本）+ fidelity
      基线；仿真插件默认关闭不影响可综合子集纯净性

### P1.4 折行（wrap）完善——end_case 分号化

> 来源：2026-08-15。wrap 已恢复（build_engine 末尾注册，断点取运算符之后、
> boundary 行尾运算符续行识别 + decl_op_cont 豁免），但根因是**语法把"行"当
> 语句边界**——27 条规则 "end_case 含 newline 且 production 以分号结尾"。
> 已试点改 6 条（assign 3 + wire/reg/integer 3），语句边界由分号决定后折行
> 插入的 newline 不再截断。剩余规则需逐条验证。

- [ ] 剩余 21 条分号收尾规则 end_case 改分号（ForLoop/EventWait/SubroutineCall/
      TaskCall/声明类等）——逐条改 + 折行场景回归
- [ ] 函数/任务声明类（FuncDecl/TaskDecl，end_case 含 endfunction/endtask）特殊处理——
      end_case 不能简单改分号（函数体声明行以分号结尾但块以 endfunction 收），
      需确认折行时块内声明不截断
- [ ] wrap 断点：位选择 `[31:25]` 已修（[] 深度跟踪）；三目只断 `:` 后已修；
      concat `{a, b, ...}` 超宽不折（无顶层断点）——评估是否需要 concat 断点
- [ ] picorv32 超宽行 75→73（其余无安全断点保留）——检查剩余 73 行是否需要
      更细断点（长标识符/括号内/块头条件行）
- [ ] 块头行（`if (...) begin` 超宽条件）折行——当前 wrap 只折分号行，块头不折，
      需 boundary 支持"块头条件续行"识别
- [ ] wrap 幂等回归测试补强（现有 test_wrap/test_idempotent 覆盖折行场景）

### P1.6 wrap 升级：惩罚值驱动折行搜索（Verible 参考）

> 来源：2026-08-15 调研 Verible（Google/chipsalliance，C++ CST 驱动 formatter）。
> Verible 的折行模型是"**策略 + 惩罚 + 搜索**"：每个语法节点在 unwrap 时分配
> 分区策略（kFitOnLineElseExpand/kWrap/kTabularAlignment/kStack 等），断行
> 决策 = 在全部 append/wrap 组合里找总惩罚最小的方案（Dijkstra 最短路，
> `over_column_limit_penalty=10000` 超列惩罚巨大，`max_search_states` 限搜索量）。
> tpc 的 wrap 是**单点贪心**（最右安全断点）——断点 A 让后续更优的情况处理不了。
> 不做完整 Dijkstra，做"候选断点 + 惩罚"的局部最优即可。

- [x] 断点惩罚表：候选断点（逗号/逻辑/算术/三目）各带惩罚值（参考 Verible
      token-annotator），选总惩罚最小的断点组合而非最右断点。配置化在
      [formatter.wrap]（tpc.toml：break_penalties + over_column_penalty）。
      验证：picorv32 超宽行 75→73→65（惩罚模型折掉贪心折不了的），幂等保持
- [x] `over_column_penalty` 概念：允许折行后某行略超列但加重惩罚，权衡
      "折两行但某行略超" vs "不折全超"——实测最右断点让首行超 7 列（70 惩罚）
      被惩罚模型放弃，选两行都不超的方案
- [ ] 分区策略概念对齐：tpc 的品类对齐 ≈ kTabularAlignment，但缺"参数列表/
      端口列表/声明"的独立策略——Verible 每种列表一个策略，tpc 可评估
      按规则类型区分 wrap/stack 策略
- [ ] 验证：折行结果对比现有贪心（picorv32 75 超宽行 → 惩罚搜索能否折更多、
      结构是否更稳）——已部分验证（65 行），完整对比待做

### P1.5 已知缺陷收尾

> 来源：2026-08-15 排查中确认的遗留项，非新增方向，逐项修复。

- [x] **@ElseChain 跨行匹配缺陷**：`end else` 换行后 `else if` 关联断裂——
      语句发现把折行的 else 链截断（2026-08-17 已修复，见下）
      > 修复：discovery 容器边界改 _container_end（matcher 按完整 production 匹配，
      > 覆盖 else chain）+ matcher 块分支优先 block_end（修 `end else` 同行跳过头）+
      > 延续关键字（else/default）跳过 + IfBlock/IfStmt 移除 end_case=newline。
      > 验证：653 全过 + run_all 93 绿 + 新增 6 回归测试（TestElseChainDiscovery）。
- [ ] **未定义 task/function 调用检测（语义层，linter 边界明确）**：`bogusstmt;`
      语法合法（可能是无参 task 调用），linter 不判语义（勿在 linter 修——id 开头
      未知语句漏检是设计权衡）。落点 = analyzer：未定义调用是"纯语义级别"。
      > 已验证（2026-08-17）：当前 analyzer 也不报（Identifier 配 identifier_ref=true
      > 只 attach _symbol_ref 不产警告，避免隐式 net 误报）；给 SubroutineCall/
      > TaskCallStmt 配 identifier_ref="callee" 会误报已定义 task（known_task）——
      > **前置：语法里无任何规则配 symbol_declare（symbol={...}），task/function
      > 声明根本没入符号表**。需先给 TaskDecl/FuncDecl 配 symbol_declare（声明符号化），
      > 再给调用规则配 identifier_ref="callee"（字符串 iref 才报 W001）。
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
- [ ] **concat 无折行**：`{a, b, c, ...}` 超宽保持原样，评估加 concat 断点
- [ ] **fidelity 缓存模式区分**：key 已带 @expand/@plain 后缀防互串，但需确认
      首次运行后缓存语义正确（不同模式不互相污染）

### P1.7 命名约定检查（analyzer 层插件，Sigasi 借鉴）

> 来源：2026-08-16 Sigasi 调研（行为观察 + 公开文档参考）。**放分析层插件**
> （不放在 linter——lexer 期已有 pre_scan 符号预检测，但那是给 parser 的提示；
> 语义层 Symbol 才有 kind 可区分名字种类，且 analyzer 已统一收集 all_symbols）。
> 检查逻辑语言通用（进引擎原语），pattern 是语言知识（进 TOML），符合铁律。
> **不适合当前阶段，计入待办。**

> **Sigasi 命名检查机制（行为观察，2026-08-16）**：
> - 规则 NAMING_CONVENTIONS（前端类别 NAMING_CONVENTION）+ 30 个名字类别参数，
>   每类一个**正则 pattern**：MODULE_NAME/NET_NAME/VAR_NAME/PORT_NAME/INPUT_NAME/
>   OUTPUT_NAME/INOUT_NAME/PARAMETER_NAME/PARAMETER_TYPE_NAME/MACRO_NAME/PACKAGE_NAME/
>   TYPEDEF_NAME/ENUM_TYPEDEF_NAME/ENUM_MEMBER_NAME/UD_NETTYPE_NAME/STRUCT_NAME/
>   UNION_NAME/CLASS_NAME/INTERFACE_NAME/INTERFACE_CLASS_NAME/INSTANTIATION/
>   SUBPROGRAM_NAME/FUNCTION_NAME/TASK_NAME/PROGRAM_NAME/CONSTRAINT_NAME/FSM_NAME/
>   FSM_LABEL_NAME/GENERATE_BLOCK_NAME/COMMENT_HEADER
> - 每 pattern 带 positive/negative 方向（匹配即合法 vs 不匹配即合法）；
>   UI 预设 uppercase/lowercase/IGNORE 三选（`nt` 枚举：TRUE/FALSE/IGNORE），
>   高级用 REGEX 自定义（参数类型枚举含 REGEX）
> - 错误文案："Naming convention violation: %s should %s pattern '%s'"
>   （名字 should match/not match pattern）；deprecated 语法单独报
> - 附带独立规则：连续下划线（ConsecutiveUnderscores）/ 末尾下划线
>   （UnderscoreAtEnd）——项目 schema 单独配置项，非 naming pattern
> - 头注释检查（HEADER_COMMENT_CHECK）也复用 namingConvention 参数
> - severity 按规则 id 配置：`.sigasi/settings.json` 里 `verilog.rules.<id>.severity`
>   （tutorial 示例：14/17/18 = IGNORE），另有 RTL 级 severity 分离
> - 对照 tpc：Symbol.kind 即名字类别；30 类清单 → analyzer 符号表 kind 分发，
>   比"规则级命名配置"更系统（全局一张 pattern 表按 kind 查）

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

### P2.0 机制可理解性

- [x] 配置生命周期评估 + 文档化（docs/config_lifecycle.md——三阶段时序 + 坑 + 评估结论保持注册制）
- [x] 表达式系统隐式约定文档化（docs/expression_conventions.md——优先级/atom/三元/一元）
- [x] 组件协议文档（docs/component_protocol.md——组件/槽位/原语/inject）
- [x] c4 定位为最小语言包模板（grammar/c4/README.md 模板路径 + 4 文档索引）

### P2.2 发布收尾

- [x] 覆盖率门禁（.coveragerc omit 入口/回退，fail_under=84，实测 84.57%）
- [x] 恢复 CI（.github/workflows/ci.yml：Windows + Python 3.11/3.12/3.13）
- [x] 安装可验证（pip install -e ".[test]" + tpc CLI 实测）
- [x] 补文档（CONTRIBUTING.md / CHANGELOG.md / docs/api.md）
- [ ] **CLI 指令替换 python main 模式（2026-08-16 方向）**：
      用 `tpc format` / `tpc lint` / `tpc new component` 等指令替代 `python main.py xxx`；
      为此 README 已删除 Quick start + API 两节（留位置），CLI 落地后补回。
      指令列表对齐 main.py 现有子命令（format/lint/init/pipeline/new），
      pyproject 配置 console_scripts 入口；CLI 用法写回 README 对应节。
- [ ] 覆盖率远期目标 ≥90%（当前 84.57%，需补 transform/renderer 等薄弱区）

## P4 — LLVM IR 前端桥（v0.2 商业向候选，非收尾）

> 来源：2026-08-14 方向。LLVM/MLIR 生态商业价值高（芯片/硬件厂商对
> "专有语言 → LLVM"定制付费意愿强），tpc 的配置驱动 + 模型代写正好能压
> 低这段最贵的前端成本。c4 已实证"语言 → 自定义 IR"（_asm.py 降 c4 VM
> 汇编），换靶为 LLVM IR 是同一件事。
>
> 定位：**不做"多级 IR 框架"（与 MLIR 撞车），做"语言 → 现成 IR 的前端桥"**——
> tpc 作为"任意 DSL → LLVM IR"的生成端，模型写变换插件组织降级管线。
> 用途也是"证明能力"的技术前提（对外 demo 靶子 = LLVM IR，厂商熟悉可接）。

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

## P3 — 增量解析（v0.2 核心，非收尾）

> 来源：2026-08-14 方向。思路 = 复用已实证的"分段解析 + 并树"
> （tests/e2e/debug_segment_parse.py，PicoRV32 调试时验证过），把失效判定
> 从 module 级细化到语法单元级（近似 tree-sitter 的失效激活）。
> 目标：编辑 → token 级 diff → 延展到语法边界 → 仅重解析受影响单元 → 并树复用。

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

### P3.3 已知坑：宏展开下的双向映射（2026-08-14 预判）

- [ ] **token span 对应的是"展开后"token，不是源文本**：源文本 → 预处理器（展开）→
      lexer → parser，AST 的 token 索引是展开后 token 流的索引
- [ ] 编辑 diff 在**源文本**上做，但 span 在**展开后 token**上——两边对不上，需映射层
- [ ] 预处理器已有反向资产：`preprocessor/_bridge.py`（锚 + 残片回插，marker 定位原文），
      renderer 靠它还原源码位置——增量需要**复用这套桥**，把"展开后 token → 源文本行"打通
- [ ] 条件编译（`ifdef/ifndef`）下编辑，会改变展开结果 → 整段缓存失效，需处理
- [ ] 宏定义本身的编辑（`define` 行改）→ 所有用到该宏的 token 全部失效，不是局部问题



## 设计说明（已落地，供参考）

- 发现器多层递归最多到句子级；句子结束符由 production 结尾字面 token 推导（`_derived_end_case`），
  仅非容器规则推导，不往 end_case 加值（end_case 配置零改动）
- A/B 类消歧统一为动态两级（2026-08-02）：Level 1 变长前瞻（前缀路径，**公共前缀匹配**——
  seen 与路径双向前缀一致，允许 seen 比路径短）+ Level 2 试解析（复用 RuleMatcher，limit 含终止符）
- 块规则（task/function）在 lookahead 构建时**还原 block_start** 到 production 首，与普通 A 类
  规则视图统一（prods[0] 都是触发 token，paths 统一从 prods[1:] 开始）
- 前瞻深度上界 = 语句边界块；候选清空 → 暂返回 None（未识别语法报告待增强）

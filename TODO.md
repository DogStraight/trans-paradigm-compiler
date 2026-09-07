# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。
> 0.1.1 目标 1「全量 Verilog 2005 语法包验证 + 缺口闭环」状态（2026-08-28）：
> 语法层已闭环（批次 1-6 + A 类 3 缺口 + 交错形态 + 真实语料 9 文件门禁）；
> 端口默认值宏已闭环（批次 10 / M1，ice40 默认配置门禁，见下）；剩余打磨项：
> darkriscv 条件编译嵌套位置精度（已修至 ifdef 全还原，见 P1.5）。
> 当前验证基线（2026-08-28）：1273 pytest 全绿（顺序无关，core/global_state
> 测试隔离机制）+ e2e 94 组 + real 语料 9 文件（FAIL 0，保真度守卫）+
> pyright 0 errors（1.1.413）+ lint recall 31/31 零误报 + 覆盖率（fail_under
> 80）+ vs Verible 差分 136 例 + vs sv-parser 差分 98 例（false-reject 0 /
> bad-interop 0 / lenient-diff 3——typed_ports 增强语法）。

## 0.1.1 目标 2 — 检查链收尾（2026-09-05 立项，三目标）

> 对标结论：references.md「P1.10 结论」（重合核心集 10 项 + 特化赛道 + 映射
> 评估）+「诊断链多维对标结论」（0.1.1 第二目标定稿）。
> 现状（2026-09-05 盘点）：30 诊断码 / 8 检查族已实现（name NC001-16 / inst
> W101-106+WC001 / width W201-2 / latch LC001 / case CC001 / unused UN001 /
> always AW001-2）；eval_check_accuracy 强检 focus 10 码 @ 34 case recall
> 100% + FP 0。重合核心集实现 ~9/10（宏卫生族缺）；强检面只盖 30 码中 10 个；
> 独到项批判吸收仅 svlint prefix 族已入（NC014-16）；自场景自定义规则范例 0。

- [ ] **T1 重合核心集补全 + 强检扩面**：
      - 宏/指令卫生族（对标 Verilator REDEFMACRO / slang redef-macro /
        svlint default_nettype——跨文件宏表）：是否进 0.1.1 待作者定
      - eval_check_accuracy focus 扩到核心全集：inst 族 W101/W102/W103/WC001
        + always AW001/AW002 + 相关 NC（NC001-11 / 14-16，与
        test_name_convention.py 分工核对）——每新增码补 pos/neg case，
        验收 recall=100% + FP=0
- [ ] **T2 独到项批判式吸收**（references「特化赛道」已定价，取舍清单待作者拍板）：
      - 零成本语法层候选：Verible 排版族（line-length/no-tabs）、svlint
        空格族（style_*）/ ANSI 头 / 参数 2-state——先定"落 linter 还是
        check 链"架构再动
      - 中成本（Verilator UNOPTFLAT/CMPCONST）与远期（Spyglass CDC）——
        明确 0.1.2+（方向注 ROADMAP，不立项）
## 文档工程（2026-09-04 立项，使用复盘 6 类文档框架）

> 已完成（提交 5f4e812/301cdda/后续）：MODEL_INDEX 按子系统重组（两表合并 +
> parser/analyzer 主干）、部件地图 docs/component_map.md（子包 + 每文件一句话）、
> decisions/README 补「讨论 → 决策」状态流。剩余项 = 文档分层落地（见下）：
> docs/README 声明 decisions→architecture→references 三层，但 architecture/ 未建、
> 19 篇架构/机制文档散在根目录（"暂留原处，逐步归位"悬空）。方向：建
> architecture/ 归位（doc_sync 批量同步 Doc:/Impl:）或明确"根目录即架构层"消除
> 漂移——两者取一，先定方向再动。

- [ ] **文档分层落地**：明确根目录 19 篇架构/机制文档 = architecture 层（建
      architecture/ 目录归位或明确"根目录即架构层"，消除 README 声明 vs 现状
      漂移）；doc_sync 批量同步 Doc:/Impl: 引用 + check_doc_refs 验证

## 对标测试（2026-08-29 立项，Verilator oracle，方案见 references.md「试水第四弹」）

> 变异注入器（试水第三弹）验证"错误能检出"后，用 Verilator 二进制当 oracle
> 对拍输出一致性。**已全闭环（2026-08-29）**：MSYS2+Verilator 5.050 装好、
> eval_benchmark.py 落地（W 码映射 + lint_off 抑制识别 + 条件编译行号偏移
> 处理 + parse 失败标定）、真实语料 7 工程 + 评测集 34 case 对拍完成。
> 结果：共识 44 条（UN001/LC001 族）+ 修复 4 个真 bug（106 条 FP → 0：
> W201 跨模块同名污染 / W103 模块体参数缺口 / W104 函数参数误收 /
> CC001 全覆盖误报——前 2 条推翻旧落档）；剩余差异全部判明类别（AW 族
> 默认关 / UN001 粒度 / generate 互斥 W105 层 3 边界 / 语料不完整）。
> 细节见 references.md「试水第四弹」+ 缺口表更新。

- [x] ~~MSYS2 + Verilator 安装，验证 `verilator --lint-only` 可跑~~（完成）
- [x] ~~eval_benchmark.py：同一输入双跑 + W 码↔tpc 规则码映射 + 差异归一化~~（完成）
- [x] ~~真实语料 + 评测集对拍，逐差异处置三选~~（完成：4 bug 修复 + 边界落档）
- [x] ~~结论落档 references.md + 全量回归绿~~（完成：1464 passed + 8 skipped，hardcode gate PASS）

## 三工具对照测试（2026-08-29 立项，Verilator + Verible + svlint，方案见 references.md「试水第四弹扩展」）

> Verilator 单 oracle 对拍闭环后，对照扩展到 Verible lint（已捆绑，零安装）
> 与 svlint（用户提供预编译 v0.9.5）。**已全闭环（2026-08-29）**：
> harness _ORACLES 注册表（run + 码映射 + 范围外码集）、--oracle=name 可
> 重复、_tpc_diags_all 全文件覆盖（修复 entry 递归漏扫独立文件）。真实
> 语料三工具共识 66（Verilator 44 + svlint 22）；**关键结论**：svlint/
> Verible 是单文件语法风格 lint，跨文件语义（UN001/W101/W104/W105/LC001
> 锁存语义）无对应规则 = 能力域差异非漏报，印证"跨文件类只有 tpc 能做"。
> **四工具扩展（2026-08-29）**：+slang v11.0 oracle（评测集共识 5，
> 位宽/越界族验证）；变异注入器 13→24 条（+W106/AW002，W105 过程赋值
> 驱动修复暴露）；并发测试默认开启（addopts -n auto，全量 87s）。
> 细节见 references.md「试水第四弹扩展执行结果」。

- [x] ~~svlint 安装（用户提供预编译 v0.9.5；cargo install 因 Rust 1.98
      与旧依赖 build script 不兼容失败）~~（完成）
- [x] ~~Verible lint 规则清单 + 输出格式探针~~（完成：60 条规则，
      `file:line:col-col: msg [rule]`）
- [x] ~~eval_benchmark.py 扩展多 oracle~~（完成：_ORACLES 注册表 +
      --oracle=name + _tpc_diags_all）
- [x] ~~三工具真实语料 + 评测集对拍，差异处置三选~~（完成：共识 66、
      能力域差异落档）
- [x] ~~结论落档 references.md + 全量回归绿~~（完成）
- [x] ~~slang oracle（用户下载 v11.0，--lint-only + -W + --diag-json）~~（完成）
- [x] ~~变异注入器扩展（13→24 条，+W106/AW002/W105 过程赋值）~~（完成）
- [x] ~~并发测试默认开启（addopts -n auto；coverage 用 -n 0）~~（完成）

## P1 — Verilog 实例完善

### P1.8 Verilog 语法补全 + 仿真语法插件化（发布前置）

> 可综合子集进主包、仿真语法进插件（plugins/sim）；完成后主包纯净可综合 = 发布基线。
> 语法对照：IEEE 1364-2005 Annex A（67 节）。已入 plugins/sim 的语法见
> policy/release-checklist.md（A.2.1.3 event / A.6.3 fork-join / A.6.4 force-release
> / A.6.5 时序控制）。
> 已入 plugins/nettypes（2026-08-27，批次 1）：net 类型全谱 12 种 + drive/charge
> strength + vectored/scalared + delay3（值/三值/mintypmax）+ real/time/realtime
> 声明（A.2.1.3/A.2.2）。wire 扩展形态（strength/delay）走 NetDecl 双候选。
> 已入（2026-08-27，批次 2）：procedural assign/deassign（sim 插件，A.6.4，
> 过程 assign 与模块级 AssignStmt 双候选同构消歧）+ config 声明（plugins/
> configs，A.1.5 全形态）+ macromodule（主包 MacroModuleDecl 独立规则）。
> 已入（2026-08-27，批次 3）：门级/开关原语 26 个（plugins/gates，A.3 全组，
> strength/delay 与 nettypes 同名同步副本 + PullStrength 单值变体）+ UDP
> 声明（plugins/udp，A.5：comb/seq 表 + initial + edge 括号对，表符号按
> sv-parser 参照 token 结构化；UDP 实例化复用 ModuleInst）+ 模块实例位置
> 端口连接（主包 OrderedPortList，A.4.1.1）。
> 引擎修复：块规则 block_start/end 推导支持尾组回退 + block_prods 剥到
> block_end 位置；matcher optional 失败恢复对 first 重叠场景静默交还 +
> first 集 nullable 传播；start_token_map 块首去重；BoundaryChecker opener
> 前驱排除（:config 类终结形态）。
> 已入（2026-08-27，批次 4）：specify 块（plugins/specify，A.7：specparam
> 含 mintypmax/范围前缀 + 路径声明简单/全路径/边沿敏感/状态依赖宽进 +
> 系统时序检查 $setup/$hold/$width 等事件参数/edge 控制/&&& 条件）+
> defparam（同插件 01_defparam.toml，A.2.4 层级参数覆盖）。路径描述
> no_soft 保单行属语法包渲染声明。
> 已入（2026-08-27，批次 5）：function 返回类型（A.2.6 function_range_or_type：
> integer/real/realtime/time + signed/range 全形态，ANSI/旧式）+ task 端口
> 类型（A.2.7 task_port_type：任务/函数端口专用 TaskPortTypeTail 分支，
> 模块端口共用规则不动）+ generate 单语句体（A.4.2：GenBlockOrNull =
> @ModuleItem|@BeginEnd|;，LoopGen 体放宽，GenerateIfDecl/GenerateCaseDecl
> 挂 InstStmt 承载 if/case 单语句体与 default 空体）。
> 引擎修复（批次 5 连带）：parser 实现 exclude 负向前瞻（消歧字段此前仅
> linter 消费，parser 靠 FOLLOW 不含目标 token 巧合生效；GenerateCaseDecl
> 引入后运算符家族前缀经 inline 传播进 Declarator FOLLOW，typed_ports
> 点语法解析回归——exclude 检查现先于 FOLLOW，与 linter 同语义）。
> 覆盖核对（2026-08-27）：A.1~A.9 主要语法已齐（net/strength/delay/类型
> 声明、procedural assign、config、macromodule、gates 26、UDP、specify、
> defparam、function/task 类型、generate 单语句体）。核对发现缺口已闭环
> 于批次 6（见下）。
> 已入（2026-08-27，批次 6，sv-parser 实现对照见 references.md）：转义
> 标识符（A.9.3，lexer 支持 `\` 起始 id，修崩溃）+ library 声明/include
> 语句（A.1.1，configs 插件 01_library.toml）+ continuous assign
> strength/delay（A.6.1，AssignStmt 复用 nettypes DriveStrength/
> Delay3）+ always 无事件控制（A.6.2，AlwaysStmt 放宽 event_control 可选）
> + 单索引 range `[3]`（A.2.5，Range 补可选 lsb 分支）+ genvar 列表
> （A.4.2，GenvarDecl 补逗号列表）+ 实例/门级 attribute 前缀（A.4.1/
> A.3.1，attributes 插件 AttrInstStmt 注入 InstStmt）。
> 审查修复（2026-08-27）：转义标识符改配置驱动（`[id.escaped]` 声明，
> c4 不声明不启用——消除 lexer 硬编码语言知识）；library `-incdir` 拆
> IncdirClause 子规则（4 层绑定降 2 层）。
> 真实语料批次（2026-08-27，real corpus 驱动，见 references.md「真实语料
> 实测」）：`===`/`!==`（A.8.4，token+CmpOp+operator 表三处缺失）+
> 多目标连续赋值（A.6.1 list_of_net_assignments，独立 AssignExtra 子规则）
> + 模块头属性（A.1.1 attribute_instance 前缀 module_declaration，顶层
> AttrModuleDecl）+ 语句体宏行尾补分号（_expand.py：`tpc_marker_N;` 按
> A.6.9 裸任务调用可解析）。真实语料扩至 9 文件（+UART×3/simcells/
> ice40_cells_sim，归属 CREDITS.md），回归基线 test_real_corpus.py
> （parse/format/lint/幂等/保真/差分门禁，module 数下限防静默截断）。
> 缺口批次（2026-08-28，A 类 3 缺口，test_2005_batch8.py）：层次化 id
> 表达式位（A.9.3 hierarchical_identifier，HierExpr 原子：a.b / a.b.c /
> a.b[3:0]，typed_ports 端口点语法共存验证）+ 无括号系统任务语句
> （A.6.2/A.9 sys_task_enable，SysTaskStmt 括号整体可选：$finish; / $stop;）
> + 参数覆盖 mintypmax（A.4.3/A.8.2，NamedParamOverride 值位改
> MintypmaxExpr：#(.P(1:2:3))）。
> 核对澄清（2026-08-28 实测）：三元 `?:`、过程体 event/localparam 声明、
> 命名块头声明**已支持**（此前 TODO 摘要误列）。
> 层次化引用交错形态（2026-08-28，batch9）：`a[0].b` / `a.b[0].c` /
> mem[i].field（成员与下标任意交错）以**形式化宽进**支持——语法接受 +
> 保真渲染，继承链语义解析（a[0] 是哪个实例、b 是不是其成员）明确不承担
> （综合/仿真工具职责）。实现：HierExpr production 改交错 + HierMember/
> HierSuffix 段包装 + SelectExpr exclude dot + 原子最长匹配（parser/linter
> 双轨）+ lookahead Level 1 回退修复（连带修复既有缺陷 `a.b <= x` NBA
> 目标位误判未识别）。
> 端口默认值宏（2026-08-28，batch10 / M1，ice40 默认配置）：`input NAME `M`
> （body=`= 1'b1`，端口默认值位）此前 token 锚顶掉默认值 → 34 错只能靠
> NO_ICE40 空宏规避；现改 inline+body 区间还原（赋值后缀宏 body 以 `=`
> 开头 → marker 注释 + body 原文保留，Declarator @Init? 兜住端口默认值，
> 还原按 [marker..body] 区间替换回宏调用残片；inline 分支补渲染行尾锚定
> 形态的 marker 前同行定位）。ice40 默认配置全绿 + sv-parser 互操作接受，
> 语料门禁预定义清空（test_2005_batch10.py）。
> 剩余核对缺口 + 真实语料前沿（yosys `$cell` 内部名）见 references.md。

### P1.5 已知缺陷收尾

- [ ] **宏展开路径条件编译还原不完整（2026-08-28 修复中，interop 门禁暴露）**：
      darkriscv 输出 `ifdef` 曾 89 个 vs 源 101 个（缺 12：__INTERRUPT__×3 /
      __COPROCESSOR__×2 / __EBREAK__×2 / __DBNZ__×2 / __CSR__×1 /
      MODEL_TECH×1 / SIMULATION×1——全是未定义条件）。已修（inline_comment.py
      4 项：tpc 占位不静默丢失 + 独立行插入 + 相邻标记顺序 + 插入后动态更新
      插值锚点）：**ifdef 101/101 全还原、无占位残留、lint 零诊断**。残余：
      表达式链内相邻条件块（IFPC 三目链的 EBREAK/INTERRUPT/DBNZ）还原位置
      依赖插值定位（渲染行距非线性 + 锚点稀疏），嵌套位置仍有偏差 →
      sv-parser 仍拒（interop 豁免保留）。根治需 active 内容 marker 化
      （_flush_block 改造）或 token span 映射（P3.1 前置），另案。

## P1.10 主流 lint 机制调研 → 规则清单（2026-08-29 立项）

> 方向（用户定调 2026-08-29）：主体目标 = 调研市场主流 lint 机制充实规则库，
> 再补 1-2 条差异化自定义规则（核心样例 + 差异化资产）。方法：**先划各工具
> 重合范围 → 核心集合（高频刚需）**，**再划各工具特化赛道 → 选择性吸取**
> （差异化候选）。差异化方向已定 = **跨文件类**（实例化端口与模块定义不匹配
> 等——只有 tpc 跨文件 handler 能做，svlint/Verible 单文件做不了）。
> 调研已完成（2026-08-29，三路并行）：svlint 159 条/Veryl 114 项/flexlint 框架
> + Verilator 136 码/Verible ~60 条 + slang/Spyglass/HDL Checker——结论落
> docs/references.md「主流 lint 机制调研」+「重合核心集合 + 特化赛道 + 映射
> 评估」：核心集合 10 类（命名/未使用/位宽/锁存/case/always/端口/实例化/多
> 驱动/宏卫生），跨文件差异化候选 = 实例化端口连接 / 未使用声明 / 端口完整性。
> 规则实现进度（2026-08-29）：elaboration 底座完成（ADR-0008，层2 连接展开 +
> 层3 信号图，提交 3acae77）；已实现 UN001 未使用声明（a22f081）、W104 未连接
> 端口（57d6e83）、W105 多驱动（394ec51）、CC001 case 完整性（1f94fbc）、
> W106 inout 须 tri（5067e8b）、LC001 锁存风险（d5148d3）、NC012/NC013 命名
> 补全（随 a22f081）、W201 赋值/端口连接截断 + W202 位选越界（width_check
> 插件，1c04652..c6c8587）——**核心集合 10 类全落地**（8 类实现 + 2 类评估
> 不做：always 写法/unsized 精化，理由见 references.md「位宽一致性落档」），
> 三层捕获能力（语法声明式 / 语义符号表 / 跨文件 handler）各被真实规则
> 验证。
> 试水评测（2026-08-29，第一弹）：构建检出准确性评测集——26 case（15 正样例
> + 11 负样例，含复合小工程 project_bus_ctrl）+ eval_check_accuracy.py +
> test_check_accuracy.py 门禁（recall=100% + FP=0 断言）。首测 80% recall /
> 3 FP 暴露并修复 3 缺陷：W105 信号图补 assign 驱动收集（协议驱动）、
> TypeSpecNoReg net 位补 tri（`inout tri` 语法缺口，连带暴露 test_inout_tri_clean
> 假阳性盲区）、命名规则 `_` 前缀豁免。修复后 18 期望码全命中 + 0 FP。
> 评测已扩至 34 case（+W201/W202），23 期望码 100% recall / 0 FP。
> 详情落 docs/references.md「试水检出准确度评测」+「位宽一致性落档」。
> P1.10 已全闭环；后续方向：位宽相关进阶（ordered 端口连接覆盖、跨模块
> 成员宽度）或试水第二弹（真实工程误报率评测）。

- [x] ~~工具调研：svlint / Veryl / Verilator / Verible / slang / Spyglass /
      HDL Checker / flexlint 检查项清单~~（已完成，落档 references.md）
- [x] ~~重合核心集合 + 特化赛道 + 映射评估~~（已完成，10 类核心集合）
- [x] ~~elaboration 底座（ADR-0008 三层）~~（已完成，3acae77）
- [x] ~~语法层声明式规则：NC012/NC013 命名补全~~（已完成，随 a22f081）
- [x] ~~语义层未使用类：UN001（符号表引用计数）~~（已完成，a22f081）
- [x] ~~跨文件端口完整性：W104 未连接端口~~（已完成，57d6e83）
- [x] ~~多驱动：W105~~（已完成，394ec51）
- [x] ~~分支完整性：CC001 case 无 default~~（已完成，1f94fbc）
- [x] ~~端口类型：W106 inout 须 tri~~（已完成，5067e8b）
- [x] ~~锁存风险：LC001 组合 always if 无 else~~（已完成，d5148d3）
- [x] ~~位宽一致性：W201 赋值/端口连接截断 + W202 位选越界（width_check
      插件 A/B/C1 闭环；C2/C3 评估不做——理由 references.md「位宽一致性
      落档」）~~（已完成，1c04652..c6c8587）
- [ ] ~~always 写法（裸 always）~~（评估：边界模糊/仿真代码大量合法使用，误报高，不做）


## references.md 执行/验证记录类清理（2026-09-02 立项，负重治理收尾）

> references.md 设计类已全部迁出（ADR-0009/0010/0011/0012 + 命名并入
> 0004，2878→2563 行）。剩余执行/验证记录类（试水弹、位宽落档、引擎增益、
> 性能实测等 ~700 行，嵌在各调研大节下）按删除判据 C1/B5 逐节处置：
> 结果已进测试/CHANGELOG 的压缩为小结或删除，保留"为什么/推翻了什么"
> 结论层。每节核对 ROADMAP/TODO 回指后处置，独立提交。

- [ ] 试水弹系列（第一/二/三/四弹 + 扩展执行结果）压缩为小结或删除
- [ ] 位宽一致性落档（W201/W202 A/B/C1）保留结论层、压缩过程层
- [ ] 引擎增益/性能实测（elaboration 热点、实例树实测、packrat/Nuitka/PyPy）压缩为结论
- [ ] sv-parser 调研节下的执行子节（真实语料实测/A 类/S 级修复）核对后处置
- [ ] 治理收尾验证：references.md 定位描述同步（docs/README）+ 全量门禁绿

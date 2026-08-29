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

## P1 — Verilog 实例完善

### P1.8 Verilog 语法补全 + 仿真语法插件化（发布前置）

> 可综合子集进主包、仿真语法进插件（plugins/sim）；完成后主包纯净可综合 = 发布基线。
> 语法对照：docs/ieee1364_2005_annex_a.md（67 节）。已入 plugins/sim 的语法见
> docs/release_checklist.md（A.2.1.3 event / A.6.3 fork-join / A.6.4 force-release
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
- [ ] **invert 嵌套引用遗留（typed_ports，L2/L3）**：L1 已防御
      （test_nested_invert_no_skip_leak）；L2 未修——invert 对含嵌套引用的 role，
      嵌套展开端口（inner_* 方向反转）不参与反转（invert 回调 resolve 期拿的是
      目标 role 原始端口数据，需用完整展开端口解析：普通端口拍平 + _ref_callbacks
      合并）；L3 未修——invert 引用的 role 定义在后时 _ref_callbacks 尚未构建
      （primitive 单遍 DFS，需两遍遍历/pending 重试）。README Known limitations
      已记录。

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
> 补全（随 a22f081）——7 类核心集合 + 三层捕获能力（语法声明式 / 语义符号
> 表 / 跨文件 handler）各被真实规则验证。评估：always 写法类（裸 always）
> 边界模糊/误报高（仿真代码大量合法使用），**不做**；位宽一致性需完整
> 类型/宽度传播系统（Verilator WIDTH 家族级，独立大工程）。
> 试水评测（2026-08-29，第一弹）：构建检出准确性评测集——26 case（15 正样例
> + 11 负样例，含复合小工程 project_bus_ctrl）+ eval_check_accuracy.py +
> test_check_accuracy.py 门禁（recall=100% + FP=0 断言）。首测 80% recall /
> 3 FP 暴露并修复 3 缺陷：W105 信号图补 assign 驱动收集（协议驱动）、
> TypeSpecNoReg net 位补 tri（`inout tri` 语法缺口，连带暴露 test_inout_tri_clean
> 假阳性盲区）、命名规则 `_` 前缀豁免。修复后 18 期望码全命中 + 0 FP。
> 详情落 docs/references.md「试水检出准确度评测」。
> 下一步：位宽一致性分期启动（阶段 A 常量宽度域，2026-08-29 立项；
> 设计：语义插件位置实现 求值器+推断器+规则——宽度语义是语言知识，
> 进 grammar/verilog/plugins/checks/width_check/，引擎零改动面）。

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
- [ ] 位宽一致性（对标 WIDTH/width-trunc 家族，2026-08-29 分期立项；
      实现位置 = 语义插件 grammar/verilog/plugins/checks/width_check/：
      求值器+推断器+规则都在插件层，语言知识不进引擎）：
  - [ ] **A3 表达式宽度推断**：原子（查表/字面量）→ 拼接（和）/复制（×n）
        /位选（1 或范围）/一元（同宽）/二元（算术 max、比较 1、移位
        LHS、位运算 max）/三目（max）
  - [ ] **A3 表达式宽度推断**：原子（查表/字面量）→ 拼接（和）/复制（×n）
        /位选（1 或范围）/一元（同宽）/二元（算术 max、比较 1、移位
        LHS、位运算 max）/三目（max）
  - [ ] **A4 WIDTH 赋值对比**：assign/阻塞/非阻塞/端口连接 LHS vs RHS
        宽度——RHS>LHS 截断报 W201（warning）；扩展不报；先 sized 域
  - [ ] **A5 评测扩充**：width_check cases（pos/neg）+ check_accuracy 位宽
        样例 + pytest 门禁
  - [ ] **B1 模块参数表**：ParamDecl 默认值 + 实例化覆盖（#(.P(v))/#(v)）
        解析 → 参数值表
  - [ ] **B2 参数化宽度求值**：宽度文本含参数名 → 代入折叠（WIDTH-1:0）
  - [ ] **B3 跨模块参数传播**（例化链）+ 评测
  - [ ] **C1 SELRANGE 位选越界**（W202）
  - [ ] **C2 自赋值宽度变化**（W203，a = a + 1 类）
  - [ ] **C3 $signed/$unsigned 符号语义 + unsized 常数精化**
- [ ] ~~always 写法（裸 always）~~（评估：边界模糊/仿真代码大量合法使用，误报高，不做）

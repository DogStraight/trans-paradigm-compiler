# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。
> 当前验证基线（2026-08-27）：1207 pytest 全绿 + e2e 94 组 + real 语料 9 文件
> （FAIL 0，保真度守卫）+ pyright 0 errors（1.1.413）+ lint recall 31/31 零误报 +
> 覆盖率（fail_under 80）+ vs Verible 差分 124 例 + vs sv-parser 差分 98 例
> （false-reject 0 / bad-interop 0 / lenient-diff 3——typed_ports 增强语法）。

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
> 剩余核对缺口见 references.md 审计清单（过程体 event/localparam 声明、
> #(min:typ:max)、命名块头声明、层次化 id、三元 ?: 等）+ 真实语料前沿
> （端口默认值宏 body、yosys `$cell` 内部名，批次 7 候选）。

### P1.5 已知缺陷收尾

- [ ] **interop 门禁覆盖宏文件（2026-08-28 调查遗留）**：test_svparser_accept_
      domain_and_interop 对含宏语料整体跳过，互操作半边（tpc 输出→sv-parser）
      对宏文件可行却未覆盖——skip 掩盖了 4 个缺陷（均已修，见下）。拆门禁：
      accept_domain 仅无宏文件（现状），interop 覆盖全语料（含宏文件，tv80 源
      sv-parser 拒收豁免）。当前 9 文件 interop 实测：除 tv80（源拒豁免）与
      darkriscv（sv-parser 预处理器限制）外全绿。
- [ ] **无括号系统任务语句语法缺口（2026-08-28 实测发现）**：`$finish;`
      等无括号形态 parse 失败（SysTaskStmt production 要求括号；SysFuncBare
      是表达式版）。A.6.2/A.9 系统任务语句允许无括号形态。
- [x] **formatter inst_port 破坏 concat 端口连接（2026-08-28 已修，AST 辅助）**：
      `.RADDR({pd(RADDR_10), pd(RADDR_9), ...})` 被 `_port_parse` 单行括号
      平衡误判（深度未归零时把行尾当表达式结束，重写时伪补 `)`）。修：
      未闭合哨兵（`_UNCLOSED`）+ parser 注入 AST 辅助（实例块包装解析拿
      端口 span，跨行端口参与 name 列对齐、expr 保留原文）；无 parser 时
      未闭合行保守跳过。ice40 interop 绿。
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

### P1.9 tpc-check 诊断体系（semantic_check 插槽架构，ADR-0004/0005）

> 2026-08-27 更新：原"规则表 + naming_check 接入"路径已变轨——诊断体系落地
> 为 semantic_check 插槽架构（docs/semantic_checks.md；ADR-0004 为什么、
> 0005 跨文件）。已落地：机制层（post-pass 钩子 + 统一报告管道 + related
> 链）、跨文件联动（inst_check：W101/W102/W103/WC001）、名称调用检查
> （check_name_call：W002）、--json/suppress。剩余两条（对应
> semantic_checks.md 状态行的 P3 声明式 schema / P4 用户配置层）：

- [ ] **TOML 规则表（L1 声明层 + P4 用户配置层）**：[[checks]] schema
      （id/category/severity/scope/message/handler）目前只在文档定义，实际
      规则是 postpasses 脚本（inst_check）——"规则 = 数据"待落地，tpc.toml
      [checks] 用户覆盖一并
- [ ] **命名约定检查（原 P1.7）**：Sigasi 式 pattern 表按 kind 分发（30 类
      kind 映射：module→MODULE_NAME、wire/reg→NET_NAME 等）+ 用户可配
      pattern/match——未实现（注意 _name_check.py 是名称调用检查 W002，
      非命名约定）

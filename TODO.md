# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。
> 当前验证基线（2026-08-27）：1098 pytest 全绿 + run_all 93（FAIL 0，real 组
> 保真度守卫）+ pyright strict 0 errors（1.1.413）+ lint recall 31/31 零误报 +
> 覆盖率 83.39%（fail_under 80）+ vs Verible 差分 124 例。

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

- [ ] **门级/开关原语**（A.3）：and/or/nand/nor/xor/xnor/buf/not + bufif0/bufif1/
      notif0/notif1 + pmos/nmos/tran 系列 —— 综合类，进主包
- [ ] **UDP**（A.5）：primitive/table/endprimitive —— 综合类（老设计），进主包
- [ ] **specify 块**（A.7）：specparam、$setup/$hold/$width 等时序检查 —— 时序分析，
      仿真/综合边界，评估放哪（可能单独 plugins/specify 或并入 sim）
- [ ] defparam（A.2.4）—— 与 specify/门级同批

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

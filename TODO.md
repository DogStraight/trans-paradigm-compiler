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

### P1.9 tpc-check 诊断模型升级（pylance 化，2026-08-25 研判入册）

> 来源：docs/references.md「Verilog 静态检查工具群」深调研（verible-lint / Verilator
> `--lint-only` / slang / svlint / hdl_checker）+ svlint 深调研（规则四件套
> check/name/hint/reason + suppress 注释对 + deny_unknown_fields fail-fast）。
> 目标场景：模型生成 v 文本 → tpc-check 当 pylance 用（即时诊断、机器可读、可豁免）。
> 定位：**诊断体系一体**——命名约定检查（原 P1.7）是体系的第一条显式规则，
> 规则表是它的承载框架；第一步低成本项已完成（--json/suppress/规则 ID 文档）。
> LSP 服务化路线观察已落 references.md（📌 路线观察），不在此立项。

- [ ] **检查规则表 + severity 配置（框架，第一步规则落地的承载）**：规则 ID →
      描述 → 默认 severity → 用户覆盖，对齐 svlint `.svlint.toml` / verible
      rule-sets；tpc 配置驱动哲学在检查侧的落地
- [ ] **naming_check 作为第一条规则接入规则表**（原 P1.7，验证"规则即数据"路径）：
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

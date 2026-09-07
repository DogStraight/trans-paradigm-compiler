# Changelog

All notable changes are listed in reverse chronological order.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **typed_ports 增强语法语义检查（T3，ADR-0013 三族）**：新增组件内 analyzer
  postpass `_check.py`（挂 typed_ports `[analyzer] postpasses`）——A 表述完整
  TP001 type 悬空 / TP002 role+invert 悬空 / TP003 显式端口 typo / TP004 role
  端口重名 / TP006 invert 自反；B 连接正确 TP010 impl `=>` 未命中端口实例
  （拦 `=> top` 历史错误写法）/ TP011 类型不匹配（spi 连 sci）/ TP012 role
  不同向（ref_spi_inf 同向基准）；C 单驱动 TP020 同一接口实例被多 impl 绑定
  （多驱动预检，对齐展开后 W105）。TP 恒开 error 级，analyze 报错即阻断展开
  （复用 schedule `_ScheduleStop`，坏输入不产出错误模块）。顺带修：TypedTypeSpec
  即时 identifier_ref 在 type 后置（合法前向引用）时误报 W001 → 移除，交 TP001
  postpass 全量核对；既有 `=> top` 错误样例修正（test_typed_ports/
  test_enhanced_render 删误导 impl 行保 TypedPortDecl 展开断言、
  test_comment_migrate/test_schedule 改同向 `=> 实例`）。验证：18 单测 +
  eval_check_accuracy 8 TP pos + 1 neg 样本（recall 100% + FP 0）+ 全量 pytest
  1566 绿 + policy 门禁零命中。

- **行尾注释统一为 `_comment_slots["trailing"]`（A2 双轨消除）**：parser
  `collect_following_comments` 行尾注释挂载从 `_attached_comments` 并入
  `_comment_slots["trailing"]`（renderer 同 LineSuffix 渲染）——消除
  "attachment 属性 + trailing 槽"双轨（ADR-0013 阶段 A 前遗留，读侧
  靠向后兼容分支 + transform 迁移双轨为代价）。删除：node_renderer
  attached 兼容分支、transform/engine `_collect_subtree_comments`/
  `migrate_comments` 的 acc_attached 通道、去重集合 `_attached_seen` 改名
  `_trailing_seen`、2 个 legacy 测试。`_comment_anchors` 记录保留（tpc
  marker 还原通道，不受影响）。验证：注释专项 94 + normal 32/32 + real
  9/9 保真不降 + 全量 pytest 1542 全绿。

- **pratt op 行尾注释挂 RHS leading（ADR-0014 ②方向 B）**：operator 间隙
  的行尾注释（`a || // bgeu\n b`）不再走 comment_sink（渲染重排后锚匹配
  失败 → 丢），`_skip_gap_comments` 返回 eol 注释并挂后续 RHS 子节点
  `_comment_slots["leading"]`——`//` 注释必处行尾、随操作数独立断行机械
  安全；BinaryOp 挂 right、Ternary 挂 true_val/false_val、Unary 前缀挂
  operand。darkriscv BMUX `|| // bgeu/bltu/bge/blt/bne` 5 条 + 全量
  保留不降（源/输出注释 403/403）。关键坑：操作数可来自外部 atom_parser
  （linter ExpressionChecker 返回 object() 占位）——挂载须 Node 守卫，
  否则 linter 表达式解析抛异常 → 语句 unrecognized 误报。

- **容器开括号同行 line comment 领为 head Comment（ADR-0014 ①）**：
  `sub u (//RF interface\n .port...` 与 `(` 同行非独占行，B1/B1.3 不收；
  `_claim_head_comments` 增第二来源（`_comment_anchors` 中紧前 token type
  以 `bracket.l_` 开头、line < 规则末行的条目）挂 Comment 子节点——
  serv_top 55/55（此前唯一丢的 `(//RF interface`）。

- **restore 函数清理为纯 tpc 通道（ADR-0013 阶段 B1.5）**：restore_comments /
  restore_line_comments 删除 only_tpc/only_midline 参数与普通注释分支
  （B1.2/B1.4 后无调用方，恒 tpc 语义）——函数只处理 tpc marker
  （`/*<tpc:*>` 宏 marker / `// <tpc:*>` 条件占位，宏/条件块还原依赖），
  普通注释条目直接跳过。tpc 还原面 101 测试 + run_all real 9/9 + 全量
  pytest 1540 全绿。

- **删除 inline 通道 midline 回插（ADR-0013 目标④达成，B1.4）**：
  行中注释回插兜底实测纯冗余（normal 组禁用前后输出一致，仅 join 分隔
  符形态 1 条需补渲染）——join 原语消费容器节点 inline_after 中锚=分隔
  符的行中注释（`clk, /* c */ output`）后，restore_all_comments 移除
  midline 分支、pipeline collect_inline_after_leftover 删除——普通注释
  restore_comments/restore_line_comments 回插通道全部删除（line B1.2 +
  inline B1.4），仅剩 tpc marker 独立 only_tpc 通道（宏/条件块还原依赖）。

- **容器首元素前独占注释进树（ADR-0013 阶段 B1.3）**：B1.2 删除 line
  通道后，容器**首元素前**独占注释（`module m (\n // head\n input a`）
  无兜底丢失——行首规则成功时领前置独占注释挂 Comment 子节点（sub_node
  首位），join 拆段独立行渲染（首注释段硬 Break）。repeat 迭代深度协调
  保证与 B1（迭代项间 Comment 迭代项）互斥不双份。门禁：
  tests/e2e/test_comment_container.py::TestContainerHeadComments。

- **删除 line 通道普通注释回插（ADR-0013 阶段 B1.2，目标④主体）**：
  B1/B1.1 后普通独占行注释全部进树（容器项间 Comment 迭代项 / 块结束符
  trailing / block body Comment 节点）——41 文件实测 restore 开/关输出差
  仅 1 条且为锚点错插缺陷，删除净改善。restore_all_comments 移除
  enable_line_comment_restore 参数与全量普通回插分支，line 通道恒
  only_tpc（宏/条件块 marker 还原依赖）；pipeline/run_all 同步删除。

- **块结束符行尾注释进树（ADR-0013 阶段 B1.1）**：块规则结束符
  （`end`/`endcase`）后的行尾注释（`end // case: x`）此前只记 inline
  anchor——restore 仅回 midline/tpc 不回行尾普通注释 → 丢失。现挂块
  规则节点 trailing 槽（LineSuffix 结构序渲染）。real 语料收益：tv80
  注释保留 509→670（eol 缺失 139→5）。门禁：
  tests/e2e/test_comment_container.py::TestBlockEndComments。

- **容器项间独占行注释进树（ADR-0013 阶段 B1）**：repeat 列表容器
  （PortList/NamedPortList/DeclaratorList/CaseItemList 等）迭代项间的独占
  行注释按**源行号窗口**上浮为 Comment 迭代项进容器 items（结构序），
  renderer join 独立行段渲染——替代宏展开场景（line 通道 only_tpc 不回
  普通注释）的注释丢失。real 语料收益：serv_top 26→54 保留、tv80 480→509。
  实现：parser 吞注释记录独占行标记 + `_repeat_loop` 行号窗口上浮 +
  绑定 list-spec 保留 Comment 项；tpc marker 与行内/行尾形态保持既有通道。
  门禁：tests/e2e/test_comment_container.py（5 测试）。

- **署名加入 AI 协作者（方案 A 定稿）**：主作者 biominescence（方向/决策/
  发布/维护）+ AI 协作者 `deepseek-v4-flash`（核心引擎、语法包与验证套件
  协作实现）——`packaging/attribution.py`（单一来源）`--credits` 输出
  `AI Co-author` + `Implementation` 行、`pyproject.toml` authors 两条目、
  PE 版权信息、README `Attribution` 段同步。披露充分但不越界：模型署名
  留在协作者/实现层，作者（责任人）仍为自然人。

## [0.1.0] - 2026-08-22

Alpha 发布——配置驱动语言管线首版：主包纯净可综合 + 仿真插件化 + 第二语言实证。
发布定义（2026-08-21 定）：0.1.0 = Alpha；语法剩项（门级/UDP/specify）后置非阻塞。

### 首版能力

- **配置驱动语言管线**：语言规则全部在 TOML（`grammar/<lang>/`），引擎为通用骨架；
  lex/parse/analyze/transform/render/lint/preprocessor 全阶段可配置、可 fork
- **两个语言包**：`grammar/verilog/`（可综合子集 + 增强语法 typed_ports、formatter、
  semantic_check、attributes、sim 插件）+ `grammar/c4/`（最小 C 子集 → c4 VM 汇编，
  语言无关性实证）
- **前置 token 级 linter**（反解析器，复用同一 TOML 语法，能检查坏代码）
- **增强语法 typed_ports**：`type` / `type.role` / `impl`（嵌套 / invert / 参数化 /
  端口位宽闭环），展开 / 保留双路径（expand_enhanced）
- **formatter 插件**：缩进 / 品类对齐 / 实例端口对齐 / 惩罚模型 wrap / 风格参数化 /
  幂等保持
- **预处理器**：宏展开 / 条件编译还原 / 指令原位回插（带参宏、`include 递归、循环检测）
- **仿真语法插件化（plugins/sim）**：可综合子集进主包、仿真语法进插件 → 主包纯净
  可综合 = 发布基线
- **CLI `tpc`**：format / lint / expand / config dump / new component / init /
  pipeline / --version；版本单一来源（core.__version__，pyproject 锁定一致）
- **工程化**：CI（Windows/Ubuntu × Python 3.11-3.13）、覆盖率门禁 80%、全局 profile
  层（`~/.tpc/config.json`，env > 工作区 > 全局 > 内建默认）、配置来源追踪
  （`tpc config dump`）、wheel 打包保留多语言包目录结构
- **边界诚实记录**：README Known limitations 4 组 22 条

### 首版内已修（Fixed）

- **role 端口 packed_range 位宽丢失**（接口位宽闭环）：展开路径保留 `[7:0]` 位宽
- **nested+invert SKIP 泄漏**（L1 防御）：不再向端口列表泄漏字面 `SKIP,`
- **linter `--json` 崩溃**：`to_dict` 死代码 → `lsp_diagnostic`
- **未定义 task/function 调用检测**（semantic_check 插件，W002，支持前向引用）
- **第二语言渗透修复**：7 处 core 单语言假设清理（见 docs/language_walkthrough.md §7）

### 验证基线

769 pytest + e2e 93 绿（FAIL 0）+ lint recall 31/31 零误报 + 覆盖率 ~83%
（fail_under 80）+ real 组（PicoRV32 / darkriscv / SERV / TV80）+
edge 门禁（12 边界语料）+ 差分对拍（124 合法文件 vs Verible，0 假拒）+
fuzz（~8000 轮，不崩溃 / token 保序 / 幂等不变量）。

### 2026-08-22 (发布准备：验证体系 + 独立 formatter + README 重写)

- **验证体系（tests/fuzz + tests/edge + tests/differential）**：语法驱动 +
  变异 fuzzing（不变量：不崩溃 / token 保序 / 幂等）；边缘构造门禁（clean 必须
  成功 / reject 必须失败）；与 verible-verilog-format 差分对拍（接受域 +
  互操作，二进制经 `tests/differential/fetch_verible.ps1` 获取，gitignored）。
  fuzz 直接从 grammar TOML 派生生成空间——配置即数据的验证红利。
- **fuzz 发现的 4 个真实缺陷（均已修复并沉淀 edge 回归）**：
  - 畸形输入过 lint → parser 截断 → 管线静默 `success=True` 且**丢内容**
    （`_stage_parse` 现检查 `_parse_truncated`，截断即失败）
  - `module name #()` 空参数表解析不了（`ParameterList` 的 `@ParamDecl` 改可选）
  - 畸形 ANSI 函数端口（缺端口名）→ parser `assert` 崩溃（改安全恢复，用户
    输入永不崩溃）
  - 自引用宏 → 宏体预展开指数膨胀 `MemoryError`（直接自引用跳过 + 体长上限）
- **README 全量重写**：按业界 README 结构（首屏定位 + 徽章 + 演示 + Why/
  when-not + Quick start + 文档分流 + 贡献指南 + 状态），559 → ~350 行；
  Known limitations 精简为摘要，完整版移入 `docs/known_limitations.md`。
- **功能切面打包管线（tpc-fmt.exe / tpc-lint.exe，Nuitka）**：按
  `packaging/facets.json` 切面规格打包单一文件 exe（内置 Python + 引擎 +
  语法包，~8.3 MB）；`packaging/build_pipeline.py` 生成入口（命令可裁剪，
  复用 `main._register_subparsers(allow)`）→ Nuitka onefile → SHA256；
  PE 元数据 + `--credits` + 二进制内嵌署名（`strings -el` 可扫）；
  文档 `docs/packaging.md`。
- **语义检查插槽设计落档**（未实现，设计先行）：`docs/decisions/0004-
  semantic-check-slot.md`（双层规则 + post-pass 链式检查）+ `docs/semantic_checks.md`
  + 前置调研 `docs/references/static_checkers_survey.md`。

### 2026-08-23 (发布收尾：GitHub 上线 + CI 首跑三修)

- **GitHub 上线**：仓库 `DogStraight/trans-paradigm-compiler`（public）——dev 分支
  推送 + tag `v0.1.0`（正式发布锚点）；旧版本 tag（v0.1/v0.11/v0.2.0）降级为
  milestone-* 里程碑（版本号伪装去除，指针保留）。提交邮箱已关联账号。
- **CI 首跑三修**（12 任务矩阵首跑暴露 3 类本地测不出的缺陷，均已修）：
  - `FileManager.get_full_path` 绝对路径 POSIX **翻倍拼接**：`lstrip("/")` 把
    绝对路径当相对路径拼 `_base_dir`（Windows 靠 Path 盘符替换碰巧正确，
    Linux 必炸）→ 绝对路径原样透传（normpath），新增 2 个回归测试
  - ci.yml wheel 冒烟 `cd /tmp` 后相对 `_venv/bin/tpc` 失效（exit 127）→
    `$GITHUB_WORKSPACE/_venv` 绝对路径
  - 测试硬编码本机绝对路径 4 处（`e:\project\tpc_compiler\...`，味道审查
    标记过的边界项）→ `FileManager.get_full_path` 可移植解析
- **CI 12 任务矩阵全绿**：test + wheel-install ×（3.11/3.12/3.13）×（ubuntu/
  windows）——含 wheel 安装后从任意目录运行 CLI 验证。
- **README 切片声明**："Sliceable — take only what you need"（format/lint/
  expand/全管线独立可用，切片自助、管道整体维护）。
- **注释味道审查 + 卫生清理**：rubric（`docs/comment_smell_rubric.md`）+
  前人调研（`docs/references/comment_smell_survey.md`），8 子代理 × ~211 文件
  全审（全部件"轻"味，人味 6-9/10）；正确性问题 + AI 味收紧 + grammar 卫生
  全部清理（TODO P2.4 清零），tests 引导样板抽公共模块 `tests/_bootstrap.py`。
- **注释正确性修复**：过时类名/失效路径/文档漂移/死 docstring/语言渗透措辞
  （"Verilog file" → "source file"）等 34 处。

### 2026-08-21 (typed_ports 接口位宽闭环)

- **role 端口 packed_range 携带（TODO P1.5 完成）**：typed_ports 展开路径不再丢
  端口位宽——`output [7:0] mosi` 写在 role 端口时展开为 `output [7:0] spi_io_mosi`
  （此前退化成 1 bit）。覆盖直接引用 / 参数引用（`[DATA_WIDTH-1:0]` 字面透传）/
  invert / 嵌套类型 / wrapper 模块端口。
- **nested+invert 组合 SKIP 泄漏防御（L1）**：`slave : spi.slave inner, invert
  master;` 展开不再向端口列表泄漏字面 `SKIP,`——映射表 `_merge_to_flat` 过滤
  无端口名空行 + `_expand_primitive` 过滤无产出结果（双保险）。语义缺口（invert
  对含嵌套引用 role 的嵌套展开端口不参与反转）与边界如实记录于 README Known
  limitations / TODO.md P1.5（L2-L3 未修）。
- **emit 原语扩展**（通用能力，引擎无语言知识）：`emit` 支持 `node_name` 键别名
  与 `{ref = "path"}` 原始值透传；捕获数据（node_name 形态 dict）可直接递归重建
  AST 节点（如 Range → msb/lsb 表达式树）。
- **`_process_items` 字段提取修正**：`{$....}` 字段源数据缺键时跳过该字段，
  不再把字面模板字符串塞进行数据（emit 端 ref 透传缺失 = 无此属性）。
- **测试**：新增 `tests/languages/verilog/test_typed_ports.py`（位宽场景 + nested+invert
  SKIP 防御，共 8 项）。
- **测试输出编码修复（Windows）**：`tests/conftest.py` 在收集前强制
  stdout/stderr 以 UTF-8 输出——本机活动代码页 GBK(936) 时 Python stdout 默认
  GBK 编码，中文测试输出（docstring/断言）在 UTF-8 解码侧乱码。

### 2026-08-18 (Engineering gaps)

- **Pipeline split**: `run_pipeline_on_source` 515 lines CC=98 → 173 lines CC=30
  (per-stage functions + `_PipelineContext`); matcher `_match_call_impl`
  151 lines CC=48 → 35 lines CC=7 (per-rule-type methods)
- **Doc: back-references**: 3 → 14, covering all 10 MODEL_INDEX entries
- **Unused imports**: cleaned 6 real issues (kept re-export compatibility)
- **Docs hygiene**: one-time plan docs removed after completion (results
  recorded in CHANGELOG)

### 2026-08-18 (Open-source readiness)

- **Config complexity management**: config source tracking (`_sources` /
  `resolve_with_sources`), `tpc config dump` debug command, declaration
  structure validation, GrammarRule field schema (fail-fast)
- **Lexer config dependency injection**: token/number configs now follow the
  language pack (no more cross-language contamination in one process)
- **Pipeline moved to `pipeline/` package**: `run_pipeline_on_source` shared by
  CLI and tests; wheel install works from any directory
- **Packaging fixed**: grammar TOML shipped as package-data (preserves
  verilog/c4 directory structure); IEEE Annex A docs and PDFs excluded from
  sdist (copyright)
- **Docs**: code quality audit, config complexity plan, open-source readiness plan

### 2026-08-13 (P2 engineering wrap-up)

- Documented P2.0 items: config_lifecycle / expression_conventions /
  component_protocol / c4 minimal language-pack template
- Install verification: `pip install -e ".[test]"` + CLI smoke test
- Coverage gate: .coveragerc (omit entry/fallback, fail_under=84, measured 84.57%)
- Restored CI: .github/workflows/ci.yml (Windows + Python 3.11/3.12/3.13)
- Fixed: linter `to_dict` dead code → `lsp_diagnostic` (`--json` crash bug)
- Removed dead code core/component_loader.py (superseded by plugin_loader)

### 2026-08-13 (P1 complete)

- formatter: width wrap pass, SV base coverage (logic/always_ff/always_comb),
  style parameterization (formatter.style)
- Preprocessor primitive-level unit tests (19)
- Enhanced render verification (nested/invert + TypeNestedPort layout)
- Number-shape configuration: declaration → FSM generator + language-pack
  declarations + signed `'s` + `0'b1` standard rejection

### 2026-08-12 (P0 second language)

- c4 full implementation (.c → c4 VM assembly), 6 integration tests — proof of
  language-agnosticism
- P0.3 penetration cleanup: boundary language penetration removed (ScopeKind
  rule derivation)
- Fixed 7 core penetrations / single-language assumptions (see
  docs/language_walkthrough.md §7)

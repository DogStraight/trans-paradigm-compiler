# Changelog

All notable changes are listed in reverse chronological order.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **删除 `sync` 锚兼容路线（宏还原）**：锚 `mode` 现为三态（`line` / `inline` /
  `token`）。旧"同步词窗口消歧"（`mode="sync"`）只服务**无 `mode` 字段**的旧格式
  记录，而产出端（`_expand` 的三种锚 + `restore_condition_blocks` 的 cond 锚）
  **全部显式带 mode**——无产生者即删（判据 A3 过时 / A1 无引用）。连带删除：
  `_reverse._normalize_anchors` 旧格式包装、`_bridge._restore_sync_entry` 与
  `preprocessor.reverse` 配置声明、`grammar/verilog/base/_macro.toml [reverse]` 段、
  `grammar/verilog/tpc.toml` 的 `reverse = {...}` 声明、锚条目里已无消费者的
  `is_func` 字段（region 侧保留）。未知 `mode` 现在 **fail-fast**（静默跳过会让
  占位残留到输出——占位与原文的对应关系一旦错，输出就是错的）。
  背景：ADR-0017 决策 4 落地后，非空体宏已改走"宏区间 + 渲染 raw 拼接"，还原锚
  只剩空体宏/行级占位与条件块两支；本次清掉的是第三支的历史兼容壳。
  验证：全量 1925 passed / 8 skipped（含真实语料保真与宏还原门禁）；smoke 363。

- **草稿区能力提升为正式工具（`_drafts/` → `tools/`）**：把清理后仍被引用/仍可用的
  诊断能力从暂存区搬进正式位（草稿区随之为空，纪律仍见 `AGENTS.md` 文档放置速查）：
  ① `tools/dump_pipeline_state.py`（来自 `_drafts/probe_pipeline_state.py`）——打印
  管线语言状态（`_PIPELINE_SHARED` 条目里的 rules/mapping_cfg/schedules、
  `ConfigRegistry` 当前语言、已装载组件），`--pre grammar/c4` 复现"同进程先跑过别的
  语言"，是跨语言串味定案时的现场转储器。
  ② `tools/check_test_isolation.py` 增 `--hashseed-scan N`（吸收
  `_drafts/hashseed_probe.py`）：换 PYTHONHASHSEED 维度做"换跑法就变脸"检测；比对用
  **去计时**摘要，否则每个种子都因耗时不同被判漂移（实测踩过）。
  反之**未提升**（同能力已在 `tools/`，A2 双实现 → 草稿侧删除、引用统一）：
  `_drafts/probe_macro_anywhere.py` 对应 `tools/check_macro_coverage.py`（同一不变量
  与度量，ADR-0017 正文引用统一到后者）；`_drafts/probe_efficacy.py` 对应
  `check_gate_efficacy` 第 5 条变异。
  守护：`tests/policy/test_tools_diagnostics.py`（3 例，跑通 + 关键结论行）+
  `tests/policy/test_check_test_isolation.py` 扩到 16 例（含"必须能报出种子漂移"的
  正反例与去计时判据）；`docs/decisions/0017` 的引用路径同步为新工具。
  全量 1906 passed / 8 skipped；smoke 362；policy 109；两项门禁脚本全绿。
- **管线单元：语言包级声明 + verilog 显式时点编排（迁移第一步）**：单元机制
  （0.1.2 阶段 5-7）此前只有测试用过——声明只能放组件目录（**编排的归属错位**：
  组件是语言包的实现单元，不是编排单元，声明随组件目录存废而变），且文档写的
  `[[pipeline.units.x]]`
  形态与 loader 实际要求的 `[[pipeline.units]]` + `name` 不一致（照文档写即报错）。
  现：① 语言包根 `tpc.toml [pipeline] units` 与组件声明**两源合并**（同名 fail-fast；
  根 `[pipeline]` 段多余键不静默忽略）；② `grammar/verilog/tpc.toml` 声明 4 个单元
  （`analyze` → `slots` → `map` → `codegen`），与 transform 插件注册序**逐一对齐**
  （等价迁移）；③ `pipeline/README.md` 声明形态纠正为 loader 真实方言，并补
  "产物即数据路径"说明。验证：全量 1906 passed / 8 skipped（同基线）；
  `tpc trace` 可见 4 个显式时点（含产物/依赖回指）。
- **管线单元（阶段 2：c4 等价迁移 + 作用域校验）**：c4 语言包显式声明它**真跑**的
  单元（`analyze` → `asm`）——c4 无槽位声明、无 mapping 条目、规则无 `[X.transform]`
  配置，三个引擎插件单元在本语言下都是空跑（`slot_runner` 承接 0 槽位即不产出），
  故不声明；输出与迁移前**逐字节一致**（汇编 + `AsmProgram`）。另：插件单元加
  **语言作用域校验**（引用了不在当前语言作用域内的插件 → fail-fast；插件注册表
  进程级累积，按名字解析本身不区分语言）。守护：`test_language_units.py` 增至
  7 例（c4 声明 + 作用域违规）。
- **postpass 链收编进单元/契约体系（迁移阶段 3）**：analyzer 的 post-pass 链
  （typed_ports 展开、inst_check/width_check 等检查）此前是**第二套隐式顺序**
  ——顺序只由组件名排序碰巧成立，两条真实依赖仅写在注释里（`_expand_ports` →
  `_check`、`hier_check` → `width_check`）。现：
  ① 声明面改表形态 `[[analyzer.postpasses]] + run`，加可选 `produces`/`requires`
  （字符串列表形态撤销，9 个组件同步迁移，无双方言）；
  ② **链内契约**：`requires` 须由更早环节 `produces` / `scope` / 链启动时
  `context.extra` 提供，否则 fail-fast——两条真实依赖已声明（`resolved_ports`、
  `hier_member_table`），不再靠组件名排序碰巧对；
  ③ 每环执行进管线**单元轨迹**（`artifacts.postpasses`：名字 + 本轮诊断数，含链尾
  L1 规则执行器）——链也是时点，`tpc trace` 可见。
  与 transform 单元契约的区别：postpass 产物写在符号表/context 上，引擎不懂语义，
  故只校验**时点可达性**（不核实物化）。守护：`tests/engine/analyzer/test_postpass_chain.py`
  （8 例：真实契约与顺序、表形态与 fail-fast、契约违规/满足、轨迹记录）。

### Fixed

- **`setup_grammar` 静默吞掉组件装载失败**：`parser/__init__.py` 的组件装载段包在
  `except ImportError: pass` 里——装载期任何 ImportError（插件模块循环导入/部分
  初始化等）被静默吞掉，语言作用域停在上一语言、组件规则整段缺失。实测：全量
  并行跑时 `test_plugin_scope_excludes_other_language` 失败过一次（切到 verilog 后
  c4 的 `AsmGenPlugin` 仍在 `active_plugin_classes()` 内），复跑不复现——症状与该
  静默路径一致（未能证明因果，但该失败模式已被消除）。现改为 **fail-fast**
  （不吞异常），与「配置加载 fail-fast、不静默降级」硬约束一致。
  守护：`tests/engine/core/test_language_switch.py::
  test_component_load_failure_is_not_swallowed`（桩掉装载 → 异常须逃出）。
- **契约只是装饰：`produces`/`requires` 未真正成为数据路径**：`ConfigDrivenTransform`
  声明的 `requires=["mapping_tables"]` 由引擎校验，但它实际靠**扫同 transformer 的
  兄弟插件**拿映射表——按契约把 map/codegen 拆成两个时点（各自 transformer 实例）
  后映射表拿不到 → typed_ports 展开全丢（16 个测试红）。现：`note_produced` 登记的
  产物同时发布到调度累积的**产物通道**（`PassState.productions`），消费方按契约名
  取用（跨单元成立）——删掉兄弟插件扫描，单一数据路径。另：被开关跳过的单元不再
  参与契约校验/物化核验（跳过 = 无产物是预期，非配置错）。
  守护：`tests/engine/pipeline/test_language_units.py`（5 例）；
  `tests/languages/verilog/test_mapping_origin.py` 的 trace 断言改为按插件名聚合
  （不再假设只有一条 transform 条目）。
- **语言作用域跨语言串味（"幽灵 flake"的机制）**：同进程「先跑 c4 管线 → 再跑
  verilog」时 verilog 输出变**空**且 `success=True`（保真度 0.9925 → 0.0000），
  实测于 HEAD，不是历史遗留。三处语言作用域状态跨语言累积，任一处都能让别的
  语言的结果变样：
  ① `GrammarRulesRegister.get_default()` 只增不清 → 后一语言的 rules 字典混入
  前一语言规则**且顺序靠前**，而 `RuleSelector.get_block_rule()` 取"第一个匿名块
  规则" → **根规则被前一语言夺走**（verilog 源码按 c4 的 `Program` 解析）；
  ② `transform.engine._plugin_registry` 累积且 `AstTransformer` 会实例化并执行
  **全部**登记插件 → 别的语言的 transform 插件参与本语言管线（`AsmGenPlugin` 的
  根守卫恰好被 ① 造成的 `Program` 根通过 → AST 被换成 `AsmProgram`）；
  ③ `_PIPELINE_SHARED` 缓存组件后，切回**已缓存**语言时 `ConfigRegistry`（进程级
  "当前语言"）仍停在别的语言上 → 该语言的 token 类别/原子映射是别人家的
  （c4 → verilog → c4 时第二次 c4 解析截断）。
  修法（原则：语言切换 = 重建语言作用域）：`GrammarRulesRegister.begin_language()`
  切语言即重置规则表并按路径规范化去抖；`plugin_loader._active_components` 在装载
  时固化语言作用域 + `transform.engine.active_plugin_classes()` 按它过滤插件
  （引擎插件恒在）；`pipeline._ensure_language_config()` 每次确认配置停在当前语言。
  守护：`tests/engine/core/test_language_switch.py`（7 例：双向 + 来回切换的端到端
  保真度、规则表无残留、根规则归属、插件作用域、配置声明随语言）；门禁有效性进
  `tools/check_gate_efficacy.py` 清单（关掉重置即变红，实测 ratio 0.9925 → 0.0000）。
  订正：`core/global_state.py` 的 `ACCUMULATED` 表原写"跨语言多出来的条目不被引用"
  ——**已被证伪**（插件是全部实例化并执行），安全来自应用侧作用域过滤而非注册名限定。
  全量 1900 passed / 8 skipped；单进程串行全量 1900 passed / 8 skipped（443s，
  正是该 bug 赖以发作的"多语言同进程"场景）；`check_gate_efficacy --only 5`
  如期变红（关掉 `begin_language` 即红）。

### Changed

- **测试隔离 L4：进程级隔离对照**：新增 `tools/check_test_isolation.py`——把选中集
  切块（默认每文件一块）在**全新解释器**里各跑一遍，再与**单进程共享档**对照，
  把"换一种跑法就变脸"分成两类并指名到位：只在共享档失败 = 进程内状态泄漏/顺序
  污染（补 `core/global_state.py` 登记表或改 fixture 作用域）；只在隔离档失败 =
  该用例隐式依赖同进程里其它文件留下的状态。**不用 `pytest-forked`**：它走
  `os.fork`，Windows 没有（实测 `hasattr(os, "fork")` 为 False），CI 矩阵含
  windows-latest——故用子进程实现（跨平台、零新依赖）。附带 `--granularity
  file|test`（单用例一进程 = 最强隔离）、`--jobs`、`--random-hashseed`。
  nightly 加快速层对照档；工具不进日常门禁（全量要起上百个解释器）。
  自保用例 `tests/policy/test_check_test_isolation.py`（13 例，含"真能报出差异"
  的端到端负例与路径/省略形态判据）。验证（全量 1901 用例，两次独立跑一致）：
  隔离档 144 块 **0 失败（~2 分钟，jobs=16）**，单进程共享档 1893 passed /
  8 skipped（~9 分钟），两档一致——即全库已无进程内状态耦合（幽灵 flake 那一类）。
- **测试隔离 L3：顺序可控（把偶发变必现）**：①`pytest addopts` 显式
  `--dist loadfile`（一个文件固定在同一 worker，模块级 fixture 与"安装态按模块
  还原"语义绑定在同一进程）。②`tests/conftest.py` 新增零依赖的顺序随机化 hook
  ——`TPC_SHUFFLE_SEED=<int>` 做**文件级**乱序（种子固定 → 失败可复现；单用例级
  乱序不在范围：模块/session 级 fixture 在其作用域内合法拥有安装态）。③CI：日常档
  固定 `PYTHONHASHSEED=0`（PR 加乱序 smoke 档），nightly 加全量乱序档 + 哈希
  种子每进程随机的巡检档。守护：`tests/policy/test_order_shuffle.py`（同种子同序 /
  不拆散文件 / 未设环境变量不动序）。
- **顺序巡检当场拓出一条真实边界（登记表新增 `ACCUMULATED`）**：`--dist loadfile`
  下的默认序曾 5 例 c4 失败——语言注册面（插件/原语注册表）**不能**按模块还原：
  写入者是模块导入副作用，而 `plugin_loader` 缓存组件模块（sys.modules 命中即不重
  exec）→ 还原后缓存命中不重注册 → 已装载语言拿不到自己的插件（`AsmGenPlugin`
  不生效，transform 退化为 `Program`）。现登记为“只增不还原”表并写明理由；同时
  删掉随之失效的 `keywise`/`prefix` 还原策略（无使用即删）。全量默认序 1880
  passed / 8 skipped；乱序档 seed 1/2/3 均绿；串行+乱序（languages+engine）
  1665 passed。
- **测试隔离 L2：外部资源隔离**：①中间产物落盘改为**只认显式 `out_dir`**
  ——删掉 `pipeline` 里"input_path 含 samples 就写回样本目录"的嗅探：测试并行时
  多 worker 对同一样本并发写同名 gen/ast/symbols（撕裂读 → 偶发保真抖动），且把
  测试语料布局约定藏进了正式包；now 测试调用零仓内写入（实测 e2e 全跑后
  `tests/e2e/samples/**` 无新文件），samples 约定归 `tests/e2e/run_pipeline.py`
  测试 CLI。②`_PIPELINE_SHARED` 缓存键补 `ext_dirs`（原只键 rules_dir，同语言
  不同 ext_dirs 会静默复用组件与规则）。③保真度缓存条目改**内容键控**
  （`{sha, fidelity}`；样本源改过即不算基线），消除陈旧基线造成的幻影 drop。
  ④`check_hardcode` 新增规则 5 [gate]：测试文件禁 `os.chdir`（进程级 CWD 泄漏
  → 并行 worker 互踩相对路径；用 `monkeypatch.chdir`）。全量 1872 passed / 8 skipped。
- **测试隔离：全局态登记表 + 覆盖门禁 + 两层还原（L1）**：`core/global_state.py`
  的覆盖从手工表 → 五张登记表（`TRACKED` 测试级 / `INSTALL_STATE` 语言安装态 /
  `CONTENT_ADDRESSED` / `CONSTANT` / `COVERED_ELSEWHERE`）+ 自动发现模块级/类级
  可变容器，`tests/policy/test_global_state_coverage.py` 断言发现集 ⊆ 登记集
  （新增全局态不登记即红）。`restore()` 分两层：测试级每测试还原（派生缓存、
  共享上下文、深度计数器、注册表新增项），安装态每模块还原（pratt 安装态、
  插件/原语注册表——逐测试擦除会打断模块级 fixture 装载的语言）。每测试还原后
  立即 `assert_clean` 比对基线指纹。过程中的两处修正：keywise 还原改为
  "去掉新增 + 补回被删基线键"（原先只删不补，会把语言重注册清掉的基线项永久
  丢失）；快照前预热全部登记条目的按需导入（导入有注册副作用，否则快照内容
  依赖触发顺序，快照与还原读到不同集合）。全量 1862 passed / 8 skipped。
- **阶段 9 终验（0.1.2 收尾）**：覆盖率门禁 **86.81%**（≥ fail_under 80；
  串行 `-n 0` 全量 1851 passed / 8 skipped）；e2e 102 组 **FAIL 0**（66 OK /
  36 预期 ERR）；lint recall 33/33、零误报；eval_check_accuracy recall 100%
  （FP 0）；`check_hardcode --strict-doc --strict-import` 与 `check_doc_refs`
  全绿。终验抓到一处潜伏门禁违规并修复：`main.py` 的 `Doc:` 头在 api.md
  删除时遗漏重指（`R3` strict 升 gate 后暴露）——补 `Doc: README.md`。
- **自定义规则范例（0.1.2 阶段 8 / T2 收尾）**：新增 `grammar/verilog/plugins/
  checks/custom_rules_example/`——两条规则各走一条路径的可运行范例（EX001
  非 ANSI 端口声明=**postpass 路径** / EX002 parameter integer 类型提示=
  **handler 路径**），`default=false`（默认关，对默认诊断面零影响）；配套
  对照样本（pos×2 + neg×1）与 `focus` 条目（评测启用，recall/误报面纳入门禁）；
  目录 README 含照抄四步与启用方式；`checks/README.md` 双路径节加指引。防误报
  回归：函数/任务子树跳过（先例 `_fill_body_ports`——旧式函数参数与模块体
  端口同节点名）。测试 `test_custom_rules_example.py`（7）。
  \* T2 批判式吸收三态落定：排版卫生族已入（ST001-003）；空格规范族**不采纳**
  （与 formatter 列对齐协调成本 + 品味性强）；ANSI 头/参数 2-state 走范例
  路径（本条目）。
- **排版卫生族（ST001-003）+ 诊断阻断性（0.1.2 阶段 8 / T2 首项）**：linter 层
  解析前行级检查——尾随空白（ST001）/ 制表符（ST002）/ 行长超限（ST003，上限
  引用语言包 `[style_check].max_line_width`，与 formatter 折行阈值同值约定）；
  子检查各自开关，未声明该段语言包不注册。配套引入 `LintDiagnostic.blocking`
  （区分"语法阻断"与"卫生提示"）——ST 为 blocking=False/severity=2：**不跳过
  语义分析**（structure）、**不计失败退出**（checker / lint CLI） 、**不截断
  管线**（_stage_lint 按码汇总一行，不逐条）。真实语料基线显式更新（+5407 条
  ST，真诊断非误报；semantic 面持平）。测试：`test_linter_style.py`（11）+ 
  checker 非阻断语义用例（≥=2 退出码/语义不跳）。
- **trace 报告时间轴呈现（0.1.2 阶段 6 收尾切片）**：`tpc trace --html` 页面
  重排为"管道条 + 单列左轴"——顶部**执行管道条**（单元节点链，箭头标上游
  `produced` 流；节点/卡片锚链互通）；卡片区左侧一条轴 + 轴节点（按 kind
  着色）；卡片新增**依赖行**：`requires` 名机械回指上游产出该名的单元（名字
  等值匹配，纯数据不认识语义；无上游记录时只显名字）。trace 条目补
  `requires` 字段（非空才带）。报告固定浅色皮肤（`color-scheme: light` + 显式
  body 底色）：此前深色模式浏览器会把背景/文字反转，与浅色设计的 badge/表格
  元素混搭。测试 `test_trace_report_html.py`（+4）。
- **pass 契约校验切片 2：物化核验 + 形状（0.1.2 阶段 7 收官）**：`produces`
  不再按声明空转——单元执行后核验**物化登记**（生产方在 `process` 内
  `note_produced(name, obj)`）：声明未物化 / 物化未声明均 fail-fast（声明 =
  物化，双向一致）；可用集按**实际登记**并入（来源核验）。可另声明**形状**
  （`register_plugin(shapes={"名": {"type": "dict"|"list", "non_empty": bool}})`
  ——注册期 fail-fast 校验 spec，执行后机械核验对象）。trace 条目带 `produced`
  （文本与 HTML 报告同显）；跳过单元不再读到上一单元的 transformer
  （`_run_pass_transform` 入口重置，核验/自述来源可靠）。声明对齐：
  `asm_gen.codegen` 去除未物化的 `extra_asts` 声明（实际产出 = 替换 AST 主输出）。
  测试 `tests/engine/pipeline/test_contract_check.py`（+8，共 13）。
- **插件单元实例化参数（`params`，0.1.2 阶段 5b-3b）**：`[[pipeline.units.*]]`
  的 `params` 表 = 插件**构造器关键字参数**（执行层 `cls(**params)`）——同一插件
  可注册为多个实例（各自参数与时点，如 `SemanticMappingPlugin` 的 `raw_config`
  覆写）；加载期按构造器签名核验（`inspect.signature` bind），未知参数 / 缺必需
  参数 → fail-fast；槽位 / 内置 / handler 单元声明 `params` → fail-fast。trace
  条目带 `params`（可视化）。测试 `tests/engine/pipeline/test_unit_params.py`。
- **诊断行号回源（check 链，P3.3 (a)）**：`scan_directives` 新增第 7 返回值
  `clean_to_raw`（行+行号对账本：续行合并取段首行、条件压缩按实际归属、include
  拼接行 `None` 不可映射），与 `expand_tokens` 的展开级映射两级复合后经
  `FileResult.line_map` 进入 `_syntax_diag`/`_semantic_diag`（含 related）换算——
  宏/条件编译文件的诊断行号从“展开后行号”回到**原始源行号**；不可映射时保守
  回退展开行号（不给错误回填）。管线 lint 日志行号同步两级回源。实测：7 处
  调用点同步；`ifdef` 压缩/续行合并/include 三类形态断言全绿。
- **诊断宏归因（check 链，P3.3 (b)）**：`_expand_source` 把宏区间表
  （`expand_tokens` semantic 产出的字符区间）换算为**展开行区间**（+ 宏调用
  原始行）存 `FileResult.macro_regions`；`_syntax_diag`/`_semantic_diag` 对落在
  宏展开区间的诊断加 `"macro": "<NAME>"` 字段——宏体触发的诊断可按宏归类/
  抑制，调用行锚点供 IDE 跳转。未展开/顿路径无表 → 不产字段。
- **解析侧改吃真展开**（2026-09-13）：解析输入由保真锚形态切到 `expand_tokens(semantic=True)`
  的展开文本——语法结构直接由展开文本判定（类型位宏 `` input `NT d `` 不再需要任何
  语法槽位），宏调用原文由**区间表 + `_verbatim_text`** 挂在覆盖节点上供渲染还原
  （引擎级 raw 拼接，语言包零宏知识）；锚机制收缩为空体宏/行级占位，另保留
  `parse_raw=True` 可选路径。实测：曾失败的 4 个真实语料文件（ice40 / picorv32 /
  darkriscv / tv80）全部解析通过；宏位置覆盖 **37% → 63.7%**（`tools/check_macro_coverage.py`，
  86/135）；`test_macro_type_slot.py` 6 个 strict-xfail **全部翻正**；e2e 102 组 FAIL 0。
- **pratt 行首运算符续行**（`parser/pratt_parser.py` 中缀循环）：原“遇 newline 非运算符
  自然 break”把 `ALL0\n + ALL1` 截在 `ALL0` → linter 语句匹配要求 `;` 却遇 `+` →
  整句判不出（`phase-unrecognized`，无宏也触发）。修法：跳过 trivia 后若下一个显著
  token 是**中缀**运算符则续行（行首中缀运算符不可能是语句起点；不变量有专测
  `tests/engine/linter/test_multiline_continuation.py`）。实测：check 路径 darkriscv
  `syntax 26 → 0` 且**语义阶段首次跑通**（+9 条 UN001 真诊断，源码自带 `// unused`
  注释佐证；诊断基线 132 → 141，真诊断增长）。
- **linter 输入改真展开 + 诊断基线增计 syntax**：`ctx.lint_source`（语义展开）供 linter
  校验真语法结构；`eval_diag_baseline.py` 原先只统计 `semantic`，导致 linter 侧误报面
  无门禁（darkriscv 那 26 条长期无人统计即此因）。

### Removed

- **语法文件中的宏知识全部撤销**（ADR-0017 决策 2/3 推翻重定，2026-09-13）：
  `[Identifier.parser]` 的 `macro.call` 备选、`[MacroCall.parser]`/`.parser.node`、
  `TypeSpec`/`TypeSpecNoReg` 首元素的 `@MacroCall` 槽位，全部删除；
  展开锚形态回退为**普通标识符**（`__tpc_marker_<salt>_<n>`，保留命名空间 +
  盐 + 序号 + 还原唯一性守卫不变）。linter 的锚窗口拼接随之删除（锚不再是宏
  token，拼接已无对象）；`_stage_lint`/`_rewrite_marker_nodes` 回到单形态。

  **依据（实测）**：宏位置本质上是**文本任意**的，逐槽位声明补不齐——新增的
  位置覆盖自查不变量（任一 token 换成等价宏、格式化输出必须不变）：逐槽位声明
  **54/135 = 40%**，撤销语法声明后 **50/135 = 37%**，即整套槽位机制只买到 4 个
  位置；且 layout 自带字面量的槽位（如 range 子槽的 `[` `]`）会多套一对（静默
  错渲染）。新方向 = **外层展开 + 渲染侧 raw 拼接**（宏调用视为不可拆原子文本）。
  验收标尺 `tools/check_macro_coverage.py`；类型位需求以 6 个
  `xfail(strict=True)` 钉在 `tests/languages/verilog/test_macro_type_slot.py`。

### Fixed

- **多声明器重组漂移（formatter，P1.5 缺陷）**：`column_align` 重组多声明行时，
  后续声明符不再逐单元补 `width+1` 列前缀（`_join_semantic(pad_columns=False)`），
  改 `, ` 单分隔紧跟——名字列不再随上一单元长度累积漂移；首单元仍参与列对齐
  （ref 基准风格 `reg dout, din_0, din_1;`，与 Verible 单行多声明形态一致）。
  实测真实语料漂移（`,\s{4,}<ident>`）**226 → 0**（simcells 146 / cells_sim 46 /
  picorv32 28 / tv80 6；更严格的 `,\s{2,}` 同为 0）。门禁补
  `test_column_align.py` 重组输出断言（旧用例只测提取，e2e `_strip_all` 抹空白
  天然失明）；全量 1814 passed / e2e FAIL 0 / 差分 136 文件 0 findings。
- **linter choice 匹配的 trivia 泄漏**（`linter/checkers/matcher.py::_match_choice`）：
  试分支时起点会前移到首个非 trivia token，失败返回却沿用了这个**内部起点**，
  于是被跳过的 trivia 被上层当成"已消费"（`seq`/`repeat`/`optional` 的 `j > i`
  判据全部据此误判），下游 token 流错位。表现为：任一规则 production 含 token
  备选（如 `Identifier` 声明 `["id|macro.call"]`）后，真实代码在**宏无关**的端口
  列表上开始误报（`module m (input clk, output data);` → 2 条 `phase-statement`，
  块头匹配提前收尾、端口项被当语句）。修法：失败路径返回原位置。
  实测：536 例 linter+verilog 回归全绿；全量 1774 passed。

### Added

- **渲染器引擎级 raw 拼接钩子**（ADR-0017 决策 4 切片 ② 的一部分，已就位未启用）：
  节点带 `_verbatim_text`（引擎标记）时整体直出该文本——不走布局、不遍历子节点，
  宏调用于是成为不可拆的原子文本；**语言包对宏零知识**（规则在引擎）。
  另修：语义展开时宏体**末行含行注释**则拼接末尾补一个换行——不补的话宏调用
  **同行的后续 token**（`;`）落进注释被吞，语句丢分号（darkriscv 实测 81 条
  `phase-unrecognized` 的同一根因）。
  测试 `tests/engine/renderer/test_verbatim_node.py`（3 断言）+
  `test_macro_regions.py::test_body_trailing_comment_gets_newline`。

- **宏区间表**（ADR-0017 决策 3 切片 ①）：`expand_tokens(..., semantic=True)` 第三
  返回值 = 每条被铺进文本的宏调用一项，含**源区间**（`src_line`/`src_col`/
  `src_end_col`）与**展开结果字符区间**（`offset`/`end_offset`，含宏体、名字、
  是否带参）。它是外层处理宏的单一事实源：渲染侧 raw 拼接与诊断宏归因都靠它
  定位"哪些内容来自哪条宏"。用字符偏移而非行/列——宏体含换行会让展开结果行数
  变化，偏移天然稳定。默认（渲染路径）为空表，与锚还原不混。
  三处调用面同步改为三返回值。测试
  `tests/engine/preprocessor/test_macro_regions.py`（单行/类型位/含换行体/带参宏/
  同行双宏偏移累加/非语义模式空表/非活跃分支不登记，10 断言）。

- **宏展开锚名协议**（`core/token_protocol.py`）：锚名 = 保留前缀 `__tpc_` +
  `marker` + **源文本 sha256 盐** + 序号（不用内置 `hash()`：PYTHONHASHSEED 会
  破坏跨进程可复现）；还原侧加**唯一性守卫**（命中次数 ≠ 1 则不回插，保留占位
  可见，不静默错还原）。锚仍是**普通标识符**形态（语言包不认识宏）。
  测试 `tests/engine/preprocessor/test_anchor_protocol.py`。

- **`tools/check_macro_coverage.py`（宏位置覆盖自查）**：不变量 = "把任一 token
  换成等价宏（`` `define M <原 token 原文> ``），格式化输出必须不变（宏调用原文
  原样保留、不被展开/重排）"，输出覆盖率 + 失败面（按 token 类型）。把"宏的位置
  支持"从"声明了哪些槽位"变成可测数字（ADR-0017 决策 3/4 的验收标尺）；不进
  日常门禁，人工/按需跑。

- **语言包↔引擎契约（`[engine] api`，缺口队列 ⑤）**：`grammar/<lang>/tpc.toml`
  可声明 `[engine] api = "0.1"`（该包构建所依据的引擎 API 线）；引擎 major.minor
  不匹配即**加载 fail-fast**（`ConfigError`），替掉"升级引擎后包静默坏掉"的隐式
  契约。未声明 = 不校验（纯增量）。双入口校验（`_load_meta_declarations` 的
  `load_all`/`resolve` 路径 + `core/define.py::_load_tpc_meta` 的 import 期默认包）；
  该段不进配置中心。内置 verilog/c4/yaml 三包均声明；引擎 minor 变更时
  `test_engine_compat.py` 的"三包声明当前线"断言会失败（故意，逼一次复核）。
  实现 `core/engine_compat.py`，契约文档 `core/config_lifecycle.md`。

- **parser token span 绑定（P3.1 / 0.1.2 阶段 0）**：解析成功的规则节点/块节点挂
  `_tok_span`（半开 `[start, end)` token 流索引；`core/define.py` 声明 +
  `parser/_production.py` try_plain_rule / try_block_rule 成功返回前写入），供
  增量重解析（P3.2）结构对齐定位。下划线前缀 = 引擎元数据，不进 dump/序列化。
  测试 `tests/languages/verilog/test_tok_span.py`（区间合法 / 父子包含 /
  dump 排除 / 回溯确定，4 断言，标 smoke）。

- **宏体形态分类器（0.1.2 阶段 1）**：`preprocessor/macro_shape.py` —— 宏体放进
  语言包声明的四类最小语法上下文（`[macro_shape].wrappers`：stmt/decl/expr/port）
  包裹解析：能完整解析 → 完整单元（语句/声明/表达式）；全失败 → 残缺片段；另配
  `continue_leads` 首 token 续接预过滤（防 `= 1'b1` 被端口模板误收）。模板与续接集
  是**语言语法知识**（进 grammar TOML），引擎只做通用包裹解析。本阶段只产出分类，
  不接消费点（阶段 2 由 MacroCall 节点消费）。测试
  `tests/engine/preprocessor/test_macro_shape.py`（16 样本 + 配置驱动断言，标 smoke）。
  原型 `tests/_proto_macro_hygiene.py` 已转正删除（验证使命完成）。

- **宏边界节点化（0.1.2 阶段 2）**：parse 后按锚表把宏调用的 `tpc_marker_N`
  标识符改写为 **MacroCall 节点**（带 `_macro_name` / `_macro_marker` 元数据），
  宏边界在 AST 中结构化可见——P3.2 增量 diff / P3.3 双向映射的前提。语言包声明
  `[MacroCall.renderer.layout]` + `[MacroCall.analyzer]` 与 Identifier 对齐，
  渲染与分析**行为零变化**（输出逐字节不变）。测试
  `tests/languages/verilog/test_macro_call_node.py`（4 断言，标 smoke）。
  注：宏体子树进节点 + 渲染改源区间还原 = ADR-0016 终态，归阶段 4。

- **宏处理单一来源门禁（0.1.2 阶段 3）**：侦察确认 linter（`linter/scanner.py`）
  与管线（`pipeline/__init__.py`）调用**同一**
  `preprocessor._expand.expand_tokens`，形态配置由 `preprocessor/macro_shape.py`
  单一读取语言包 `[macro_shape]`——无第二实现/副本。新增
  `tests/engine/linter/test_macro_sync.py` 锁定（函数对象同一 + 配置单源 +
  已定义宏不误报 / 未定义仍报），防未来路径私自复制实现（标 smoke）。

- **宏调用源区间元数据（0.1.2 阶段 4a）**：展开阶段记录宏调用在**源文本**中的
  位置（`_expand.py` token 锚加 `line`/`col`/`end_col`），宏边界节点化时挂到
  MacroCall 节点 `_src_span`（`core/define.py` 声明）。与 `_tok_span`（展开后
  token 流区间）互补 = ADR-0016「raw 源区间权威」的节点级表达（P3.3 双向映射
  基础）。测试加“源文本切片 == `` `NAME ``”强校验。

- **宏体子树提取器（0.1.2 阶段 4b-1）**：`preprocessor/macro_shape.py` 新增
  `build_parse_ast` + `extract_macro_body`——按语言包
  `[macro_shape.wrappers.<key>]` 的 `pick`（节点名路径）+ `skip_head`/`skip_tail`
  钻取宏体对应节点，合成 `MacroBody` 包装节点；wrapper 配置升级为嵌套表
  （`tpl` + 提取路径），提取路径属语言语法知识（进配置），引擎只做通用钻取。
  测试 `tests/engine/preprocessor/test_macro_body_extract.py`（4 形态 + 多单元 +
  残缺回退，标 smoke）。**尚未接入管线**（挂载到 MacroCall 节点 = 4b-2）。

- **宏体子树挂载 + 探测静默（0.1.2 阶段 4b-2）**：完整单元宏的展开体子树
  （`MacroBody`）挂到 `MacroCall._macro_body`——**不占 children**（`Node.iter_children`
  显式排除）→ 渲染与语义遍历均不进入，**行为面零变化**（全量逐字节不变）。
  `Parser` 新增 `silent` 开关（签名末位，向后兼容）：探测性解析（形态分类 /
  宏体提取）全静默（含失败报告），不污染宿主日志与“真实语料无 WARN”门禁。
  测试加“子树已挂 + 不占 children”断言。剩 4c：渲染改区间/源区间还原。

- **宏渲染走 raw 源区间（0.1.2 阶段 4c，阶段 4 收口）**：`MacroCall` 挂
  `_macro_fragment`（= 源区间切片，与 `_src_span` 对应），渲染声明改为节点直接
  输出该字段——替代“marker 占位 + 事后文本替换”（ADR-0016「渲染直接走源区间」）。
  事后替换**保留为安全网**（对已节点化的 token 锚找不到 marker → 静默跳过；
  未节点化场景仍可救回）。全量 1611 逐字节不变。**阶段 4（管线后端适配）完成**。

- **加工单元实例 + 统一时点生成（0.1.2 阶段 5a）**：新增 `pipeline/units.py`——
  `UnitInstance`（`type`/`impl`/`after|order`/`params` 显式带参数配置品类，
  ADR-0015 §1）+ `parse_units`（fail-fast 校验）+ `assign_points`（**时点由调度器
  统一生成**：order 钉号 / after 推导 / 声明序填空，与 pass 级同构；冲突 / 环 /
  未知引用→诊断）。支持同变换多实例（不同时点/参数）。**纯新增，零执行变化**
  （执行接入 = 5b）。测试 `tests/engine/pipeline/test_units.py`（14 断言，标 smoke）。
  连带：`check_hardcode` TOKEN_ALLOWLIST 加 `impl`（配置字段名，非语言知识）。

- **加工单元声明面（`[pipeline] units`，0.1.2 阶段 5b-1）**：`core/plugin_loader`
  新增 `pipeline.units` 声明加载（项 = `{name, type, impl, after|order, params}`，
  显式 + 带参数；缺 name / 非表 → fail-fast）+ `get_pipeline_units()` 汇总；
  `pipeline/units.py` 新增 `build_unit_sequence`（声明 → 有序单元序列，时点由
  调度器统一生成）。**执行接入（替代 pass 序列）= 5b-2**。

- **单元序列接入调度（0.1.2 阶段 5b-2，粗粒度）**：`schedule.build_unit_schedule`
  把 `[pipeline] units` 声明构建为**可执行单元序列**（`PassDecl`——与 pass 执行层
  同构，直接复用 `_run_schedule` 分派）；`impl` 约定 `builtin.analyze` /
  `builtin.transform` → 内置执行器，其余 → 加载时解析的 handler（check 类）。
  `_ensure_shared` 接入：units 声明存在时**替代默认 schedule 的 pass 序列**
  （统一调度：analyze / transform / check 同列）。**粗粒度限定**：
  `analyze`/`transform` 单元各至多 1 个（内置黑盒执行器不可重复跑），多实例限
  `check` 类——同一变换多时点需细粒度拆解（5b-3）。无声明时走原路径（零回归）。

- **单元执行轨迹（0.1.2 阶段 6 可视化切片）**：`PassState.trace` 逐单元记录
  `{index, name, kind, extra_added, extra_keys}`（谁在哪个时点跑了、向黑板
  `extra` 写了哪些键）→ `ctx.result["trace"]`；`sym_json` 指定时同目录落
  `trace.json`。ADR-0015 §2「时点 = 可视化断点」首项落地（配对隐式，但产物可视）。

- **映射表来源追踪（0.1.2 阶段 6 可视化）**：`resolved_ports` 行携带 `origin`
  （展开链 + 源端口锚点，`spi.slave > invert(spi.master) > #miso`；嵌套叠加
  `nested(实例:类型.角色)`/`rename(实例)`/`opposite(...)` 段）→ SemanticMappingPlugin
  旁路收集 → 插件 `describe()` 自述 → trace 条目 `artifacts`（落 `trace.json`）。
  回答「这行从哪来」；引擎只认协议字段名与自述容器（`TransformPlugin.describe()`
  默认空 = 可选能力），不解析段语义。测试 `tests/languages/verilog/test_mapping_origin.py`。

- **插件身份面 + 插件级单元（0.1.2 阶段 5b-3a）**：插件以限定名注册（引擎插件 =
  类名，语言插件 = `<组件名>.<单元名>`，如 `typed_ports.bridge`）；
  `transform.engine.get_plugin_index()` 查询，索引同名首胜（`_plugin_registry`
  执行序语义不变）。`[pipeline.units.*].impl` 新增第三形态**插件限定名** → 该单元
  只跑该插件（同一变换可多时点）；未知插件 / 非 transform 类型 / `params` 非空
  均 fail-fast。序列限定改为：`analyze` ≤1；`transform` 要么单个
  `builtin.transform`，要么全为插件单元（混用重复执行 → fail-fast）。未声明
  units 的语言包零行为变化。测试 `tests/engine/transform/test_plugin_index.py`、
  `tests/engine/pipeline/test_unit_plugin_schedule.py`。

- **插件契约校验（0.1.2 阶段 7 切片）**：插件注册时声明 `produces` / `requires`
  （显式平铺名列表，**不含时点**——时点归管线配置，ADR-0015 §1/§3 2026-09-11
  作者定调）；调度层在**时点边界**（单元执行前）核验 requires 是否已被前面的
  单元满足 → 未满足 fail-fast（列缺失名 + 当前可用集），通过后并入 produces。
  真实声明：`SemanticMappingPlugin` 产 `mapping_tables`、`ConfigDrivenTransform`
  依赖它、`typed_ports.bridge`/`asm_gen.codegen` 依赖 `scope`；内置执行器契约在
  `_BUILTIN_UNIT_CONTRACTS`。**无声明 = 不校验**（可选、附加）。测试
  `tests/engine/pipeline/test_contract_check.py`。

- **槽位契约声明面（0.1.2 阶段 5b-3c-1）**：`[[transform.slots]]` 从「无人读的
  名字列表」变为**槽位契约声明**——每槽位声明触发节点（`on`）/ 遍历形态
  （`walk` = top|recursive）/ ctx 来源（`ctx`，`$node` = 触发节点）/ 结果接回
  （`result` = extra|none|replace|remove）；**时点不在此声明**（归
  `[pipeline.units.*]`）。加载期 fail-fast：槽位名未注册 / 取值非法 → 报错。
  typed_ports 四个槽位已按此声明（`tpc.toml`），执行仍由 `_bridge.py` 调用
  （遍历/接回的通用执行器见 5b-3c-2）。另：删死槽位 `expand_typed_port`
  （no-op，A1/A3）。测试 `tests/engine/core/test_transform_slot_decls.py`。

- **槽位执行面（0.1.2 阶段 5b-3c-2）**：新增引擎通用槽位执行器
  `transform/slot_runner.py`（限定名 `slot_runner`；契约 `requires=["scope"]` /
  `produces=["slot_transforms"]`）——按 `[[transform.slots]]` 声明机械执行：遍历
  （`walk`）→ 触发（`on`）→ ctx（声明 + 固有通道 `root_scope` +
  `[transform.ctx_channels]` 派生通道）→ 调 handler → 按 `result` 接回
  （extra / none / replace（1:1 替换 + 注释迁移）/ remove）。新配置品类
  `[transform.ctx_channels]`：通道构造声明式（如 `type_map = { symbol_kind =
  "typed_port", attr = "type_name" }`），引擎不认识 kind/attr 语义。
  **typed_ports 桥插件 `_bridge.py` 退役删除**（`handlers = ["_transform.py"]`），
  不留双路径。等价判据：typed_ports 全组 54 + e2e 122（保真/互操作）+ 全量 1678
  全绿。测试 `tests/engine/core/test_transform_slot_decls.py`（含 ctx 通道校验）。

- **槽位级单元（0.1.2 阶段 5b-3c-3）**：槽位可各自声明时点——
  `[[pipeline.units.<name>]] slot = "<槽位名>"`（与 `impl` 互斥）→ 该单元只跑该
  槽位（`SlotRunnerPlugin(only_slot=...)`）；未知槽位 / 非 transform 类型 /
  `slot`·`impl` 并存 → fail-fast。槽位单元的契约沿用承担它的插件（`slot_runner`：
  `requires=["scope"]` / `produces=["slot_transforms"]`）。未声明槽位单元的
  语言包仍走整包槽位执行（现行为零变化）。测试
  `tests/engine/pipeline/test_unit_slot_schedule.py`。

- **修复：模块体首注释被渲染到 `module` 声明之前（渲染层）**：
  `renderer/primitives/join.py` 的"容器首部 Comment 拆段"（ADR-0013 B1.3）
  会把 item `sub_node` 首部 Comment 摘出前置——对 `ModuleDecl` 这类**分段节点**
  （有 head/body/tail）则漂到 head 之前（顶格）。修：拆段只作用于**非分段节点**
  （列表项）；分段节点的 body 首注释归 `render_node` 的 body 段渲染。
  触发条件：模块体**首个元素**是注释。最小复现 12 行（与宏/typed_ports 无关）；
  `ref_spi_inf` 展开路径注释回到 ref 位置（第 11 行）。回归
  `tests/languages/verilog/test_comment_body_head.py`；记录
  `docs/gaps/gap-renderer-comment-fidelity.md`。

- **时点轨迹 HTML 报告（`tpc trace --html`）**：新增 `pipeline/report_html.py`
  （`render_trace_html`）——吃 `ctx.result["trace"]`（ADR-0015 §2 可视化产物），
  渲染单文件 HTML（内联 CSS、零依赖）；与 `tpc check --html` 同一视觉语言
  （`analyzer/report_html.REPORT_CSS` 提为共享常量，单一样式来源）。页面 =
  每单元卡片（时点/`kind` 徽标/`impl`/黑板键）+ **artifacts** 自述
  （槽位调用计数、映射表行来源链）。新增 CLI 子命令 `tpc trace FILE
  [--html OUT] [--json OUT]`。渲染器只做通用值树渲染（不认识具体键名，
  不引入插件知识）。测试 `tests/engine/pipeline/test_trace_report_html.py`。

- **检查精度评测扩面（0.1.2 阶段 8 / T1）**：`eval_check_accuracy` 的 focus
  补入已实现但未入评测的码——inst 族 `W101`/`W102`/`W103`/`WC001`（跨文件）
  与 always 族 `AW001`/`AW002`（默认关，评测显式启用）。样本 26 → **56 case**
  （35 正 / 21 负），recall **100%**（40 期望码全命中）+ FP **0** + parse_err 0。
  顺带修正 `UN001_used_signal` 样本（时序块阻塞赋值 → 非阻塞，避免顺带触发
  新启用的 AW001）。
- **修复：组件 handler 注册面失同步（补注册）**：模块体已 exec 过（`sys.modules`
  缓存不重跑）但注册表被外部清理（测试隔离还原 `/` 热重载）时，`[[transform.slots]]`
  的加载期校验会误报"槽位未注册"。修：校验缺名时**补注册一次**（重新 exec 本组件
  handlers），并把 `register_primitive` 改为**同名同函数幂等**（不同函数仍报冲突）。

- **修复（5b-3c-2 回归）**：`slot_runner` 的 `result = "extra"` 误将 handler
  返回值接回 AST → `build_wrapper` 的 wrapper 模块被内联进主输出
  （`ref_spi_inf` 展开保真 0.43）。现改为**不接回**（额外产物由 handler 侧
  `mark_extra` 自出，同桥时代语义）；补单测锁 `extra` 不重接 / `none` 接回返回值。
  由 0.1.2 阶段 9 真实语料终验（`tests/e2e/run_all_tests.py`）抓到，测试
  `tests/engine/pipeline/test_unit_slot_schedule.py`。

- **检查精度评测扩面（0.1.2 阶段 8 / T1 续）**：NC 族（命名风格）入评测——
  `NC001`-`NC011` 按 kind 合并为 5 个正样例（module/信号/参数/实例/子程序）+
  2 个负样例，样本 56 → **63 case**（40 正 / 23 负），focus 23 → **34 码**，
  recall **100%**（51 期望码全命中）+ FP **0** + parse_err 0。

- **修复：GenvarDecl 符号从未注册（NC008 形同死配置）**：`name_attr` 误配
  `genvar_names.name`——该列表元素是裸 `Identifier` 节点（名字在 `content`，
  无 `name` 字段），`_walk_path` 取不到即丢弃，符号静默不注册，导致 `genvar`
  命名检查永不触发（既有测试只断言“大写合规零诊断”，未覆盖违规检出）。
  修为 `genvar_names.content`；补回归测试 `test_genvar_lowercase_nc008`
  （已回退验证：修复前精准失败）。

- **检查精度评测补全命名族（0.1.2 阶段 8 / T1 完）**：NC014-016（前后缀语义
  约定：方向后缀防接反 / 类型后缀防混淆，handler 判定）入评测——1 正样例 +
  1 负样例，样本 63 → **67 case**（44 正 / 24 负），focus 34 → **37 码**，
  recall **100%**（54 期望码全命中）+ FP **0**。至此全部命名族 NC001-NC016
  均在强检面内。样本用模块内 `reg` 声明而非 ANSI 端口 reg——后者符号 kind 归
  `port`（由 NC005 覆盖），评测描述已注明分界。

- **宏/指令卫生族（MH 族，0.1.2 阶段 8 / T1 完）**：`linter/checkers/macro_hygiene.py`
  在解析前扫**原始源码行**（指令行已被预处理剥离，不进 token 流）——`MH001`
  nettype 指令未复位（对标 svlint `default_nettype_wire_at_end`：文件末尾生效值
  非 `wire` 即报，防跨文件泄漏）、`MH002` 宏以**不同值**重定义未先 `undef`
  （对标 Verilator `REDEFMACRO`：值相同不报）。关键字/前缀/复位值/续行符全部
  来自语言包 `[linter.macro_hygiene]`，未声明该段的语言包（如 c4）不注册检查器
  （零开销零误报）；多行宏体因值不确定不参与比较（保守优先）。linter 准确度
  评测样本 31 正 / 5 负 → **33 正 / 7 负**（负样本锁"已复位"与"同值重定义"
  两个边界），recall 100% + 误报 0。测试
  `tests/engine/linter/test_linter_macro_hygiene.py`（13 项）。

- **规则可达性门禁（门禁体系改进，2026-09-12）**：`tests/policy/test_rule_coverage.py`
  —— 自动枚举"已定义码"（声明式规则表 ∪ 插件 handler 源码的 `code=` 关键字
  实参，**ast 提取**）与"已入样本码"（评测 focus），断言差集为空。动机：
  `NC008` 曾长期是死规则（符号从未注册 → 判定永不触发），而原评测只覆盖
  "正样本能检出 / 负样本不误报"两侧，**不覆盖"某规则根本没进正样本"**。
  门禁上线即暴露两个真实缺口——`TP002`（role+invert 悬空）与 `TP006`
  （invert 自反）已实现但无样本，同批补齐：样本 67 → **69 case**（45 正 /
  24 负），focus 37 → **39 码**（= 全部已定义码）
  + FP 0。门禁自带免疫设计：豁免数上限（照 linter `MAX_KNOWN_MISS` 防滥用
  思路，当前 0）、反向核验（样本码须能找到定义，防拼错后"看着在跑其实
  没测到"）、枚举源非空下限（防提取失效假绿）。
  注：首版用正则提取漏掉单字母前缀码（W101/W201 等 8 个），把"枚举不全"
  误报成样本问题——提取本身也要经得起检验，故改 ast。
- **易漂移数字单一来源化（门禁体系改进）**：样本规模数字（case 总数 / 正负
  样例数 / focus 码数 / 期望码数）不再写死在文档里——由
  `tests/e2e/eval_check_accuracy.sample_stats()` 从 `expected.json` 现算，
  文档只引用来源或改述为定性描述（docstring / TODO 现状段 / ROADMAP 已同步）。
  新增门禁 `tests/policy/test_doc_stats.py`：纳管清单（docstring + TODO 正文，
  跳过 `>` 引用块——按文档纪律引用块不沉淀数字）出现硬编码规模数字即失败。
  门禁自带两向自检：该匹配的必须匹配（防模式失效假绿）、规则码含数字的表述
  不得误报（首版真实发生 `CC001 case 无 default` 被当成 case 总数——误报比
  漏报更伤，会诱发无谓改写进而让人想加豁免）；另校验单一来源自身正确
  （现算值 == 实跑评测统计）。动机：同一轮内 case 数/期望码数在三个文件各写
  一遍，**错了三次**，全靠实测输出发现。

- **增量覆盖率自查（门禁体系改进）**：`tools/check_coverage_delta.py` —— 只统计
  本次改动的引擎源码文件，自动定位其所在包对应的测试目录（找不到才回退 smoke
  层），几十秒给出每文件覆盖率与缺失行；统计范围取自 `pyproject.toml` 的
  `[tool.coverage.run].source`（新增引擎包自动跟上，不硬编码包名）。
  动机：全量 `--cov` 串行 ~32min 只在发布时跑 → 平时新增代码的覆盖率是盲区。
  开发中即验出价值：新写的 MH 检查器在只看 smoke 时是 75.3%（其单测未标
  smoke），跑对应测试目录才是真实的 95.9%。两处细节是实测修正的——coverage
  的 `--cov=` 只认模块名不认文件路径（传路径报 "never imported"）、pyproject
  的全局 `fail_under=80` 会把"只统计改动文件"误判为失败（须显式
  `--cov-fail-under=0`，是否达标改由脚本按文件判定）。默认只报告不失败：
  smoke/局部测试未必走到改动文件的全部路径，硬卡会误伤，要卡用 `--fail-under`。

- **真实语料误报基线（门禁体系改进）**：`tests/e2e/eval_diag_baseline.py` +
  `tests/e2e/samples/real/diag_baseline.json` —— 把真实语料（9 个工程，分组口径
  复用 `eval_benchmark._GROUPS`）上的诊断**按码计条数**固化成基线，新增门禁
  `tests/policy/test_diag_baseline.py` 卡"只许减不许增"。动机：规则默认开/关是
  数据决策，但真实语料的误报面此前只有人工量化、无留痕——规则改动引发的误报
  增长只能靠人偶然发现。基线**不依赖 oracle**（"增长即需解释"与判定对错无关；
  查证哪些是误报仍用 `eval_benchmark.py`，它需外部工具故不进日常门禁）。
  门禁另含两项自洽校验：`total` 必须等于 `counts` 之和（防手改漂移）、基线
  非空（防清空后静默通过）。首个基线：**132 条 / 7 个码**
  （CC001 22 / LC001 25 / UN001 22 / W101 13 / W104 10 / W105 2 / W201 38）。
  代价：全量测试 +约 33s（真实语料必须实跑；smoke 层不含 policy，不受影响）。
  门禁有效性已回退验证：把基线调小模拟增长后，精准报出 `W105: 0 → 2 (+2)`。

- **门禁有效性抽查（门禁体系改进）**：`tools/check_gate_efficacy.py` —— 把"回退
  验证"从手工一次性动作变成清单化抽查。清单里每条变异都**来自真实发生过的事故**
  （NC008 死规则的 `name_attr`、`slot_runner` 的 `extra` 接回、MH002 续行保守、
  误报基线改小），逐条执行：备份 → 施加文本变异 → 跑相关测试 → **期望失败** →
  还原；若测试仍然通过则报错（门禁已失效，或被削弱的测试掩盖了变异）。
  **首轮 4/4 如期变红**。设计要点：锚点找不到就报错而不静默跳过（防抽查慢
  慢变成空转）、要求工作区干净（防还原掩盖未提交改动）、`finally` + 回读校验
  保证还原。不进日常门禁（一轮约一分钟）。

- **文档纠错 + `W101` 根因定位**：先前把"跨文件语料基座"记为"待 elaboration 底座
  （P2.7）"，实际底座（ADR-0008 三层）早已完成于 `3acae77`——`analyzer/checker.py`
  的 `_discover` 已能按实例化链递归发现定义文件（层 1 模块注册表 + 层 2 端口连接
  展开 + 层 3 信号驱动/负载图）。真实缺口是两点：①**入口只有单个**
  （`check(entry_path)`），多文件工程只喂 entry 时同工程其它文件里的模块成为未知
  模块；②定义文件查找按"模块名 ↔ 文件名"匹配。误报基线里 `W101=13`（未知模块）
  即由此而来：语料文件名带 `ref_` 前缀而模块名不带（真实工程通常靠命名约定满足，
  属语料人为偏差）。ROADMAP 与 gap 描述已同步修正。

  **同日实测更正**：上述"`W101` 由文件名不匹配导致"的判断**不成立**。逐条
  打印诊断后，13 条 `W101` 全部来自 `ref_serv_top.v`，报的是 `serv_alu` /
  `serv_csr` 等 SERV 子模块——它们的定义文件**根本不在语料里**，是真未知、
  不是误报。且 `_find_module_file` 早有"同名文件 → 目录内关键字文本扫描"
  **两级**策略，同目录下的文件名不符不成问题（"同目录扫描"本来就已具备）。
  真实缺口只剩：入口曾是单个（已补：`check(paths)` 多入口，跨目录工程需要）、
  以及语料侧缺文件。教训：根因必须落到实测（逐条打印诊断），不能停在
  "看代码猜机制"——本轮因未验证连下了两次错结论。

### Fixed

- **块结束符/模块头行尾注释漂移**（renderer + parser，缺口队列 ④）：语句行尾
  注释能原位渲染，但 `end // c` / `endmodule // c` 被挪到下一行、`module m; // c`
  更漂过 `endmodule` 落到文件末尾（AST 侧本已正确挂上 `_comment_slots`，问题全在
  渲染顺序）：① `render_node` 把 `trailing` 的 LineSuffix 追加在 tail 的
  `tail_break` 空行 break **之后**——LineSuffix 只在下一个换行点前落地，故掉到
  下一行；② 模块头注释挂在 `ModuleDecl.trailing`，而它的 tail 是 `endmodule`，
  且 head 布局自身以 `{ break = true }` 收尾并被 group 包成 `Union`。修法：parser
  在块体解析前把块头那行的 trailing 迁到 `head_trailing`；renderer 把 trailing
  输出在 tail 尾随 break 之前、`head_trailing` 经新增 `_insert_before_trailing_break`
  （Doc 小工具，递归进 `Union` 两支）插到 head 末尾换行点之前。回归
  `tests/engine/parser/test_comment_attachment.py::TestBlockEndTrailing`（3 例，
  **逐行位置敏感**）——e2e 保真度用 `_strip_all` 抹掉空白与换行，对该缺陷天然
  失明，故须单独锁。

- **`delim` 类多字符定界符静默失效**（`lexer/capture_runner.py`）：终止判定原为
  `ch == rule.end` 单字符比较，而配置层只校验"非空字符串"（即声称支持任意长度）
  ——配 `"""` 会永不匹配、静默吞到行尾/EOF（把后续 token 一起吞进字符串）。改为
  按长度比较（与 `marker`/`line_match` 同构）：同起同止多字符（`"""`）与起止
  不同形态（`[[capture]] kind="delim"` + `r#"`/`"#`）均可用。顺带删除
  `lexer/main_lexer.py` 中不可达的"字符串分支" + `_string_delims`（A1 死码；
  清空该集合后 verilog/c4/yaml 三包字符串 token 完全不变，已实测）。回归
  `tests/engine/lexer/test_capture_runner.py`（+4 用例）；全量 1739 passed。

### Changed

- **结构提取底座独立（`analyzer/structure.py`）**：原 `analyzer/checker.py`
  （1375 行）三重职责拆分——结构提取底座（elaboration 三层，33 方法 / 995 行）
  移入 `analyzer/structure.py` 的 `_StructureBase`；`checker.py` 只留检查门面
  （`ProjectChecker(_StructureBase)`，6 方法 / 238 行）。收益：① 语言包
  `[structure] protocol` 的**声明点**随底座迁出，门面不再声明结构协议
  （注册点分离）；② 文件名不再暗示"分析器必然实现检查插件"。外部 API 与行为
  零变化（`from analyzer.checker import ProjectChecker` 全部调用方未动；全量
  1735 passed + 8 skipped）。本轮用继承实现文件级分离，**组合式依赖注入推迟**
  到出现第二个真实消费方时再做。
- **验证体系强化（本版）**：规则覆盖门禁（声明码 vs 采样码，含反向校验）、
  数字单源门禁（文档禁止硬编码样本统计）、真实语料误报基线（只许降不许升）、
  增量覆盖率工具、门禁有效性变异抽查（4/4 期望变红）。

## [0.1.1] - 2026-09-09

注释还原体系闭环（ADR-0013 阶段 B1~B1.5/A2 + ADR-0014）+ typed_ports 语义
检查与清理（T3/invert/resolve_refs 链删除）+ 检查链收尾推进 + 测试 smoke
快速层（217 用例）与并发回归修复。基线：pytest 1575 全绿 / smoke 217 /
real 语料 9 文件 FAIL 0 / lint recall 31/31 零误报。

### Changed

- **删除一次性调试工具 debug_segment_parse.py**（分段解析 + 并树）：仅一次
  picorv32 大文件调试会话使用，无引用/无测试/未进正式管线（"并树"能力从未
  落地），git 历史 4 次提交全为被动清理。删除判据 A1。全项目同类审计（对照
  scaffold 判据：无真实使用/无测试/机制脱节）结论：其余候选均保留——
  run_all_tests（发布门禁，2026-09-09 靠它抓 TP003 误报）/ eval_benchmark
  （oracle 对拍工作流）/ _proto_macro_hygiene（ROADMAP 立项原型）/
  run_differential_svparser（全语料差分扫描，test_real_corpus 覆盖固定语料）。

- **删除 `new component` 脚手架（scaffold_component.py）**：CLI 子命令从未被
  真实组件使用（全部组件手写演进），无测试覆盖，且模板停在已删原语链时代
  （`[analyzer] primitives`），与当前组件协议（postpasses / 声明式 checks）
  脱节。删除判据 A1（无真实使用）+ A5（结构不一致）。连带删 main.py `new`
  子命令、README quick start 示例、pyproject py-modules、
  component_protocol §8 脚手架节。

- **测试分层：smoke 快速回归层 + 全量**：全量测试重（串行 ~32min / 并行
  ~6min），新增 `@pytest.mark.smoke` 分层（pyproject markers 注册）——每组
  功能域挑代表测试（engine 9 子系统 + verilog/c4/yaml + e2e + policy 门禁），
  `python -m pytest -m smoke` 217 用例 ~37s 做日常快速回归；全量留发布/大改后。
  real_corpus 抽 `ref_uart_rx` 做轻量真实语料代表（`_SMOKE_CORPUS` 参数级
  打标，module 缓存只跑 1 次全管线）。组别表与代表维护规约见 tests/README.md。
- **pytest timeout 60→120s，修复并行 worker crash**：并行（`-n auto`）CPU
  争抢使真实语料全管线慢 ~2.5x（tv80 单跑 24s → 并行 60.63s），越过 60s
  阈值触发 pytest-timeout → thread 方法与 xdist worker 交互崩溃
  （`Not properly terminated`；串行无争抢不触发，全量并行曾崩 3 个
  tv80/ice40 断言）。放宽到 120s 留争抢余量。
  验证：smoke 217 绿（37s）+ crash 高发组（real_corpus/real_fidelity/
  check_accuracy/mutation/comment_container）并行 60 passed + 8 skipped 无崩溃。

- **typed_ports resolve_refs 原语链整体移除（P1.5 step 2 A+B）**：role 端口展开
  统一走 postpass 递归（`_expand_ports` → `resolved_ports` → `_apply_entry` 直接
  注入）后，旧"analyze 即时 resolve"双实现链冗余，分两步删净：
  - A（组件内，69948f6）：typed_ports 停用 resolve_refs/flatten_ports/
    attach_invert_map 配置与 handler（删 `_flatten_ports.py`/`_invert_map.py`）、
    `_check`/`_transform` 去 `_ref_callbacks` 回退、删 collect_callbacks 能力与
    resolve_entries 声明
  - B（引擎级，本提交）：删引擎 resolve_refs built-in 原语
    （`analyzer/primitives/_resolve.py`）与其专属工具（`_utils.py` 整体）、
    `_semantic_mapping` 的 apply_refs 后处理链（_run_resolve/_apply_refs/
    _walk_refs/_merge_to_flat）、`_protocol` 冗余常量（ATTR_REF_CALLBACKS +
    3 原语名）、plugin_loader 的 resolve_entries 收集与 pipeline 组装简化
  - 文档同步：component_protocol 语义映射通道节改"已移除"、transform/README、
    引擎注册示例（已删 `_flatten_ports.py`）换真实 `check_name_call`
  验证：引擎专项 346 + 全量 pytest 1567 绿 + policy 双门禁 PASS + pylance 改动
  零诊断。

- **typed_ports invert 嵌套/后置定义修复（TODO P1.5 L2/L3）**：新增组件内
  analyzer postpass `_expand_ports.py`——analyze 遍历结束后（scope 完整）对
  每个 role 从 raw 声明递归展开完整端口集（nested 递归 + invert 取对侧角色），
  写 `sym.attrs["resolved_ports"]`。修复 L2（invert 含嵌套 role 时嵌套端口静默
  缺失——现取对侧角色展开，`inner_*` 方向反转 + 位宽保留）与 L3（invert 目标
  role 后置定义时单趟 DFS 取不到符号漏展开）。下游 `_semantic_mapping`：
  `_apply_entry` 对 attr==ports 且含 resolved_ports 的 role 直接注入扁平行，
  `_walk_refs` 跳过有 resolved_ports 的 role（避开 analyze 旧回调的坏 invert
  数据）。测试样本修正（`wrap.slave` 由混用重复 `spi.slave inner, invert
  master` 改干净 `invert master`，展开不再重 `inner_*`）+ 新增 L3 后置定义
  pos 测试（`test_backward_def_invert_expands`）。验证：typed_ports 相关 36 +
  全量 pytest 1566 绿 + policy 双门禁 PASS。

- **README top type-spi 示例修正（0.1.1 发布准备）**：示例原 `spi.slave
  spi_io` + `impl spi.master => spi_io` 混角色绑定会被 T3 检查（TP012 同角色 /
  TP003）拦为发布反例；改同角色 `spi.master spi_io` + `impl spi.master =>
  spi_io`，展开块方向同步，抽取验证可运行。

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

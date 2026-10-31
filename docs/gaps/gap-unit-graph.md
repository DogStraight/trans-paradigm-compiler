# Gap — unit graph 内置化（块 5）· 调查轮

- 状态：**P1 已实现（2026-10-31，ADR-0027）**——多入口多根森林 + `check` 多入参 + `--json` graph 出口；
  P2/P3 见「不做 / 否掉」表
- 关联：`docs/gaps/gap-engine-abstraction-audit.md` 矩阵 #4（文件链接/入口点）；`ROADMAP.md`「用户侧 CLI 形态」；`PROGRESS.md` 块 5
- 参照：Veryl `sort_filelist`（符号依赖图拓扑序，`docs/references.md:236`）、hdl_checker design-unit + 依赖图/编译序（`docs/references.md:1514`）；**工作链图化调研（2026-10-31）**：`docs/references.md`「依赖/单元图工作链调研」（Verilator V3LinkCells / slang Compilation / GCC -M depfile / hdl_checker 六条共性）
  Doc: docs/gaps/README.md

## 缺口是什么（矩阵 #4 原文）

C 的 `#include` 全链路与 Verilog 的 `module_index` 是**两套索引**，没有统一 unit graph；
linter/报告/CLI 无法消费"文件之间怎么连"。块 5 目标：`unit_graph.v1`——C include 与
Verilog module 同图；`ProjectChecker.check([roots])` 同 API；无语言分支。

## 现状测绘（位置 + 事实）

| 面 | 位置 | 事实 |
|---|---|---|
| V 单元索引 | `analyzer/structure.py` `ModuleIndexer`（L427-526）；协议 `grammar/verilog/base/_structure.toml`（`module_decl_rule`/`module_inst_rule`/`module_keyword`/`file_exts` 全在配置） | 递归发现：实例名 → 定义文件（同名文件优先，再目录文本扫描兜底，按目录缓存 `dir_module_files`）；`module_index` **同名首定义胜**（L431-433）；**只产 name→file 映射，不产边** |
| C include 链 | `preprocessor/primitives/include.py`（`path_forms` L31-56 / `_resolve_path` L82-99 / `handle_include` L122-244） | 解析出 `inc_path` 并内容进流；`_include_stack` 只做循环检测（L146-159），**结束即 discard，不输出被包含文件清单**；缺文件/循环/深度走 `_include_diags` |
| C 侧"单元" | `grammar/c/tpc.toml` **无** `[structure]` | C 的单元 = 翻译单元（root + include 闭包），当前由展开文本隐式表达 |
| 渲染剪枝 | `pipeline/__init__.py` L1357-1379 `_prune_include_regions` | 只影响渲染；分析面照常消费（图化不得改变此条） |
| CLI | `main.py` L534-549 `tpc check <file>` 单值；`ProjectChecker.check()` L105 已接受 list（L148-159 多入口共享索引） | **多入口能力库层已有，CLI 未暴露** |
| 路径默认 | `include.py` L17-25 `_DEFAULT_PATH_FORMS`（C 系约定：`"…"` 相对优先 / `<…>` 仅 search_dirs）；V 在 `grammar/verilog/base/_macro.toml` L114-117 显式声明同形 | 引擎默认 = C 约定（注释自述占位）；图化必须复用同一解析口径，不得另写路径算法 |

## 关键发现

1. **两套索引形态不同**：V 是"名字 → 文件"（定义索引）+ 递归里隐含的实例边；C 是"文件 → 内容"
   （展开进流）。统一图的最小公分母 = **file→file 有向边 + 边种类（include / definition·instance）
   + roots**；语言语义不进图。
2. **C 缺的是"边输出"不是解析**：`inc_path` 已算出（L136-138），只是没记录。新增
   `included_files`/edges 是加字段级改动，但改的是 preprocessor ctx 契约 ⇒ 需 A/B 证明展开文本
   逐字节不变。
3. **V 缺的是"导出"不是发现**：`discover()`（L442-457）已有完整遍历，边可在遍历处顺手产出，
   不重算。
4. **"同 API"库层成立一半**：多入口 list 已支持且共享 `module_index`；块 5 缺图产物 + C 参与 +
   CLI 多入口（CLI 属契约面）。
5. **删除测试视角**：图若无消费者就是摆设——必须至少一个消费点（`tpc check --json` 输出
   `graph`/`edges`，或 `tpc trace`），且删掉消费者后对应测试红。

## 先例调研结论（2026-10-31，详见 `docs/references.md`）

语言专用（Verilator/slang/GCC/hdl_checker）+ **通用工具链**（Bazel/Ninja/SCons/Meson/BSP/Glean）
两轮调研后，对方案 A 的加固：

1. **边生产者注册，不枚举边种类**（SCons Scanner 模型）：`[unit_graph]` 每 kind 只声明
   `source`（preprocessor / structure）、匹配的文件类、搜索路径、递归策略；引擎按注册表调度，
   新增语言 = 加声明，不是加代码分支。
2. **动态边是常态**（Ninja depfile/dyndep）：C include 边在预处理期才完整 ⇒ 必须现算现出；
   缺文件走既有 `on_missing` 策略，不 hard fail。
3. **图 API 三问**（BSP/Meson）：roots / 每 root 的源 / **反查**（某文件被哪些 root 依赖）；
   公共骨架 + 语言 payload（BSP `dataKind`）——与 tpc 配置驱动同构。
4. **roots 显式化**（slang/Verilator/BSP）：P1 只做显式 roots，自动推断后置。
5. **节点身份唯一化**（Ninja 教训）：图内 path 统一 normcase/abspath，且必须与 `include.py`
   现算值一致（判据 3）。
6. **增量层不混进来**（Skyframe/DICE）：块 5 只做静态图，增量属块 7。

## 方案候选

- **A（推荐）**：`analyzer/` 内新增 `unit_graph` 组件（**不设顶层包**，与"推导层留在 linter 内部"
  同一决策）：`UnitGraph(roots, nodes, edges)` + `build(ctx)`，API 对齐「三问」——`roots` /
  `sources(root)` / `inverse(file)`；`[unit_graph]` 是**边生产者注册表**（每 kind：`source =
  "preprocessor" | "structure"`、匹配的文件类、搜索路径、递归策略），V 复用
  `ModuleIndexer.discover` 产 definition/instance 边，C 由 preprocessor 产 include 边；
  `check()` 返回值加 `graph`；P1 消费点 = `tpc check --json`（机器可读出口）+ 报告依赖字段。
- **B（否掉）**：在 analyzer 内把 `ModuleIndexer` 泛化成"通用单元索引"，让 C 也声明 `[structure]`。
  C 没有"单元声明规则"，硬塞 = 把 C 塞进 V 的 module 模型（方言复制/逃生门）；且 include 边在
  preprocessor 里，不在 analyzer。
- **C（否掉）**：不改引擎，CLI 拼 roots 逐个 check（现状）。图不存在，"两语言同图 / 报告消费"
  判据不可达。

## 实现轮判据草案（可执行形态）

1. **图产物（改前红）**：`ProjectChecker.check([...]).graph` 含 `roots/nodes/edges`，且
   `inverse(file)` 能反查到 roots；C（`cJSON.c`）出现 `include → cJSON.h` 边、V（`real_uart*.v`）
   出现 instance/definition 边。改前红 = 现在返回 dict 无 `graph` 键。
2. **无语言分支**：`python tools/lang_penetration.py --dirs analyzer` 与基线比不新增结构名；新声明键
   过 `python tools/config_sites.py check`。
3. **解析口径单一**：C 边路径 == `handle_include` 现算值（探针比对，不得二次解析）；V 边来自
   `discover` 同一遍历（计数器断言 `_dir_module_index` 未被重复调用）。
4. **不变量**：A/B 0/144、`eval_lint_accuracy` 33/0/0、V benchmark 共识 53 不变。
5. **删声明段**（判据②）：删 C `[unit_graph]` ⇒ 相应测试红（声明承重）。
6. **删除测试**：删 `--json` 的 `graph` 字段 ⇒ 对应测试红，否则图无消费者。
7. **性能**：V 7 工程 benchmark ±5% 内；C 单文件 check 新增 <100ms。

## 反例与风险（写进实现轮计划）

- **双算法风险**：builder 自己扫 `#include` 会与 preprocessor 的形态/search_dirs/循环语义漂移 ⇒ 禁止，
  边由 preprocessor 现算现出。
- **渲染剪枝**：`_prune_include_regions` 依赖 `include_regions` 字符区间；图化不得改区间来源，否则
  渲染回归。
- **同名首定义胜**：图化保持 `module_index` 语义，否则诊断/exit code 变化。
- **多入口跨目录**：`check()` 现有语义（L110-114 注释：跨目录工程必须一次 check）不得回退。
- **CLI 契约**：`tpc check <file>` → 多值 `nargs="+"` 属 CLI 契约/退出码面 ⇒ **升级作者拍板**；
  P1 可先只做库 API + `--json` 增字段（不动 CLI 入参）。**已拍板（2026-10-31）：允许多参数**，
  与多入口/多图同轮落地。

## 实现记录（P1，2026-10-31）

- **契约**（ADR-0027）：`check([...])` ⇒ `report["graph"] = {roots, nodes, edges}`；多入口 = 多根
  森林（共享节点去重、`inverse` 可多根）；`UnitGraph.dependencies(root)` / `reachable` / `inverse`；
  CLI `tpc check <file> [<file> ...]`，`--json` 带 `graph`。
- **边来源**（注册能力面）：kind = 引擎 `EDGE_KINDS` 的稳定词（`instantiation` / `include`，
  能力 `unit_graph.edges.v1`）；语言包只在 `[unit_graph] edge_kinds` 声明产出哪些；
  `preprocessor` 新增
  `out_include_edges` 出参，嵌套子扫描的边并入宿主；`StructureCtx.unit_edges` /
  `FileResult.include_edges` 承载。引擎无语言字面量。
- **节点身份**：`normcase(abspath())` 一次定型；自环与重复边在装配时去掉。
- **判据结果**：`tests/engine/analyzer/test_unit_graph.py` 4 passed（C 双根 include 边 / V 实例化边 /
  节点集与去重 / CLI 多参数）；`tests/engine/analyzer` + `tests/engine/preprocessor` **738 passed**；
  A/B **0/144**；benchmark 共识 **53** 不变（53/18/343、parse_fail 0）；`lang_penetration
  --dirs analyzer` 结构名 **0**、Tier A 回基线 6。
- **与预声明的偏差**：① CLI 多入参按作者拍板一并做了（原计划可只做库层）；② `[unit_graph]`
  生产者注册表未做——P1 直接用既有配置数据当 kind，零新增声明面（P2 若要稳定 kind 名再补映射）；
  ③ 止损点未触发（`include.py` 只加了出参，未重构 `scan_directives` ctx 契约）。
- **性能**：benchmark 7 工程 32.6s（此前 45.8s，口径内波动）；C 单文件 check 未见可测增量。


## 预算与止损

- **调查轮**：≤25 探针命令（实际 ~18：结构 / 包含 / CLI / 配置 / 语料各 3-4），产出本档即停。
- **实现轮**：≤4 个生产文件（unit_graph 组件 + checker 接线 + include.py 边输出 + 语言包声明）
  + ≤3 个测试文件；性能口径见判据 7。
- **止损点（预声明）**：若 `include.py` 输出边必须重构 `scan_directives` 的 ctx 契约（超出"加一个
  输出字段"），则本轮只落 V 侧图 + 声明面，C 侧转"触发条件式登记"（触发 = C 真实语料 check 需要
  跨文件图），**块 5 只能报 partial，不标 ✅**。

## 不做 / 否掉

| 不做 | 反证 | 触发条件 |
|---|---|---|
| B 方案（analyzer 内泛化 module 模型给 C） | C 无单元声明规则；include 边不在 analyzer | 永久否掉 |
| C 方案（CLI 逐个 check） | 图不存在 ⇒ 判据 1/6 不可达 | 永久否掉 |
| 图存语言语义（端口/方向） | 违反「语言知识不进代码」；语义归 postpass | 报告需要语义视图时由插件在 postprocess 产出，不进 graph |
| `[unit_graph]` 生产者注册表（每 kind 的匹配文件类/搜索路径/递归策略） | P1 直接用既有配置数据当 kind，已满足消费面 | 出现"kind 名需要跨语言统一 / 消费者按固定名筛选"时补映射 |
| 自动推 roots（slang 式 unreferenced） | P1 只做显式 roots（调查结论 + 作者定"入口先行"） | LSP/无参 `tpc check` 需求出现时 |
| 图之上做增量失效（Skyframe/DICE 式） | 属块 7（增量解析/check） | 块 7 开工 |

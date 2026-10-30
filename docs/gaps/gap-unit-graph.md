# Gap — unit graph 内置化（块 5）· 调查轮

- 状态：**调查完成（2026-10-31）**；实现未开工；方案 A 待实现轮
- 关联：`docs/gaps/gap-engine-abstraction-audit.md` 矩阵 #4（文件链接/入口点）；`ROADMAP.md`「用户侧 CLI 形态」；`PROGRESS.md` 块 5
- 参照：Veryl `sort_filelist`（符号依赖图拓扑序，`docs/references.md:236`）、hdl_checker design-unit + 依赖图/编译序（`docs/references.md:1514`）
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

## 方案候选

- **A（推荐）**：`analyzer/` 内新增 `unit_graph` 组件（**不设顶层包**，与"推导层留在 linter 内部"
  同一决策）：`UnitGraph(roots, nodes, edges)` + `build(ctx)`。边来源由语言包声明
  `[unit_graph]`（`edge_kinds`，每 kind 的 `source = "preprocessor" | "structure"`）；V 复用
  `ModuleIndexer.discover` 产 definition/instance 边，C 由 preprocessor 产 include 边；
  `check()` 返回值加 `graph`；P1 消费点 = `tpc check --json` + 报告依赖字段。
- **B（否掉）**：在 analyzer 内把 `ModuleIndexer` 泛化成"通用单元索引"，让 C 也声明 `[structure]`。
  C 没有"单元声明规则"，硬塞 = 把 C 塞进 V 的 module 模型（方言复制/逃生门）；且 include 边在
  preprocessor 里，不在 analyzer。
- **C（否掉）**：不改引擎，CLI 拼 roots 逐个 check（现状）。图不存在，"两语言同图 / 报告消费"
  判据不可达。

## 实现轮判据草案（可执行形态）

1. **图产物（改前红）**：`ProjectChecker.check([...]).graph` 含 `roots/nodes/edges`；C（`cJSON.c`）
   出现 `include → cJSON.h` 边、V（`real_uart*.v`）出现 instance/definition 边。改前红 = 现在返回
   dict 无 `graph` 键。
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
  P1 可先只做库 API + `--json` 增字段（不动 CLI 入参）。

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

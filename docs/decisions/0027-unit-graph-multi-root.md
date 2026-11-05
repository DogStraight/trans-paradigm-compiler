# ADR-0027: unit graph = 多入口多根森林（文件级）

- Status: accepted
- Date: 2026-10-31

## 背景

块 5：C 的 `#include` 链与 Verilog 的 `module_index` 是两套索引；`tpc check` CLI 只收单文件，
多入口只能走库层 `check([...])`。调查（`docs/gaps/gap-unit-graph.md`）确认：缺的不是功能，是
"文件之间怎么连"的统一出口；抽象取通用工具链的形态（BSP `sources`/`inverseSources`、
SCons Scanner 的边生产者、Ninja 的动态依赖与路径精确匹配）——见
`docs/references.md`「通用工具链的图化抽象」。

## 决策

1. **入口先行**：`ProjectChecker.check(paths)` 把每个 entry 当一个 root；多入口 ⇒ **多根森林**
   （共享节点去重；`inverse` 返回多个 root 是合法结果）。
2. **图产物随 check 返回**：`report["graph"] = {roots, nodes, edges}`；边 = `{kind, source,
   target}`。**kind 词汇归语言包**（语言侧抽象，作者 2026-11-05 裁定）：语言包用
   `[[unit_graph.edges]] kind + from` 声明自己产哪些边、从哪个通道收边；引擎只保留
   **产边通道注册表** `EDGE_CHANNELS`（`structure.unit_edges` / `preprocessor.include_edges`；
   "从哪个阶段收边"是管线编排事实，不是语言知识）。能力面 `unit_graph.edges` **v1 → v2**
   （声明面语义变化）。消费者只把 kind 当标签（`to_dict` / `render_tree` 无按 kind 穷举）。
   Fail-closed：`from` 不在通道表 / kind 重复 / kind 非法命名 / 旧键 `edge_kinds` 均为
   `ConfigError`（报错自解释、不留兼容垫片）；`EDGE_KINDS` 与全局态登记一并删除。
3. **边由阶段产，图只装配**：`ModuleIndexer.discover` 产单元依赖边；preprocessor 的 include
   产包含边（新增 `out_include_edges` 出参，嵌套子扫描的边并入宿主）；`unit_graph` 只做
   规范化/去重/反查。**不做第二遍解析**（Ninja 教训：两套路径口径会静默错）。
4. **节点身份唯一化**：`normcase(abspath())` 一次定型（相对/绝对混用会被当成两个文件）。
5. **CLI 多入参**：`tpc check <file> [<file> ...]`（`nargs="+"`）；`--json` 出口含 `graph`；
   `--tree` 出口为**文本树**（`UnitGraph.render_tree()`，多根森林逐根展开、重复节点标
   `(seen)`，不依赖图形库）。
6. **边界**：图只放 file→file 事实，不放语言语义（端口/方向/精化产物仍归插件 postpass）；
   不引入声明图/BUILD 语；不做增量失效（块 7）。

## 后果

- 正：报告与后续 LSP 有统一依赖出口；**kind 词汇随语言包携带**（加一种边只改包声明）；
  新增语言只需在既有阶段产边，引擎零分支。
- 负：C 的边依赖预处理器实际展开（`expand_macros` 关时不产 include 边）；引擎侧新增
  **通道**才需改引擎（通道表是刻意封闭面），kind 不再需要改引擎。
- 遗留：`[unit_graph]` 生产者注册表（每 kind 的匹配文件类/搜索路径/递归策略）与"自动推
  roots"（slang 式 unreferenced）留 P2；增量（块 7）不碰本图。

## 实现与验证

- Impl：`analyzer/unit_graph.py`（`UnitGraph` + `build_unit_graph` + `EDGE_CHANNELS`）、`analyzer/structure.py`
  （`StructureCtx.unit_edges` / `FileResult.include_edges`）、`analyzer/checker.py`
  （`check()` 返回 `graph`）、`preprocessor/_expand.py` + `preprocessor/primitives/include.py`
  （边出参）、`main.py`（CLI 多入参）。
- Test：`tests/engine/analyzer/test_unit_graph.py`（C 多根 include 边 / V 实例化边 / 节点集 /
  CLI 多参数 / 未注册通道 / 重复 kind / 旧键 / 非法命名 / **临时包 custom_link 不改引擎即出边**）。
- 证据：`tests/engine/analyzer` + `tests/engine/preprocessor` **738 passed**；A/B **0/144**；
  benchmark 共识 **53** 不变（53/18/343，parse_fail 0）；`lang_penetration --dirs analyzer`
  结构名字面量 **0**、Tier A 回到基线 6（新增文件零命中）。

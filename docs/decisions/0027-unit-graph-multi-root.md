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
   target}`。`kind` 是**配置数据**不是引擎字面量：单元依赖边取语言包 `[structure]
   module_inst_rule`；包含边取指令关键字（`[directive_handlers]` 声明）。
3. **边由阶段产，图只装配**：`ModuleIndexer.discover` 产单元依赖边；preprocessor 的 include
   产包含边（新增 `out_include_edges` 出参，嵌套子扫描的边并入宿主）；`unit_graph` 只做
   规范化/去重/反查。**不做第二遍解析**（Ninja 教训：两套路径口径会静默错）。
4. **节点身份唯一化**：`normcase(abspath())` 一次定型（相对/绝对混用会被当成两个文件）。
5. **CLI 多入参**：`tpc check <file> [<file> ...]`（`nargs="+"`）；`--json` 出口含 `graph`。
6. **边界**：图只放 file→file 事实，不放语言语义（端口/方向/精化产物仍归插件 postpass）；
   不引入声明图/BUILD 语；不做增量失效（块 7）。

## 后果

- 正：报告与后续 LSP 有统一依赖出口；新增语言只需在既有阶段产边，引擎零分支。
- 负：C 的边依赖预处理器实际展开（`expand_macros` 关时不产 include 边）；`kind` 目前直接
  用配置词（`ModuleInst` / `include`），消费者按白名单取，P2 再做规范化映射。
- 遗留：`[unit_graph]` 生产者注册表（每 kind 的匹配文件类/搜索路径/递归策略）与"自动推
  roots"（slang 式 unreferenced）留 P2；增量（块 7）不碰本图。

## 实现与验证

- Impl：`analyzer/unit_graph.py`（`UnitGraph` + `build_unit_graph`）、`analyzer/structure.py`
  （`StructureCtx.unit_edges` / `FileResult.include_edges`）、`analyzer/checker.py`
  （`check()` 返回 `graph`）、`preprocessor/_expand.py` + `preprocessor/primitives/include.py`
  （边出参）、`main.py`（CLI 多入参）。
- Test：`tests/engine/analyzer/test_unit_graph.py`（C 多根 include 边 / V 实例化边 / 节点集 /
  CLI 多参数）。
- 证据：`tests/engine/analyzer` + `tests/engine/preprocessor` **738 passed**；A/B **0/144**；
  benchmark 共识 **53** 不变（53/18/343，parse_fail 0）；`lang_penetration --dirs analyzer`
  结构名字面量 **0**、Tier A 回到基线 6（新增文件零命中）。

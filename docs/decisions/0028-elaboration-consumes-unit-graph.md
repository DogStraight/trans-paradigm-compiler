# ADR-0028: 精化基座消费单元图（块 6）

- Status: accepted
- Date: 2026-10-31

## 背景

块 5 落了 `unit_graph`（多入口多根森林），但精化（elaboration）仍直读会话状态：
`StructureAtomSource` 扫 `memo`、`ElaborationService` 按 `memo`/`module_index` 开面、
Verilog 插件 `solve_connections` 还自建 `collect_nodes("ModuleInst")` 索引；同时
T3 审查的接受项 `inst_sites`（postpass 面命名）一直以裸字符串出现（`width_check`、
`inst_check` 各读一处），属"命名未收口"。

## 决策

1. **精化只消费图**：`ProjectChecker.check()` 在发现完成后先建 `UnitGraph`，再跑精化——
   - `UnitGraph` 增 `definitions`（单元名 → 定义文件，`module_index` 的同键视图）；
   - `StructureAtomSource(ctx, graph)`：文件原子 = 图节点、单元原子 = 图定义索引；
   - `ElaborationService(ctx, graph)`：`files()` 按图节点过滤、`unit_file()` 取图定义索引、
     新增 `instantiation_sites(path)`（发现期产物，`FileResult.inst_sites`）。
2. **插件不再自建索引**：Verilog `solve_connections` 改调 `service.instantiation_sites()`
   （删掉本地 `_INST_RULE` / `collect_nodes`）；层 3 的 `files()` 仍走服务面（现由图过滤）。
3. **`inst_sites` 命名收口**：postpass 面改用协议常量 `CTX_INSTANTIATION_SITES`
   （`core/_protocol.py`，值 `instantiation_sites`），引擎注入、`width_check`/`inst_check`
   读取——T3 接受项（"`inst_sites` 命名接受"）关闭，不再以裸字符串作组件间协议。
4. **边界不变**：引擎仍**不消费**精化产物；产物形状与插件语义归属不变；
   `graph` 只放 file→file 事实与定义索引，不放语言语义。

## 后果

- 正：精化输入面收敛到"图 + 服务"，插件零自建索引；postpass 协议键统一、拼写错误可见；
  图不再是 check 的输出摆设，而是精化的真实输入（删除测试：把 `graph` 换成图外文件集，
  精化原子/服务视图随之收缩，见 `test_unit_graph.py::test_elaboration_consumes_graph`）。
- 负：`ElaborationService`/`StructureAtomSource` 多一个可选参数（`graph=None` = 旧直读路径，
  供单测降级）；图节点规范化路径与 `memo` 原始路径需按身份匹配（实现里用 `norm_node` 对齐）。
- 遗留：图目前只承载"文件级"事实；若后续精化需要"跨文件语义原子"（如类型可见性），
  应在 `unit_graph` 加**语言无关边种类**，而不是让插件回到私有索引。

## 实现与验证

- Impl：`analyzer/unit_graph.py`（`definitions`）、`analyzer/elaboration/atoms.py`、
  `analyzer/elaboration/service.py`、`analyzer/checker.py`（先建图后精化）、
  `core/_protocol.py`（`CTX_INSTANTIATION_SITES`）、
  `grammar/verilog/plugins/elaboration/_elaborator.py`、
  `grammar/verilog/plugins/checks/{width_check,inst_check}/`。
- Test：`tests/engine/analyzer/test_unit_graph.py`（含"消费图"删除测试）、
  `tests/engine/analyzer`（364 passed）、`tests/languages/verilog` + `check_accuracy`（406 passed）。
- 证据：A/B **0/144**；verilator benchmark **53**（53/18/343，parse_fail 0）；
  lint accuracy **33/0/0**。

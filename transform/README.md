# transform — AST 变换（配置驱动 + 插件，AST → AST）

> 语义映射 + 变换由 `grammar/` 声明（[transform] 原语/映射表），插件扩展
> （typed_ports 展开 / sim 剥离等），引擎骨架语言无关。

| 文件 | 一句话 |
|------|--------|
| `engine.py` | AstTransformer + TransformPlugin 基类 + 自动注册（注释迁移 `migrate_comments`；插件自述 `describe()`） |
| `slot_runner.py` | 通用槽位执行器（按 `[[transform.slots]]` 声明驱动组件槽位） |
| `config_driven.py` | 配置驱动变换（原语扩展：emit/expand/delete 等） |
| `_semantic_mapping.py` | 语义映射表构建 + 后处理管线 |
| `normalizer.py` | 统一的 AST 规范化层（结构保留） |
| `primitives/` | 变换原语 |

> 变换时注释迁移（旧子树注释随替换结构走）在 `engine.py::migrate_comments`。

## 语义映射机制（怎么拼）

transform 由 SemanticMappingPlugin（`_semantic_mapping.py`）先建语义映射表，
ConfigDrivenTransform（`config_driven.py`）再消费表做 expand/replace/delete。
数据流：analyze 写 `sym.attrs`（黑板）→ 建表（`_apply_entry` 按 source.attr
提取）→ `type_ports_flat` 表（键 `{type}.{role}`）→ transform 消费。

### 建表（SemanticMappingPlugin）

- 组件 .py 模块暴露 `mapping_entries`（表定义：trigger.kind 匹配符号、
  source.attr 从 `sym.attrs` 提取、key 模板、fields 提取子字段）。
- ⚠ **易错**：提供 mapping_entries 的模块（typed_ports `_mapping.py`）无
  @register，但**必须留在 `tpc.toml [analyzer].handlers`**——`plugin_loader`
  `get_component_mapping_config` 从 `info["analyzer"]` 收集 mapping/resolve 表；
  误挪到 `[transform].handlers` 会静默丢表。

### resolved_ports 优先注入（typed_ports 先例）

`_apply_entry` 对 `source.attr=="ports"` 且符号带 `resolved_ports`（组件 postpass
递归展开的完整端口集）→ 直接用它注入扁平行（已是 {direction,name,packed_range}），
跳过 `_process_items` 字段模板提取（那是给 raw 声明结构的）。引擎只做通用判断，
语言语义在组件 postpass。

### resolve_entries / apply_refs —— 已删除（P1.5 step 2 B）

引擎曾提供 `resolve_entries`（`kind=apply_refs`）后处理（消费 `_ref_callbacks`
合并映射表）与 analyzer `resolve_refs` 原语链。typed_ports 迁移到 postpass 递归
展开（resolved_ports → `_apply_entry` 直接注入）后该通道无用户，引擎侧机制随
`analyzer/primitives/_resolve.py`/`_utils.py` 一并移除（不再有 _run_resolve/
_apply_refs）。role 端口展开只走 resolved_ports 路径，别走回头路。

### 消费（ConfigDrivenTransform）

`06_typed_decl` 的 TypedPortDecl 配 `[transform.source] lookup="type_ports_flat"`
`key="{type_spec.type_name}.{type_spec.role_name}"` → expand 时按表展开端口 AST。
行契约 `{direction, name, packed_range}` 是 transform 与下游的稳定面——改表结构
须连带改 config_driven 的 expand 消费与 emit。

### 行来源追踪（0.1.2 阶段 6，可视化管道）

`resolved_ports` 行携带 `origin`（协议字段 `core/_protocol.ROW_ORIGIN`）——
展开链 + 源端口锚点，如 `spi.slave > invert(spi.master) > #miso`；嵌套叠加
`nested(实例:类型.角色)` / `rename(实例)` / `opposite(...)` 段（终点恒为 `#端口名`）。
`_apply_entry` 旁路收集成 `{table: {key: [{name, origin}]}}`（不进表数据），
插件 `describe()` 自述 → 调度层记进 trace 条目的 `artifacts` → dump 模式落
`symbols/trace.json`。回答“_这行从哪来_”（ADR-0015 §2），分流插件复杂后的调试。

- 引擎只认协议字段名与自述容器，不解析段含义（语言知识在组件侧）；
- 新增插件想让中间产物可见 → 覆写 `TransformPlugin.describe()`（默认空 dict
   = 不自述，可选能力）。

### 槽位执行（SlotRunnerPlugin，5b-3c-2）

组件不再写自己的桥插件：槽位的触发/遍历/ctx/接回全由**声明**描述
（`core/component_protocol.md` §3），由引擎 `slot_runner.py` 机械执行：

```
遍历（walk: top|recursive）→ 触发（on: 节点名）→ ctx（声明 + 固有通道 root_scope
+ [transform.ctx_channels] 派生的通道）→ 调 handler → 接回（result: extra|none|
replace（1:1 替换 + 注释迁移）|remove）
```

**语言知识全在声明里**（触发节点名 / 遍历形态 / ctx 来源 / 结果形态 / 通道的
符号 kind 与 attr）；引擎只按名匹配、按声明执行——组件退役了自己的桥
（typed_ports `_bridge.py` 已删）。本插件与声明同源：注册名 `slot_runner`，
契约 `requires=["scope"]` / `produces=["slot_transforms"]`。

### 插件身份面（0.1.2 5b-3a）

插件以**限定名**注册：引擎插件默认取类名（`SemanticMappingPlugin`）、可用语义名
（`slot_runner`）；语言插件用 `<组件名>.<单元名>`（`asm_gen.codegen`）
——管线配置 `[pipeline.units.<name>].impl` 按此名引用，`get_plugin_index()` 查询、
未知名 fail-fast。索引同名**首胜**（同一插件文件被多路径 import 时类对象不同，是
既有常态）；`_plugin_registry`（执行序）语义不变。

声明插件单元后，该单元**只跑该插件**（`AstTransformer(plugins=[...])`）——同一
变换可声明多次（多时点/多实例），每单元在 trace 中独立可见。未声明 units 的语言
包仍走 `builtin.transform`（跑全部插件，现行为零变化）。插件实例化参数覆写
（`params`）尚未实现 → 声明即 fail-fast（不静默忽略）。

### 插件契约（0.1.2 阶段 7，ADR-0015 §3）

插件在**注册时**声明它需要/产出什么（显式平铺名列表，同语法 `production` 列表
风格；引擎只做机械核验，不懂语义；**不含时点**——时点归管线配置）：

```python
@register_plugin(name="asm_gen.codegen", requires=["scope"])
@register_plugin(produces=["mapping_tables"])
@register_plugin(requires=["mapping_tables"])
```

校验点 = **时点边界**（单元执行前，物化即校验）：该单元的 `requires` 必须已被
初始集 ∪ 前面单元声明的 `produces` 覆盖，否则 fail-fast（诊断列出缺失名与当前
可用集）；通过后其 `produces` 并入可用集。**无声明 = 不参与校验**（可选、附加，
粒度作者自选）。内置执行器契约在 `pipeline/schedule.py` 的
`_BUILTIN_UNIT_CONTRACTS`（`builtin.analyze` 产出 `scope`；`builtin.transform`
是黑盒跑全部插件，不声明）。

> 组件协议（tpc.toml 结构/加载链/capabilities）见 `core/component_protocol.md`；
> 从零搭语言的端到端教程见 `docs/language_walkthrough.md`。

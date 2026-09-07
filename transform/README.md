# transform — AST 变换（配置驱动 + 插件，AST → AST）

> 语义映射 + 变换由 `grammar/` 声明（[transform] 原语/映射表），插件扩展
> （typed_ports 展开 / sim 剥离等），引擎骨架语言无关。

| 文件 | 一句话 |
|------|--------|
| `engine.py` | AstTransformer + TransformPlugin 基类 + 自动注册（注释迁移 `migrate_comments`） |
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

### resolve_entries（apply_refs 后处理）——当前无用户

`resolve_entries`（`kind=apply_refs`）驱动 `_run_resolve` 后处理（消费旧
`_ref_callbacks` 合并映射表）。typed_ports 迁移到 resolved_ports 路径后已删
声明——`_resolve_entries` 空则引擎空转无害。机制保留在引擎
（`core/component_protocol.md` `_ref_callbacks` 协议节），未来语言若需
"引用解析→回调"可复用。

### 消费（ConfigDrivenTransform）

`06_typed_decl` 的 TypedPortDecl 配 `[transform.source] lookup="type_ports_flat"`
`key="{type_spec.type_name}.{type_spec.role_name}"` → expand 时按表展开端口 AST。
行契约 `{direction, name, packed_range}` 是 transform 与下游的稳定面——改表结构
须连带改 config_driven 的 expand 消费与 emit。

> 组件协议（tpc.toml 结构/加载链/capabilities）见 `core/component_protocol.md`；
> 从零搭语言的端到端教程见 `docs/language_walkthrough.md`。

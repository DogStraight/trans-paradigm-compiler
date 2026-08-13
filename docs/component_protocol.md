# 组件协议（插件层）

> 文档目的：说明插件层协议——`@register_plugin` / transform 钩子 / analyzer 原语 /
> setup_grammar 组件加载。模型写插件（Python）靠它，避免从既有插件猜协议。
> 来源：2026-08-13 P2.0 文档化。

## 1. 组件 = 语言包扩展单元

组件（component）是"语法文件 + analyzer 处理器 + transform 处理器"的捆绑包，
通过 `<component>/tpc.toml` 声明，挂在语言包的 `[plugins] enabled` 下。

```
grammar/verilog/plugins/
├── typed_ports/
│   ├── tpc.toml          ← 组件元数据（声明语法文件/处理器/原语）
│   ├── 00_type_decl.toml ← 语法规则（注入点 @ModuleItem 等）
│   └── _transform.py     ← Python 处理器（transform 槽位）
├── formatter/
│   └── ...
└── attributes/
```

**tpc.toml 结构**：

```toml
# grammar/verilog/plugins/typed_ports/tpc.toml
[lexer]
token_ext = { file = "_token_ext.toml", required = false }

[grammar]
files = ["00_type_decl.toml", "06_typed_decl.toml", "10_impl_binding.toml"]

[analyzer]
primitives = ["resolve_refs", "flatten_ports", "attach_invert_map"]
handlers = ["_mapping.py", "_flatten_ports.py", "_invert_map.py"]

[transform]
slots = ["delete_type_decl", "build_wrapper", "expand_typed_port", ...]
handlers = ["_transform.py", "_bridge.py"]
```

## 2. 加载流程（setup_grammar）

```
discover_components(plugins_dir)   # 扫描插件目录的 tpc.toml
  → _resolve_dependencies(metas)   # 按依赖排序（meta 里声明 deps）
  → load_component(meta)           # 逐个：
       grammar_files ← [grammar].files 的 .toml
       analyzer     ← [analyzer].handlers 的 .py（import 执行 register_analyzer）
       transform    ← [transform].handlers 的 .py（import 执行 register_plugin）
```

语法文件由 `setup_grammar` 合并进规则树；处理器模块被 import（副作用 = 注册）。

## 3. transform 槽位（@register_transform_slot）

```python
# grammar/verilog/plugins/typed_ports/_transform.py
from core.plugin_loader import register_transform_slot
from core.define import Node

@register_transform_slot("expand_typed_port")
def expand_typed_port(node: Node, ctx) -> Node | None:
    """节点级变换：返回新节点（替换）或 None（删除）或原节点（不动）。"""
    return node
```

- 槽位名在 tpc.toml `[transform].slots` 声明，处理器文件在 `[transform].handlers`。
- 节点级钩子签名：`(node, ctx) -> Node | None`。

## 4. analyzer 原语

```python
# grammar/verilog/plugins/typed_ports/_flatten_ports.py
from analyzer.primitives.registry import register_primitive

def flatten_ports(scope, config):
    ...

register_primitive("flatten_ports", flatten_ports)
```

- 原语名在 tpc.toml `[analyzer].primitives` 声明（执行顺序）。
- 处理器文件在 `[analyzer].handlers`。

## 5. TransformPlugin（注册到 AstTransformer 管线）

```python
# transform/config_driven.py（参考）
from transform.engine import register_plugin, TransformPlugin

@register_plugin
class ConfigDrivenTransform(TransformPlugin):
    """配置驱动变换：读规则 TOML 的 [RuleName.transform] 段执行 expand/emit 等。"""
```

- `@register_plugin` 注册到 AstTransformer 的插件表，`transform` 阶段自动执行。
- 插件经 `AstTransformer.set_shared("rules", ...)` 共享上下文。

## 6. 语法注入（inject）

```
[TypedPortDecl.inject]
targets = ["@AnsiPortDecl", "@ModuleItem"]
```

组件语法通过 `inject` 挂到基础语法的注入点（`@Xxx` 引用位），
`setup_grammar` 把组件规则并入注入点——不修改基础语法文件。

## 7. 数据流（analyzer → transform 通道）

```
TOML grammar rules
      ↓ (setup_grammar 加载)
Parser 产出 AST
      ↓
Analyzer 遍历 AST，执行组件原语
      ↓ (原语写入 sym.attrs，键见 _protocol.py)
SemanticMappingPlugin 读作用域树，构建映射表
      ↓ (表：type_ports_flat 等)
ConfigDrivenTransform 消费映射表
      ↓ (expand / replace / delete 操作)
Renderer 产出格式化输出
```

### `_ref_callbacks` 协议（analyzer ↔ transformer 关键通道）

1. **Analyzer**（`_resolve.py`）：把回调写入 `sym.attrs["_ref_callbacks"]`
2. **Collector**（`_mapping.py`）：`collect_callbacks()` 从作用域树读取
3. **Transformer**（`_semantic_mapping.py`）：从回调构建映射表

所有此类魔数键集中在 `core/_protocol.py` 定义，**禁止在代码里写裸字符串**。

## 8. 脚手架

```bash
python main.py new component my_feature --lang verilog
```

生成 `plugins/my_feature/`（tpc.toml + 00_xxx.toml + _handler.py 骨架）。

## 9. 写新组件的最小步骤

1. `plugins/<name>/tpc.toml`：声明语法文件 + 处理器 + 槽位/原语。
2. `plugins/<name>/00_xxx.toml`：语法规则（`inject` 挂到基础语法）。
3. `plugins/<name>/_handler.py`：Python 处理器（`@register_plugin` / `@register_transform_slot` / `register_primitive`）。
4. 语言包 tpc.toml `[plugins] enabled = ["<name>", ...]` 挂载。
5. `setup_grammar` 自动发现加载；`get_component_grammar_files` 取语法文件。

## 10. 常见坑

| 坑 | 现象 | 修法 |
|---|---|---|
| 处理器模块未 import | 槽位/原语未注册 | `[analyzer].handlers` / `[transform].handlers` 列出 |
| inject target 拼错 | 语法未挂上 | 确认注入点存在（`@Xxx` 引用位） |
| 原语顺序错 | analyzer 阶段顺序乱 | `[analyzer].primitives` 数组顺序 |
| 单语言污染 | 组件跨语言加载 | tpc.toml 声明 `lang` 过滤 |
| 魔数键裸写 | 拼写错难查 | 用 `core/_protocol.py` 常量 |

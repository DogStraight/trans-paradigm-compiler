# 组件协议（插件层）

> 文档目的：说明插件层协议——`@register_plugin` / transform 钩子 / analyzer 原语 /
> setup_grammar 组件加载。插件作者（含模型辅助）写 Python 插件靠它，避免从既有插件猜协议。
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

# 编排调度（ADR-0007）：自定义 pass + 命名 schedule
[[pipeline.pass]]
name = "post_check"
kind = "custom"               # analyze | transform | custom
handler = "_check.py:run"     # custom 必需；签名 fn(state) -> None

[[pipeline.schedule]]
name = "transform_first"      # 调用方 schedule="transform_first" 启用
passes = [
  { name = "transform", order = 1 },
  { name = "analyze" },
  { name = "post_check", after = "transform" },
]
```

## 2. 加载流程（setup_grammar）

```
discover_components(plugins_dir)   # 扫描插件目录的 tpc.toml
  → _resolve_dependencies(metas)   # 按依赖排序（meta 里声明 deps）
  → load_component(meta)           # 逐个：
       grammar_files ← [grammar].files 的 .toml
       analyzer     ← [analyzer].handlers 的 .py（import 执行 @register）
       transform    ← [transform].handlers 的 .py（import 执行 register_plugin）
       pipeline     ← [pipeline] pass/schedule 声明（handler 解析为可调用）
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
from analyzer.primitives.registry import register
from core.define import Node

@register("flatten_ports")
def flatten_ports(analyzer, node: Node, config: dict) -> None:
    """签名固定：analyzer（遍历器）/ node（当前 AST 节点）/ config（规则 analyzer 配置）"""
    self_cfg = config.get("flatten_ports", {})
    ...
```

- 处理器文件在 `[analyzer].handlers`（import 即触发 `@register`）。
- 原语在规则上**按配置键触发**——规则 analyzer 段出现 `原语名 = {...}` 即触发该
  原语并携带配置（键名 = 原语名，一个键同时管触发与配置）：

```toml
# 给主包规则加 analyzer 配置（直接在原文件加字段，无需重声明规则）
[SubroutineCall.analyzer]
check_name_call = { name_attr = "callee" }
```

  （兼容旧写法：`primitives = ["原语名"]` 列表 + 单独配置段，两者合并去重。）

- 内置原语（symbol_declare / scope_enter / scope_exit / identifier_resolve）由固定
  键触发：`symbol` / `scope` / `identifier_ref`。其中 `symbol_declare` 无显式
  `symbol` 时从 `scope` 推断（scope 带 `name_attr` 即视为"声明符号 + 进入作用域"，
  声明规则无需重复写 symbol 配置）。
- 纯 analyzer 插件（只做语义检查、无语法/变换）可只声明 `[analyzer]` 段——组件
  判定已支持（无 `[grammar] files` / `[transform] handlers` 也可加载）。

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

# Renderer 设计方案 — AST + 布局规则驱动的代码生成

## 问题分析

当前后端架构：

```
AST → CG (模板引擎) → 文本 → Formatter (行扫描) → 格式化文本
```

### 核心矛盾

1. **CG 模板硬编码格式**：`\n`、`    `（缩进空格）、逗号/分号位置全部硬编码在 TOML template 里
2. **Formatter 逆向工程**：把 CG 生成的文本重新解析（行扫描/括号深度/正则），猜回结构再重排
3. **互相拉扯**：CG 生成 `if (cond)\n    stmt`，Formatter 又拆了重拼，两遍做同一件事

### 根源
> **风格在 CG 阶段就已经固化成字符串了，Formatter 只能靠猜来还原结构**

---

## 新架构

```
AST → Renderer (AST + 布局规则) → 格式化文本
```

**CG 和 Formatter 合并为一个 Renderer**，直接从 AST 渲染最终文本。

---

## 核心哲学：本质硬编码 vs 偶然硬编码

```
本质硬编码（保留在 Renderer 代码中，DSL 原语）
├── text()     — 插入字面量文本
├── ref()      — 引用子节点，递归渲染
├── join()     — 用分隔符连接多个项目
├── group()    — 组（可能在一行或折行）
├── line()     — 行布局（多个元素水平排列）
├── indent()   — 增加缩进级别
└── opt()      — 条件存在（引用的子节点可能为空）

偶然硬编码（必须配置化，放 TOML）
├── 节点类型名        ModuleDecl, IfStatement, ...
├── 字段名            module_name, condition, then_stmt, ...
├── 关键字字面量      module, endmodule, if, else, reg, ...
├── 列表结构          first/rest 展平、分隔符
└── 特殊语法结构      端口对齐、always 块格式
```

**Renderer 代码只包含 DSL 原语**。所有"这门语言长什么样"的知识都在 TOML 里。

---

## DSL 原语（本质硬编码）

### `text(text)` — 字面量文本

插入一段固定文本，Renderer 自动管理空格。

在 TOML 中简写为字符串：
```toml
"module "
";"
```

### `ref(child_name)` — 子节点引用

引用 AST 节点的某个字段，递归渲染该子节点。

```toml
{ ref = "module_name" }
{ ref = "condition" }
```

### `join(separator, items)` — 列表连接

将多个子项用分隔符连接。

```toml
# 用逗号+空格连接端口列表
{ join = ",", items = "ports" }

# 用逗号连接参数列表
{ join = ",", items = "params" }
```

### `group(children...)` — 组

一组内容，要么在一行内渲染，要么折行渲染。Renderer 根据内容长度自动决策。

```toml
# 可选参数组：(#(params))
{ group = [
    " #(",
    { ref = "params" },
    ")",
] }
```

### `line(children...)` — 行布局

多个元素水平排列。

```toml
# module <name> #(...) (...);
{ line = [
    "module ",
    { ref = "module_name" },
    { opt = { group = [" #(", { ref = "params" }, ")"] } },
    " (",
    { ref = "ports" },
    ");",
] }
```

### `indent(children...)` — 缩进

子内容缩进一级。在 TOML 中通常用于 body 描述：

```toml
body = { indent = true }
```

等价于：
```toml
{ indent = ["@body"] }
```

### `opt(children...)` — 条件组

如果组内引用的子节点不存在，整组跳过。

```toml
# 只在有 params 时才渲染 #(params)
{ opt = { group = [" #(", { ref = "params" }, ")"] } }
```

---

## 布局规则语言（TOML 表示）

### 格式约定

每个 DSL 原语在 TOML 中的表示：

| DSL 原语 | TOML 表示 |
|---------|-----------|
| `text(s)` | `"s"`（字符串）|
| `ref(name)` | `{ ref = "name" }` |
| `join(sep, items)` | `{ join = "sep", items = "field" }` |
| `group(children)` | `{ group = [...] }` |
| `line(children)` | `{ line = [...] }` |
| `indent(children)` | `{ indent = [...] }` 或 `body = { indent = true }` |
| `opt(children)` | `{ opt = [...] }` |

### 块结构：三段式 head + body + tail

对于带 close 关键字的块结构节点：

```toml
[ModuleDecl]
# head: 开口行
head = { line = [
    "module ",
    { ref = "module_name" },
    { opt = { group = [" #(", { join = ",", items = "params" }, ")"] } },
    " (",
    { ref = "ports" },
    ");",
] }
# body: 主体（剩余子节点，每个缩进一级）
body = { indent = true }
# tail: 关闭关键字
tail = "endmodule"
```

渲染效果：
```verilog
module traffic_light (
    input wire clk,
    input wire rst_n,
    output reg [1:0] light
);
    reg [1:0] state;
    always @(posedge clk) begin
        ...
    end
endmodule
```

### 无主体节点：直接用 layout

```toml
[RegDecl]
layout = { line = [
    "reg ",
    { opt = { group = ["[", { ref = "range" }, "]"] } },
    { ref = "reg_name" },
    ";",
] }
```

### 列表节点：用 join

```toml
[PortList]
layout = { join = ",", items = "@body" }
```

### 内联包装节点：用 ref

```toml
[Statement]
layout = { ref = "stmt" }

[ElseChain]
layout = { ref = "branch" }
```

### 完整规则一览

```toml
# ===== 模块 =====
[ModuleDecl]
head = { line = [
    "module ",
    { ref = "module_name" },
    { opt = { group = [" #(", { join = ",", items = "params" }, ")"] } },
    " (",
    { ref = "ports" },
    ");",
] }
body = { indent = true }
tail = "endmodule"

[ParameterList]
layout = { join = ",", items = "@body" }

[ParamDecl]
layout = { line = [
    "parameter ", { ref = "param_name" }, " = ", { ref = "value" },
] }

# ===== 端口 =====
[PortList]
layout = { join = ",", items = "@body" }

[PortDecl]
layout = { line = [
    { ref = "direction" }, " ",
    { opt = { ref = "port_type" } },
    { opt = { group = [" [", { ref = "range" }, "]"] } },
    " ", { ref = "port_name" },
] }

# ===== 声明 =====
[RegDecl]
layout = { line = [
    "reg ",
    { opt = { group = ["[", { ref = "range" }, "]"] } },
    { ref = "reg_name" }, ";",
] }

[WireDecl]
layout = { line = [
    "wire ",
    { opt = { group = ["[", { ref = "range" }, "]"] } },
    { ref = "wire_name" }, ";",
] }

[LocalParamDecl]
layout = { line = [
    "localparam ",
    { join = ",", items = "items" }, ";",
] }

[LocalParamItem]
layout = { line = [
    { ref = "param_name" }, " = ", { ref = "value" },
] }

# ===== 赋值 =====
[BlockingAssign]
layout = { line = [{ ref = "target" }, " = ", { ref = "value" }, ";"] }

[NonBlockingAssign]
layout = { line = [{ ref = "target" }, " <= ", { ref = "value" }, ";"] }

[AssignStatement]
layout = { line = ["assign ", { ref = "target" }, " = ", { ref = "value" }, ";"] }

# ===== 时序 =====
[AlwaysBlock]
layout = { line = ["always @(", { ref = "sensitivity" }, ") ", { ref = "body" }] }

[BeginEnd]
head = "begin"
body = { indent = true }
tail = "end"

# ===== Case =====
[CaseStatement]
head = { line = ["case (", { ref = "expr" }, ")"] }
body = { indent = true }
tail = "endcase"

[CaseItem]
layout = { line = [{ ref = "label" }, ": ", { ref = "body" }] }

# ===== 控制流 =====
[IfStatement]
layout = { line = ["if (", { ref = "condition" }, ") ", { ref = "then_stmt" }] }

[ElseIf]
layout = { line = ["else if (", { ref = "condition" }, ") ", { ref = "body" }] }

[ElseBranch]
layout = { line = ["else ", { ref = "body" }] }

[Statement]
layout = { ref = "stmt" }

[ElseChain]
layout = { ref = "branch" }

[Range]
layout = { line = [{ ref = "msb" }, ":", { ref = "lsb" }] }

[OptType]
layout = { ref = "type_desc" }
```

---

## Renderer 实现

### 核心类

```python
class Renderer:
    """AST → 格式化文本
    只包含 DSL 原语（text/ref/join/group/line/indent/opt），
    所有语言特定知识来自 TOML 布局规则。
    """

    def __init__(self, rules_dir: str):
        self._layouts: dict[str, dict] = {}
        self._load_layouts(rules_dir)

    def render(self, node: Node, indent: int = 0) -> str:
        """入口：渲染 AST 根节点"""
        ...

    def _render_node(self, node: Node, layout: dict, indent: int) -> str:
        """渲染单个节点"""
        ...
```

### DSL 求值器

```python
def _eval(self, expr, node, indent):
    """递归求值一个布局表达式"""

    if isinstance(expr, str):
        # text("...")
        return expr

    if "ref" in expr:
        # ref("child_name")
        child = node.get_attr(expr["ref"])
        if child is None:
            return None
        return self._render_node(child, indent)

    if "join" in expr:
        # join(sep, items)
        items = self._resolve_items(node, expr["items"])
        rendered = [self._render_node(item, indent) for item in items]
        return expr["join"].join(filter(None, rendered))

    if "group" in expr:
        # group(children...) — 尝试一行，太长则折行
        parts = [self._eval(e, node, indent) for e in expr["group"]]
        parts = [p for p in parts if p is not None]
        joined = "".join(parts)
        if len(joined) < self._max_inline:
            return joined
        return ("\n" + self._indent_str * (indent + 1)).join(parts)

    if "line" in expr:
        # line(children...) — 水平排列
        parts = [self._eval(e, node, indent) for e in expr["line"]]
        return "".join(filter(None, parts))

    if "indent" in expr:
        # indent(children...) — 缩进一级
        return self._render_children(node, indent + 1)

    if "opt" in expr:
        result = self._eval(expr["opt"], node, indent)
        return result if result else ""

    return ""
```

### 渲染流程

```python
def _render_node(self, node, layout, indent):
    head = layout.get("head") or layout.get("layout")
    body_cfg = layout.get("body")
    tail = layout.get("tail")

    # 渲染头部
    open_line = self._eval(head, node, indent) if head else ""

    # 渲染主体
    body_lines = []
    if body_cfg:
        body_lines = self._render_children(node, indent + 1)

    # 渲染尾部
    close_line = self._eval(tail, node, indent) if tail else ""

    # 组装
    prefix = self._indent_str * indent
    if body_lines or close_line:
        return (prefix + open_line + "\n" +
                "\n".join(body_lines) + "\n" +
                prefix + close_line)
    else:
        return prefix + open_line
```

### 缩进与辅助方法

```python
class Renderer:
    _INDENT_STR = "    "  # 4 空格

    def _render_children(self, node, indent):
        """渲染所有子节点，每个一行"""
        lines = []
        for child in node.sub_node:
            layout = self._layouts.get(child.name, {})
            r = self._render_node(child, layout, indent)
            if r:
                lines.append(r)
        return lines

    def _resolve_items(self, node, items_spec):
        """解析 items 引用：@body = 所有子节点，否则按字段名取"""
        if items_spec == "@body":
            return node.sub_node
        attr = node.get_attr(items_spec)
        if isinstance(attr, list):
            return attr
        return [attr] if attr else []
```

---

## 与旧系统对比

### 旧模板（偶然/本质硬编码混合）

```
module {{ module_name }}{{#params}}{{?@first}} #(
{{/@first}}    {{.}}{{!@last}},{{/@last}}{{?@last}}
){{/@last}}{{/params}} (
{{#ports}}    {{.}}{{!@last}},{{/@last}}
{{/ports}});
{{#body}}    {{.}}
{{/body}}endmodule
```

**问题**：`\n`、`    `（空格缩进）等格式细节也混在模板中，与语言知识耦合在一起。

### 新布局（分离清晰）

```toml
[ModuleDecl]
head = { line = [
    "module ",                          # 偶然(text)
    { ref = "module_name" },            # 偶然(ref)
    { opt = { group = [                 # 本质(opt/group)
        " #(", { join = ",", items = "params" }, ")"   # 偶然(text/join)
    ] } },
    " (",
    { ref = "ports" },                  # 偶然(ref)
    ");",
] }
body = { indent = true }                # 本质(indent)
tail = "endmodule"                      # 偶然(text)
```

**偶然硬编码 → TOML 配置**
**本质硬编码 → Renderer Python 代码**

---

## 开放问题

### Q1: 列表展平
`PortList` 在 AST 中是 `first` + `rest` 结构。布局规则中如何展平？用 `@body` 引用所有子节点？

### Q2: 端口对齐
```
input  wire [W-1:0] a,
output reg  [W-1:0] sum
```
对齐是纯格式问题，Renderer 是否做后处理对齐？

### Q3: 单行/多行决策
短内容（如 `#(param)`）内联一行，长内容折行。Renderer 根据内容长度自动决策？还是由规则显式指定？

---

## 迁移计划

### Phase 1：Renderer 核心（本质硬编码）
- 创建 `renderer/` 目录
- 实现 `Renderer` 类：`_eval` DSL 解释器
- 实现 text/ref/join/group/line/indent/opt 原语
- 实现布局规则加载器

### Phase 2：Verilog 布局规则（偶然硬编码）
- 为每个 Verilog 节点类型编写 TOML layout 字段
- 布局规则放在语法规则 TOML 中（与 production 同文件）

### Phase 3：集成与清理
- 修改 run_pipeline.py：Renderer 替代 CG + Formatter
- 删除 generator/、旧 formatter/verilog_formatter.py
- 验证所有测试用例输出一致
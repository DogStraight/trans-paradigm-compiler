# Renderer 设计文档 & 当前架构说明

> ⚠️ 本文档描述**当前实现**的架构，不是理想设计。
> 已知问题在末尾「开放问题」中列出。

---

## 架构总览

```
AST → Normalizer → Renderer (Doc IR) → layout() → 格式化文本
```

```
Renderer/
├── renderer.py          # 入口：Renderer.render() → normalize → render → layout
├── doc.py               # Doc IR 类型 + Wadler-Leijen layout 算法
├── loader.py            # TOML 配置加载
├── node_renderer.py     # 节点级三段式渲染 (head/body/tail)
└── primitives/          # DSL 原语求值器
    ├── __init__.py      # eval_expr() 分发
    ├── registry.py      # @register() 装饰器中心
    ├── text.py          # 字面量
    ├── ref_prim.py      # 子节点引用
    ├── join_prim.py     # 列表连接
    ├── group_prim.py    # 组（自动 inline/wrap）
    ├── line_prim.py     # 行布局
    ├── indent_prim.py   # 缩进（当前未在 Verilog 中使用）
    ├── opt_prim.py      # 条件可选
    └── soft_break.py    # 软/硬换行控制
```

---

## 核心哲学：本质硬编码 vs 偶然硬编码

```
本质硬编码（Renderer Python 代码）
├── text()       — 字面量文本
├── ref()        — 子节点引用，递归渲染
├── join()       — 分隔符连接列表
├── group()      — 组（flat 或 broken，自动宽度感知）
├── line()       — 水平排列 + {soft} 换行点
├── indent()     — 增一级缩进
├── opt()        — 条件存在
├── soft/break   — 换行控制

偶然硬编码（TOML 配置）
├── 节点类型名       ModuleDecl, IfStatement, ...
├── 字段名           module_name, condition, then_stmt, ...
├── 关键字字面量     module, endmodule, if, else, reg, ...
├── 列表结构         展平路径、分隔符
└── 特殊语法结构     端口对齐、always 块格式
```

---

## Doc IR（中间表示）

基于 Wadler "A prettier printer" (2003) / Leijen "Wadler-Lindig" 模型。

### 类型

| 类型 | 含义 |
|------|------|
| `Empty` | 无内容 |
| `Text(s)` | 字面量 |
| `Line(i)` | 软换行：flat→空格, broken→换行+k+i |
| `Break(i)` | 硬换行：永远换行+k+i（不被 flatten） |
| `Concat(docs)` | 顺序拼接 |
| `Nest(i, doc)` | 缩进偏移：内部所有 Line/Break 的 k 增加 i |
| `Prefix(i, doc)` | 首行缩进 i + 内部 Nest i（当前几乎已弃用） |
| `Union(flat, broken)` | 二象性：group 创建 Union(flatten(doc), doc) |

### Layout 算法

```python
def layout(doc, width=40) -> str:
    """宽度感知的 Doc → 字符串"""
    return _best(width, 0, doc)

def _best(w, k, doc):
    match doc:
        case Empty():  return ""
        case Text(s):  return s
        case Line(i):  return "\n" + " " * (k + i)
        case Break(i): return "\n" + " " * (k + i)
        case Concat(docs):  return "".join(_best(w, k, d) for d in docs)
        case Nest(i, d):    return _best(w, k + i, d)
        case Prefix(i, d):  return " " * i + _best(w, k + i, d)
        case Union(flat, broken):
            flat_s = _best(w, k, flat)
            first_line = flat_s.split("\n")[0]
            if len(first_line) <= w - k:
                return flat_s
            return _best(w, k, broken)
```

---

## DSL 原语

### `text("string")` — 字面量文本

TOML 简写为字符串。直接对应 `Text(s)`。

```toml
"module "
";"
```

### `ref("child_name")` — 子节点引用

获取 AST 节点的属性，递归渲染。`ref` 调 `_render_inline`，
不额外加缩进 Prefix。

```toml
{ ref = "module_name" }
{ ref = "condition" }
{ ref = "then_stmt" }
```

支持属性路径：`{ ref = "items.name" }`。

### `join(separator, items)` — 列表连接

```toml
{ join = ", ", items = "ports" }
{ join = ",", items = "params", first_soft = true, nest = 1 }
```

`first_soft` 表示第一个元素前加软换行。自动 `group` 包装。

### `group(children...)` — 组

创建 `Union(flatten(doc), doc)`。内容超宽时自动折行。

```toml
{ group = [
    " #(",
    { ref = "params" },
    ")",
] }
```

### `line(children...)` — 行布局

多个元素水平排列。内部的 `{ soft = true }` 为可选的折行点。
整个 line 自动 `group` 包装（当存在 soft 时）。

```toml
{ line = [
    "module ",
    { ref = "module_name" },
    { opt = { group = [" #(", { ref = "params" }, ")"] } },
    { soft = true },
    "(",
    { ref = "ports" },
    ");",
] }
```

### `indent(children...)` — 缩进（当前未使用）

```toml
{ indent = [{ ref = "body" }] }
```

### `opt(children...)` — 条件可选

如果引用的子节点不存在，返回 `Empty()`（而非 None），
避免上层 group 因 None 整体跳过。

```toml
{ opt = { ref = "params" } }
{ opt = { group = [" #(", { ref = "params" }, ")"] } }
```

### `soft` / `break` — 换行控制

```toml
{ soft = true }          # 软换行：flat→空格, broken→换行
{ break = true }         # 硬换行：始终换行
{ break = true, indent = 1 }  # 换行并多缩进一级
```

---

## 三段式渲染 (head / body / tail)

每个节点的 layout 由三部分组成：

```toml
[BeginEnd]
head = "begin"                              # ← 开口
body = { indent = true, source = "body" }   # ← 主体
tail = { text = "end", break = 1 }          # ← 闭合
```

渲染伪代码：

```python
def render_node(node, layout, indent, renderer):
    parts = []
    if head:
        parts.append(eval_expr(head, node, indent))
    if body:
        body_docs = render_body(node, indent + 1, body_cfg)
        for bd in body_docs:
            parts.append(Break(4))          # 换行 + 额外缩进一级
            parts.append(Nest(4, bd))       # 内部 break 继承此深度
    if tail:
        parts.append(Break())               # tail 与 head 同级
        parts.append(tail_doc)
    return Concat(parts)                    # 无 Prefix
```

### 缩进策略（当前方案）

- `render_node` **不**添加 `Prefix(indent*4, doc)`
- body 子项的缩进由父级的 body 渲染段统一控制：
  - `Break(4)` → 换行到 `k+4`
  - `Nest(4, bd)` → 子项内部 break 继承 `k+4`
- tail 用 `Break()`（无额外缩进），与 head 平齐

这样每层 body 恰好向里缩进一级，`end` 与对应 `begin` 对齐。

---

## 原语注册机制

新增原语只需三步：

```python
# 1. primitives/my_prim.py
from .registry import register

@register("my_key")
def eval_my(expr, node, indent, parent_layout, renderer):
    ...
    return SomeDoc()
```

```python
# 2. primitives/__init__.py 加 import
from . import my_prim
```

```python
# 3. 定义 TOML 布局时使用
{ my_key = [...] }
```

无需手动维护 dispatch 表。

---

## 与旧系统对比

### 旧架构 (已废弃)

```
AST → CG (Jinja2 模板) → 文本 → Formatter (行扫描/正则) → 格式化文本
```

问题：CG 生成的文本已经固化了换行和缩进，Formatter 只能靠猜还原结构。

### 当前架构

```
AST → Normalizer → Renderer (Doc IR) → layout() → 文本
```

一次完成，无需二次格式化。

---

## 模块文件结构

```
renderer/
├── __init__.py
├── renderer.py      ~50行  入口，orchestrator
├── doc.py           ~200行 Doc IR 类型 + layout 算法
├── loader.py        ~60行  TOML 加载
├── node_renderer.py ~200行 节点渲染 + body 解析
└── primitives/
    ├── __init__.py   ~40行  分发调度
    ├── registry.py   ~30行  @register 装饰器
    ├── text.py       ~15行  text 原语
    ├── ref_prim.py   ~45行  ref 原语
    ├── join_prim.py  ~60行  join 原语
    ├── group_prim.py ~25行  group 原语
    ├── line_prim.py  ~45行  line 原语
    ├── indent_prim.py~20行  indent 原语
    ├── opt_prim.py   ~30行  opt 原语
    └── soft_break.py ~30行  soft/break 原语
```

---

## 开放问题

### Q1: Prefix 是否应移除

当前 `Prefix` 只在 `node_renderer.py` 的 import 中存在，
实际 `render_node` 已不再使用它。可以考虑完全删除 Prefix 类型。

### Q2: indent 原语未验证

`indent_prim.py` 的 `eval_indent` 目前没有被任何 Verilog 布局使用。
它通过 `Nest(indent * 4, body_docs)` 实现缩进，但这里的 `indent`
是层级数（从 `eval_expr` 传入），`indent * 4` 可能与其他地方的
缩进策略不一致。需要在实际使用时验证。

### Q3: soft_break 的 indent 语义

`{ soft = true, indent = 1 }` 在 `line_prim.py` 中被支持，
但在 `if_statement` 布局中 `{ soft = true }` 的 indent 行为
可能与预期的缩进层级有偏差。break 的 indent 是否应从「额外缩进」
理解为「绝对缩进层级」需要更清晰的定义。

### Q4: render_inline 与 render_node 冗余

两个函数逻辑几乎相同（都不加 Prefix），区别只在于语义。
可以合并为一个参数化的 `_render` 函数。

### Q5: body_cfg 的 indent=true 形同虚设

`{ body = { indent = true, source = "body" } }` 中的 `indent = true`
在 `render_body` 中被忽略（`render_body` 只读取 `source` 和 `items`）。
实际的缩进来自 `_render_node` 中 body 段的 `Break(4) + Nest(4, bd)`。
这个配置字段容易造成误解——应该移除或让它真正控制缩进行为。

### Q6: 行宽上限全局统一

`MAX_INLINE = 40` 是全局的，不能按节点类型设置。
对某些节点可能需要更长的行宽。未来可考虑
在 TOML layout 中增加 `max_inline` 字段覆盖全局设置。
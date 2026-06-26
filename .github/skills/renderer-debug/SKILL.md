---
name: renderer-debug
description: '调试渲染器布局问题：追踪 layout 求值过程、检查 Doc IR 树、分析 flat/broken 选择与 Nest 叠加效应。适用于缩进错位、间距异常、整行压平等渲染问题。'
user-invocable: true
argument-hint: '指定测试用例名，如 array2d'
---

# Renderer Debug — 渲染调试

## 适用场景

- 生成代码缩进错位（过多/过少空格）
- 元素被意外压成一行（group flat 模式）
- 元素意外跨行（SoftLine 被展平为空格）
- 注释与声明合并到同一行
- 端口/参数列表格式异常

## 使用方法

```bash
# 渲染布局追踪
python .github/skills/renderer-debug/scripts/trace_render.py <test_name>

# 查看完整 Doc IR 树（显示 Union/flat/broken 分支）
python .github/skills/renderer-debug/scripts/trace_render.py <test_name> --show-doc

# 只关注某个节点类型的渲染路径
python .github/skills/renderer-debug/scripts/trace_render.py <test_name> --node NamedPortList
```

## 渲染管线

```
归一化 AST → layout 配置 → Layout IR (Doc) → layout() 算法 → 字符串
                    ↑                          ↑
             head/body/tail             flat/broken 选择
```

## 核心原语速查

### Text — 字面文本
```
{ line = ["module ", { ref = "module_name" }, ";"] }
→ Text("module ") + Text(name) + Text(";")
```

### SoftLine — 软换行
```
{ soft = true }
→ Line()        flat: 空格     broken: 换行
```

### Break — 硬换行
```
{ break = true }
→ Break()       flat: 换行     broken: 换行（始终换行）
```

### group — 二象性选择
```
{ group = [ ... ] }
→ Union(flat=压平版本, broken=原始版本)
  layout() 优先尝试 flat，首行超宽则回退 broken
```

### line — 行布局
```
{ line = [ ... ] }
→ 逐个求值子元素，如果包含 { soft } 或 { break } 则自动包裹 group
```

### join — 连接
```
{ join = ", ", items = "ports" }
→ 元素间插入 Text(", ") + SoftLine()
  注意：默认包裹 group()，SoftLine 可能被展平
```

### Nest — 缩进
```
{ nest = 1 }
→ 对内部所有换行增加 4 格缩进（可叠加）
```

## 常见问题排查

### 1. 元素被意外压成一行

**表现**: `array2d_test( )`、`mem2d[0:3] [0:7]`

**排查**:
1. 查看对应节点的 `layout` 配置是否包含 `group`
2. `group` 的 flat 版本首行长度是否 ≤ `max_inline(40)`
3. `join` 的 `SoftLine` 是否被 group 展平为空格

**修复**:
- 用 `Break` 替代 `SoftLine`（如 `{ break = true }`）
- 对无内容时的多余空格，在 `opt` 中加 `ref` 条件判断

### 2. 缩进错位/叠加

**表现**: 第二行比第一行多 8 空格

**排查**:
1. 父级 `body.indent = true` 提供 4 格缩进
2. 子级 `join.nest = 2` 提供 8 格缩进
3. 两者叠加 → 12 格

**修复**: 调整 `nest` 值或移除父级/子级中的一层

### 3. `)` 不在独立行

**表现**: `output wire co);` 应为 `output wire co\n);`

**排查**:
1. 检查 `)` 是否在 `head` 的 `line` / `group` 内
2. `{ soft = true }` 在 flat 模式被展平为空格
3. 改用 `{ break = true }` 强制换行

### 4. 注释行与下行合并

**表现**: `// comment\nmodule` → `// comment module`

**排查**:
1. `Root.layout.join = "\n"` 中的 `"\n".rstrip()` 会返回空字符串
2. 空分隔符导致 `SoftLine` 在 group flat 模式被展平

**修复**: `eval_join` 中分隔符为 `\n` 时用 `Break` 且不 group

### 5. `);` 后缺少空白行

**表现**: `endmodule` 紧贴上一行

**排查**: 检查 `tail.break` 值

**修复**: 增大 `break` 值或在 `head` 末尾添加 `{ break = true }`

## 布局配置参考

### head/layout

```toml
# 纯文本
head = "endmodule"

# 引用属性
head = { ref = "value" }

# 行布局（水平排列）
head = { line = ["module ", { ref = "module_name" }, ";"] }

# 连接列表
head = { join = ", ", items = "ports" }
```

### body

```toml
# 缩进 + 子节点
body = { indent = true, source = "body" }

# 具名字段
body = { indent = true, items = ["then_stmt", "else_chain"] }

# 展平块
body = { indent = true, role = "flatten" }
```

### tail

```toml
# 纯文本
tail = { text = "endmodule", break = 2 }

# 包裹引用
tail = "end"
```

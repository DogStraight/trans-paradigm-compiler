# Renderer Layout DSL 原语与空格规则

## DSL 原语速查

| 原语 | TOML 写法 | 行为 |
|------|-----------|------|
| `text(s)` | `"literal"` | 直接输出文本 |
| `ref(name)` | `{ ref = "attr" }` | 取节点属性递归渲染 |
| `opt(inner)` | `{ opt = { ... } }` | 属性缺失时整体消失 |
| `group(inner)` | `{ group = [...] }` | 可选折行组（宽度不够时整体换行） |
| `line([...])` | `{ line = [...] }` | 顺序拼接，无自动空格，不折行 |
| `soft` | `{ soft = true }` | 软换行提示（group 折行时生效；可带 `indent`） |
| `join(sep, items)` | `{ join = ", ", items = "field" }` | 分隔符拼接列表（**保留形态**：`\n` 块级 / `no_soft` 硬拼 / `""` 拼接） |
| `intent` | `{ intent = "compact", items = "field" }` | 布局意图（ADR-0006 阶段 4a）：`compact` = 可折行列表（列表布局首选，等价 `join+first_soft+nest` 手拼四件套） |

> `nest` / `first_soft` 不是独立原语，是 `join`/`intent` 的列表参数：
> `{ join = ", ", items = "x", nest = 1 }`（折行后缩进级，单位 `_INDENT_STR`）、
> `{ join = ", ", items = "x", first_soft = true }`（首项前软换行）。
> 完整 14 原语目录（含 break/align/fill/indent/line_suffix/suffix_when…）见
> `docs/renderer_architecture.md`。

## 核心原则

`line` 中的元素**直接拼接，无自动空格**。空格必须显式写出。

## 标准模式（端口/声明类）

```toml
layout = { line = [
    "keyword",               # ← 纯文本，无尾部空格
    " ",                     # ← 显式空格（如果下一个元素必有）
    { ref = "some_attr" },   # ← 引用属性
    " ",                     # ← 下一个分隔空格
    { ref = "another_attr" },
] }
```

## opt + group 中的空格

空格写在 opt group 的**开头**，接在**前一个元素**后面：

```toml
# ✅ 正确
layout = { line = [
    "input",
    { opt = { group = [
        " ",                     # 空格在 group 开头
        { ref = "port_type" },   # → " reg"
    ] } },
    " ",
    { ref = "items" },           # → "input reg clk"
] }

# ❌ 错误："input " 尾部空格 + group 开头 " " = 双空格
layout = { line = [
    "input ",                    # 尾部空格！
    { opt = { group = [
        " ",                     # 开头空格！
        { ref = "port_type" },
    ] } },
    { ref = "items" },           # → "input  regclk"（双空格+缺空格）
] }
```

## 范围/下标括号

```toml
# ✅ 正确
layout = { line = [
    "input",
    { opt = { group = [
        " [",                    # 空格在左括号前
        { ref = "packed_range" },
        "]",                     # 右括号无尾部空格
    ] } },
    " ",                         # 专用空格元素
    { ref = "items" },           # → "input [7:0] clk"
] }

# ❌ 错误
layout = { line = [
    "input ",
    { opt = { group = [
        "[",                     # 缺前导空格！
        { ref = "packed_range" },
        "] ",                    # 尾部空格！
    ] } },
    { ref = "items" },           # → "input [7:0]clk"
] }
```

## 分号

```toml
# ✅ 正确：用前面的空格元素隔离
    " ",
    { ref = "items" },
    ";",                         # → " clk;"

# ✅ 也正确：直接跟在 ref 后
    { ref = "items" },
    ";",                         # → "clk;"
```

## 检查清单

修改 layout 后对照检查：

- [ ] 方向/关键字文本（`"input"`, `"output"`）无尾部空格
- [ ] 相邻元素间有显式 `" "` 分隔
- [ ] opt group 内的空格写在开头（`" "`），不是结尾
- [ ] 括号前有空格（`" ["` 而非 `"["`）
- [ ] 括号后无空格（`"]"` 而非 `"] "`）
- [ ] `{ ref = "items" }` 或 `{ ref = "port_name" }` 前有 `" "`
- [ ] 同族规则（AnsiInputDecl / BodyInputDecl 等）保持一致的 layout 结构

## 快速验证

```powershell
# 回归门禁：空格/折行断言在渲染测试 + e2e ref 对比内
python -m pytest tests/engine/renderer/ tests/languages/verilog/ -q
python tests/e2e/run_all_tests.py            # e2e 全量 ref 对比（FAIL 0）

# 肉眼检查：渲染含端口声明的样例并落盘（samples/<group>/gen/）
python tests/e2e/run_pipeline.py ref_simple
Get-Content tests/e2e/samples/normal/gen/gen_simple.v
# 查方向/括号前空格：`input [7:0] a` 而非 `input[7:0]a` / 双空格粘连
```

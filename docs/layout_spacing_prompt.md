# Renderer Layout DSL 原语与空格规则

## DSL 原语速查

| 原语 | TOML 写法 | 行为 |
|------|-----------|------|
| `text(s)` | `"literal"` | 直接输出文本 |
| `ref(name)` | `{ ref = "attr" }` | 取节点属性递归渲染 |
| `opt(inner)` | `{ opt = { ... } }` | 属性缺失时整体消失 |
| `group(inner)` | `{ group = [...] }` | 可选折行组（宽度不够时整体换行） |
| `line([...])` | `{ line = [...] }` | 顺序拼接，无自动空格，不折行 |
| `join(sep, items)` | `{ join = ", ", items = "field" }` | 用分隔符连接列表 |
| `soft` | `{ soft = true }` | 软换行提示（group 折行时生效） |
| `nest(n)` | `{ nest = 1 }` | 换行后增加缩进（单位：`_INDENT_STR`） |
| `first_soft` | `{ first_soft = true }` | join 首项前加软换行 |

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
# 跑一个涉及端口声明的用例
python .\verilog\run_pipeline.py ref_counter
# 检查 output 中的空格：`input wire clk` 而非 `input  wireclk`
Get-Content .\verilog\gen\gen_counter.v
```

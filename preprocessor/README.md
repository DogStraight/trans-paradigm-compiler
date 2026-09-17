# preprocessor — 宏展开 / 反向映射

> TOML 驱动的宏展开（`` `NAME ``、指令）与反向（渲染后把展开还原回宏调用），
> 语言无关。位置桥 = 锚 + 原文（source_text）消耗式回插。
> 锚形态两态（`mode`）：`line`（行首空体宏，整行占位）/ `inline`（行内空体宏，
> marker 占位）；未知 mode → fail-fast。非空体宏不建还原锚，宏体文本铺进流，
> 还原走宏区间 + 渲染 raw 拼接（`_macro_source_text`）。

## marker 的书写形态（声明驱动）

占位 marker（`tpc:<kind>:<seq>`）必须**以注释形态**穿过管线（parser 当 trivia
跳过、渲染端保留注释），所以它的书写标点 = **语言的**注释标点，全部从语言包
声明取（`[comment] pairs` / `[[capture]]`）：

- 读取点：`lexer/comment_syntax.py`（`CommentSyntax`：行注释起始 + 成对定界符）；
- 书写/识别约定：`_markers.py`（整行形态 `line_marker` / 行内形态 `inline_marker`）；
- 两种形态：**整行**（行注释独占一行：条件块占位 / 整行宏锚 / 指令行占位）与
  **行内**（块注释：空体宏锚）。

引擎不认识 `//` / `/* */`（yaml 是 `#`，c4 只有行注释且有两种）——语言包未声明
所需形态而该形态又被需要 → fail-fast（不静默降级）。

## 形态清单（哪些是声明列表、哪些是引擎机制）

**语言知识 → 语言包声明（列表形态）**：

| 形态 | 声明位置 | 消费点 |
|------|----------|--------|
| 注释标点（行注释起始 / 成对定界符） | `[comment] pairs` / `[[capture]]` | `lexer/comment_syntax.py` → `_markers.py`、`analyzer/suppress.py` |
| 宏形态（`shape` 生产式：前缀 token 名 + 名字位；段候选列表枚举） | `[macro_recognition]`（`shape` / `directive` / `call`） | `macro_shape.py`（声明解析）→ `lexer` 宏 token 扫描、`_expand.py`（文本层展开） |
| 带参宏实参形态（调用括号对 + 实参槽 + 分隔符；定义侧与调用侧同形） | `[macro_recognition]`（`call_args` / `arg_separator`） | `macro_shape.py`（声明解析 + 配平/切分）→ `_expand.py`（调用侧）、`primitives/define.py`（形参表） |
| 数字形态（位宽字面量等） | `[[number.based]]` | `lexer/number_gen.py` |
| 括号对 / 逗号等标点 | `[bracket] pairs` / `[symbol.*]` | lexer / parser / linter |

**引擎机制 → 不进语言包**（形态确定之后的"怎么替换/怎么还原"）：三种处置机制
（`splice` / `line` / `inline`）与其执行；**选哪一种由语言包策略决定**
（见下节「宏处置策略」）；注释形态的可用性由声明**推导**（有行注释 → 整行形态
可用；有块注释 → 行内形态可用）。

## 宏处置策略（插件能力）

引擎只做**文本操作**（替换 / 锚书写 / 还原 / 区间与行映射）；"这个宏调用该怎么
处置"是**语言知识** → 语言包通过 `[capabilities] macro_policy = "file.py:fn"`
声明策略（与 formatter 同款，见 `core/component_protocol.md`）：

- 引擎给**通用文本事实**（调用点上下文，`preprocessor/_expand.py::_call_site`）：
  名字 / 宏体 / 是否带参 / 行号与行内起止列 / 行内前后文 / 是否行首行尾 /
  是否独占该行；
- 策略返回**处置枚举**（引擎机制面，与铺条目 `mode` 同词）：
  `splice`（宏体铺进流 + 宏区间）/ `line`（整行占位）/ `inline`（行内注释锚）；
- 未声明能力 → 默认 `splice`；方案非法（mode 未知 / `line` 用于同行多调用）
  → fail-fast（不静默降级）；
- 查找按 **rules_dir** 作用域（`core/plugin_loader.py::get_capability_in`）：
  只有该语言包 `plugins/` 下的组件才有资格应答，同进程切语言不串用。

verilog 的判定表见 `grammar/verilog/plugins/macro_policy/README.md`。
**尚未迁出的引擎侧语言知识**（ROADMAP P3.6 剩余项）：宏调用后随位宽字面量后缀
（`_expand.py::_LITERAL_SUFFIX_RE` 与 `[[number.based]]` 是同一知识的两处表达）。

| 文件 | 一句话 |
|------|--------|
| `_expand.py` | 宏展开（strip 指令 + `` `NAME `` 引用展开）+ 指令扫描的注释跨度 |
| `macro_shape.py` | 宏形态声明读取（`[macro_recognition]` 生产式解析：前缀 token 文本 + 名字候选 + 实参形态） |
| `_reverse.py` | 宏反向（统一位置桥：锚 + 原文回插） |
| `_bridge.py` | 统一位置桥（Anchor Bridge）——锚 + 原文消耗式回插引擎 |
| `_markers.py` | tpc marker 书写/识别（注释形态声明驱动） |
| `primitives/` | 指令处理原语（define/ifdef/include/undef 等） |

> 入口：`_expand.py`（展开）/ `_reverse.py`（反向）；宏还原门禁见
> `tests/e2e/`（test_comment_restore / 宏还原）。

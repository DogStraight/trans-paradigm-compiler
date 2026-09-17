# preprocessor — 宏展开 / 反向映射

> TOML 驱动的宏展开（`` `NAME ``、指令）与反向（渲染后把展开还原回宏调用），
> 语言无关。位置桥 = 锚 + 原文（source_text）消耗式回插。
> 锚形态三态（`mode`）：`line`（行首空体宏，整行占位）/ `inline`（行内空体宏、
> `=` 后缀宏，marker+body 区间）/ `token`（非空体宏，唯一 token 锚）；未知 mode →
> fail-fast。非空体宏在**语义展开**路径下不建还原锚，改走宏区间 + 渲染 raw 拼接
> （`_macro_source_text`）。

## marker 的书写形态（声明驱动）

占位 marker（`tpc:<kind>:<seq>`）必须**以注释形态**穿过管线（parser 当 trivia
跳过、渲染端保留注释），所以它的书写标点 = **语言的**注释标点，全部从语言包
声明取（`[comment] pairs` / `[[capture]]`）：

- 读取点：`lexer/comment_syntax.py`（`CommentSyntax`：行注释起始 + 成对定界符）；
- 书写/识别约定：`_markers.py`（整行形态 `line_marker` / 行内形态 `inline_marker`）；
- 两种形态：**整行**（行注释独占一行：条件块占位 / 整行宏锚 / 指令行占位）与
  **行内**（块注释：空体宏锚 / `=` 后缀宏锚）。

引擎不认识 `//` / `/* */`（yaml 是 `#`，c4 只有行注释且有两种）——语言包未声明
所需形态而该形态又被需要 → fail-fast（不静默降级）。

## 形态清单（哪些是声明列表、哪些是引擎机制）

**语言知识 → 语言包声明（列表形态）**：

| 形态 | 声明位置 | 消费点 |
|------|----------|--------|
| 注释标点（行注释起始 / 成对定界符） | `[comment] pairs` / `[[capture]]` | `lexer/comment_syntax.py` → `_markers.py`、`analyzer/suppress.py` |
| 宏 token 识别（前缀/后缀策略） | `[macro_recognition]` | `lexer` 宏 token 扫描 |
| 宏体形态（赋值后缀前导集） | `[macro_shape]`（`suffix_leads`） | `macro_shape.py`（声明读取）、`_expand.py`（锚形态选择） |
| 数字形态（位宽字面量等） | `[[number.based]]` | `lexer/number_gen.py` |
| 括号对 / 逗号等标点 | `[bracket] pairs` / `[symbol.*]` | lexer / parser / linter |

**引擎机制 → 不进语言包**（形态确定之后的"怎么替换/怎么还原"）：锚三形态
（`line` / `inline` / `token`）与语义展开路径的选择；注释形态的可用性由声明
**推导**（有行注释 → 整行形态可用；有块注释 → 行内形态可用）。

| 文件 | 一句话 |
|------|--------|
| `_expand.py` | 宏展开（strip 指令 + `` `NAME `` 引用展开）+ 指令扫描的注释跨度 |
| `macro_shape.py` | 宏体形态声明的读取点（`[macro_shape] suffix_leads`：赋值后缀宏体的锚形态依据） |
| `_reverse.py` | 宏反向（统一位置桥：锚 + 原文回插） |
| `_bridge.py` | 统一位置桥（Anchor Bridge）——锚 + 原文消耗式回插引擎 |
| `_markers.py` | tpc marker 书写/识别（注释形态声明驱动） |
| `primitives/` | 指令处理原语（define/ifdef/include/undef 等） |

> 入口：`_expand.py`（展开）/ `_reverse.py`（反向）；宏还原门禁见
> `tests/e2e/`（test_comment_restore / 宏还原）。

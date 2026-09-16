# preprocessor — 宏展开 / 反向映射

> TOML 驱动的宏展开（`` `NAME ``、指令）与反向（渲染后把展开还原回宏调用），
> 语言无关。位置桥 = 锚 + 原文（source_text）消耗式回插。
> 锚形态三态（`mode`）：`line`（行首空体宏，整行占位）/ `inline`（行内空体宏、
> `=` 后缀宏，marker+body 区间）/ `token`（非空体宏，唯一 token 锚）；未知 mode →
> fail-fast。非空体宏在**语义展开**路径下不建还原锚，改走宏区间 + 渲染 raw 拼接
> （`_macro_source_text`）。

| 文件 | 一句话 |
|------|--------|
| `_expand.py` | 宏展开（strip 指令 + `` `NAME `` 引用展开） |
| `macro_shape.py` | 宏体形态分类（包装解析：完整单元 vs 残缺片段） |
| `_reverse.py` | 宏反向（统一位置桥：锚 + 原文回插） |
| `_bridge.py` | 统一位置桥（Anchor Bridge）——锚 + 原文消耗式回插引擎 |
| `primitives/` | 指令处理原语（define/ifdef/include/undef 等） |

> 入口：`_expand.py`（展开）/ `_reverse.py`（反向）；宏还原门禁见
> `tests/e2e/`（test_comment_restore / 宏还原）。

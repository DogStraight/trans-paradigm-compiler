# preprocessor — 宏展开 / 反向映射

> TOML 驱动的宏展开（`` `NAME ``、指令）与反向（渲染后把展开还原回宏调用），
> 语言无关。位置桥 = 锚 + 残片消耗式回插。

| 文件 | 一句话 |
|------|--------|
| `_expand.py` | 宏展开（strip 指令 + `` `NAME `` 引用展开） |
| `macro_shape.py` | 宏体形态分类（包装解析：完整单元 vs 残缺片段） |
| `_reverse.py` | 宏反向（统一位置桥：锚 + 残片回插） |
| `_bridge.py` | 统一位置桥（Anchor Bridge）——锚 + 残片消耗式回插引擎 |
| `primitives/` | 指令处理原语（define/ifdef/include/undef 等） |

> 入口：`_expand.py`（展开）/ `_reverse.py`（反向）；宏还原门禁见
> `tests/e2e/`（test_comment_restore / 宏还原）。

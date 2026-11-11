"""first_set.py — linter 侧的 FIRST 调用口径（**实现在 `core/first_set.py`**）。

历史：同一事实曾有两份实现（`grammar_slicer` 的保守版 = 强制起始；`matcher` 的可空
传播版 = 可能起始），语义不同却都叫 first，且 matcher 的 docstring 说"必然"而实现对
optional 按"可能"处理（自相矛盾）。D10 尾项（作者 2026-11-09 批准）把实现**下沉到
`core/first_set.py`** 单一实现；本模块只保留 import 面，`grammar_slicer` / `matcher`
的 import 路径不变。

两种口径由 `nullable` 开关表达（详见 `core/first_set.py` 模块 docstring）：

  nullable=False  强制起始（保守）：optional 视为空集；seq 只看首元素；
                  call 不越过可空前缀。用于**前缀判别**（lookahead/slicer）。
  nullable=True   可能起始：optional/repeat 下钻；seq 按可空前缀传播；
                  call 在首元素可空时并入后续元素。用于**候选筛选**（matcher）。

两者都不是"错"的——错的是让它们各自长大且互不知情。
Doc: linter/linter_architecture.md（前瞻消歧 / 匹配器 first 口径）
"""
from __future__ import annotations

from core.first_set import first_tokens

__all__ = ["first_tokens"]

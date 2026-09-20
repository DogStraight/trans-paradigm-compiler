"""flow.py — 流程控制原语

foreach    遍历列表，对每个元素执行 callback
make_exists_condition  创建'属性存在'条件谓词
Doc: docs/language_walkthrough.md（流程控制变换原语）
"""

from typing import Any, Callable


def foreach(
    items: list[Any],
    as_name: str,
    callback: Callable[[Any, dict[str, Any]], Any],
    outer_context: dict[str, Any],
) -> list[Any]:
    """遍历列表，对每个元素执行 callback"""
    results: list[Any] = []
    for item in items:
        item_ctx = dict(outer_context)
        item_ctx[as_name] = item
        result = callback(item, item_ctx)
        if isinstance(result, list):
            results.extend(result)
        elif result is not None:
            results.append(result)
    return results


def make_exists_condition(path: str) -> Callable[[dict[str, Any]], bool]:
    """创建'属性存在'条件谓词"""
    def _pred(ctx: dict) -> bool:
        if path in ctx:
            return True
        parts = path.split(".")
        val: Any = ctx
        try:
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    return False
                if val is None:
                    return False
            return True
        except (KeyError, IndexError, TypeError):
            return False
    return _pred

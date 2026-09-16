"""Macro reversal — 统一位置桥（锚 + 原文）回插。

对外统一入口，内部委托给 _bridge.restore_anchors。调用方传入的锚必须是统一格式
（每项带 `mode`：line/inline/token，见 `_bridge.py` 头部字段说明）——旧的
“无 mode”兼容包装已删（2026-09-17：产出端早已全部显式带 mode）。
Doc: preprocessor/README.md
"""

from ._bridge import restore_anchors


def protect_and_reverse(
    rendered: str,
    anchors: list[dict] | None = None,
) -> str:
    """按统一锚列表回插还原（锚 + 原文消耗式）。"""
    if not anchors:
        return rendered
    return restore_anchors(rendered, anchors)


def restore_condition_blocks(
    rendered: str, placeholders: dict[str, str] | None = None
) -> str:
    """把渲染输出中的条件块占位注释替换回原文段（统一为 line 锚回插）。

    placeholders: {占位 id → 原文段}，来自 scan_directives。
    占位注释（`// <tpc:cond:N>`）在扫描时替代 inactive 分支 + 块边界指令，
    渲染后原位替换回原文，实现条件编译多义性的保真恢复。

    嵌套条件块由 restore_anchors 的多轮扫描处理：外层原文可能含内层 marker。
    """
    if not placeholders:
        return rendered
    anchors = [
        {"marker": ph_id, "source_text": original, "mode": "line", "kind": "cond"}
        for ph_id, original in placeholders.items()
    ]
    return restore_anchors(rendered, anchors)

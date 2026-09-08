"""Macro reversal — 统一位置桥（锚 + 残片）回插。

对外统一入口，内部委托给 _bridge.restore_anchors。
兼容旧调用格式：
- protect_and_reverse 接受统一锚列表；旧 sync 记录（含 body/macro/sync 字段、
  无 mode）自动包装为 mode="sync" 锚。
- restore_condition_blocks 接受 {marker → 原文段} 占位 dict，内部转为 line 锚。
Doc: preprocessor/README.md
"""

from ._bridge import restore_anchors


def _normalize_anchors(anchors: list[dict] | None) -> list[dict]:
    """旧 sync 记录（restoration_stack 格式）统一包装为锚。"""
    if not anchors:
        return []
    out = []
    for entry in anchors:
        if isinstance(entry, dict) and "mode" in entry:
            out.append(entry)
        else:
            # 旧格式：{macro, body, sync, sync_nth, offset, is_func, args}
            e = dict(entry)
            e.setdefault("mode", "sync")
            out.append(e)
    return out


def protect_and_reverse(
    rendered: str,
    prefix: str = "`",
    restoration_stack: list[dict] | None = None,
    *,
    anchors: list[dict] | None = None,
) -> str:
    """按统一锚列表回插还原（锚 + 残片消耗式）。

    参数 prefix 和 sync 容差来自配置 preprocessor.reverse（_macro.toml → [reverse]）。
    restoration_stack 为旧参数名（兼容），anchors 为统一锚列表。
    """
    if anchors is None:
        anchors = restoration_stack
    if not anchors:
        return rendered
    return restore_anchors(rendered, _normalize_anchors(anchors), prefix)


def restore_condition_blocks(
    rendered: str, placeholders: dict[str, str] | None = None
) -> str:
    """把渲染输出中的条件块占位注释替换回原文段（统一为 line 锚回插）。

    placeholders: {占位 id → 原文段}，来自 scan_directives。
    占位注释（`// <tpc:cond:N>`）在扫描时替代 inactive 分支 + 块边界指令，
    渲染后原位替换回原文，实现条件编译多义性的保真恢复。

    嵌套条件块由 restore_anchors 的多轮扫描处理：外层残片可能含内层 marker。
    """
    if not placeholders:
        return rendered
    anchors = [
        {"marker": ph_id, "fragment": original, "mode": "line", "kind": "cond"}
        for ph_id, original in placeholders.items()
    ]
    return restore_anchors(rendered, anchors, "`")

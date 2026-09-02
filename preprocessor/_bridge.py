"""统一位置桥（Anchor Bridge）——锚 + 残片消耗式回插引擎。

把宏还原与条件块占位统一为同一定位机制：
- 锚（anchor）在展开/扫描阶段注册，携带唯一 marker + 原文残片（fragment）
- marker 以注释形态存在于 clean_source 中，穿过渲染管线后仍可定位
- 回插 = 定位 marker → 替换为残片 → 消耗（marker 全局唯一，天然只替换一次，
  不会"一个残片全局替换掉"多处）
- 多轮扫描：残片可能含内层 marker（嵌套条件块），直到不再变化

锚条目字段：
    marker:   唯一标识（"tpc:<kind>:<seq>"），以注释形态定位
    fragment: 原文残片（还原内容，可能是多行原文段）
    mode:     "line"（整行注释 marker，整行替换）
              "inline"（行内注释 marker，原位替换）
              "sync"（同步词启发式，表达式中间非空体宏，兼容现状）
    kind:     来源类别（"cond" / "macro"），仅作调试/归组
    # sync 模式额外字段（兼容现状 _restore_lines）：
    body / macro / sync / sync_nth / offset / is_func / args
Doc: docs/api.md（管线第一阶段：反向桥）
"""

import re

from core.config_registry import declare_cfg

# ── 配置需求（来自 tpc.toml）──────────────────────────────
# preprocessor.reverse
#   #sym:config = [reverse]
#   格式: dict
#     { sync_window_base: int, sync_window_pad: int, offset_tolerance: int }
_reverse_cfg: dict = declare_cfg(
    "preprocessor.reverse",
    {"sync_window_base": 15, "sync_window_pad": 5, "offset_tolerance": 2},
    __name__, "_reverse_cfg",
)


def make_marker(kind: str, seq: int) -> str:
    """生成统一 marker 文本：tpc:<kind>:<seq>。"""
    return f"tpc:{kind}:{seq}"


def _line_marker_re(marker: str) -> re.Pattern:
    """匹配独占整行的 marker 注释行（可带前导缩进/尾部空白）。"""
    return re.compile(
        rf"^[ \t]*//[ \t]*<{re.escape(marker)}>[ \t]*$", re.MULTILINE
    )


def _restore_sync_entry(result: str, entry: dict, prefix: str) -> str:
    """回插一条 sync 锚（现状同步词启发式逻辑，纳入统一引擎）。

    非空 body 的行内宏（如表达式中间 `NAME(args)）。空 body 不在此路径
    （由 line/inline 锚处理）。
    """
    body = entry.get("body", "")
    macro = entry.get("macro", "")
    if not body:
        return result

    sync_window_base = _reverse_cfg.get("sync_window_base", 15)
    sync_window_pad = _reverse_cfg.get("sync_window_pad", 5)
    offset_tolerance = _reverse_cfg.get("offset_tolerance", 2)

    sync = entry.get("sync", "")
    sync_nth = entry.get("sync_nth", 1)
    offset = entry.get("offset", 0)

    pos = 0
    while True:
        pos = result.find(body, pos)
        if pos < 0:
            break
        if sync:
            window = max(sync_window_base, len(sync) + offset + sync_window_pad)
            before = result[max(0, pos - window):pos]
            count = 0
            matched = False
            sync_idx = -1
            while True:
                sync_idx = before.find(sync, sync_idx + 1)
                if sync_idx < 0:
                    break
                count += 1
                if count == sync_nth:
                    real_sync_end = max(0, pos - window) + sync_idx + len(sync)
                    actual_offset = pos - real_sync_end
                    if abs(actual_offset - offset) <= offset_tolerance:
                        matched = True
                        break
            if not matched:
                pos += 1
                continue
        if entry.get("is_func"):
            replacement = f"{prefix}{macro}({entry.get('args', '')})"
        else:
            replacement = f"{prefix}{macro}"
        result = result[:pos] + replacement + result[pos + len(body):]
        break
    return result


def restore_anchors(
    rendered: str,
    anchors: list[dict] | None,
    prefix: str = "`",
) -> str:
    """统一回插引擎：按锚定位 marker，替换为残片，消耗式。

    line/inline 锚：marker 唯一 → 精确替换一次（残片不被全局复用）。
    sync 锚：同步词窗口消歧（现状启发式）。
    多轮扫描直到不再变化：残片可能含内层 marker（嵌套条件块/嵌套宏调用）。
    """
    if not anchors:
        return rendered

    result = rendered
    changed = True
    while changed:
        changed = False
        for entry in anchors:
            mode = entry.get("mode", "line")
            marker = entry.get("marker", "")
            fragment = entry.get("fragment", "")
            if not marker:
                continue

            if mode == "line":
                # 整行 marker：优先整行替换为残片（残片可为多行原文段）；
                # 渲染后 marker 若被并进其他行（非独占行），退化为文本替换。
                m = _line_marker_re(marker).search(result)
                if m:
                    result = result[:m.start()] + fragment + result[m.end():]
                    changed = True
                elif marker in result:
                    # 宽松退化：`// <marker>` 出现处原位替换
                    result = result.replace(f"// <{marker}>", fragment)
                    changed = True
            elif mode == "inline":
                # 行内 marker + body 区间替换：按操作栈机械撤销展开——
                # 找到 marker（`/*<marker>*/`）后，body 有两条定位路径：
                #   1. marker 后（展开原文顺序：`/*<marker>*/= 1'b1` 保留在
                #      clean_source，parser 跳过注释看到端口默认值；渲染端
                #      行尾锚定把 marker 挪到行尾后 body 仍在 marker 前同行）
                #   2. marker 前同行（渲染行尾锚定形态：`= 1'b1 /*<marker>*/,`）
                # 两种都替换 [body..marker] 整体为宏调用原文残片（body 不残留）。
                marker_text = f"/*<{marker}>*/"
                m_pos = result.find(marker_text)
                if m_pos < 0:
                    continue
                body = entry.get("body", "")
                if body:
                    b_pos = result.find(body, m_pos + len(marker_text))
                    if b_pos >= 0:
                        b_end = b_pos + len(body)
                        result = result[:m_pos] + fragment + result[b_end:]
                        changed = True
                        continue
                    # marker 前同行（行尾锚定形态）：body 被渲染挪到 marker 前
                    line_start = result.rfind("\n", 0, m_pos) + 1
                    b_pos = result.rfind(body, line_start, m_pos)
                    if b_pos >= 0:
                        result = result[:b_pos] + fragment + result[m_pos + len(marker_text):]
                        changed = True
                        continue
                # 无 body 或 body 渲染后不可定位：仅替换 marker（保守，body 残留）
                result = result.replace(marker_text, fragment)
                changed = True
            elif mode == "token":
                # 唯一 token（tpc_marker_N）：随 AST 确定渲染（标识符节点），
                # 全词匹配（\b）精确还原——避免 tpc_marker_1 误匹配 tpc_marker_10
                # 的子串；多锚互不干扰，不依赖注释通道启发式。
                pat = re.compile(rf"\b{re.escape(marker)}\b")
                new_result, count = pat.subn(fragment, result)
                if count:
                    result = new_result
                    changed = True
            else:  # sync
                new_result = _restore_sync_entry(result, entry, prefix)
                if new_result != result:
                    result = new_result
                    changed = True
    return result

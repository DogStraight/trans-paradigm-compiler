"""统一位置桥（Anchor Bridge）——锚 + 原文（source_text）消耗式回插引擎。

把宏还原与条件块占位统一为同一定位机制：
- 锚（anchor）在展开/扫描阶段注册，携带唯一 marker + 原文（source_text）
- marker 以**注释形态**存在于 clean_source 中（标点来自语言包声明，见
  `preprocessor/_markers.py`），穿过渲染管线后仍可定位
- 回插 = 定位 marker → 替换为原文 → 消耗（marker 全局唯一，天然只替换一次，
  不会"一段原文全局替换掉"多处）
- 多轮扫描：原文可能含内层 marker（嵌套条件块），直到不再变化

锚条目字段：
    marker:      唯一标识（"tpc:<kind>:<seq>"），以注释形态定位
    source_text: 原文（还原内容，可能是多行原文段）
    mode:        "line"（整行注释 marker，整行替换）
                 "inline"（行内注释 marker + body 区间，原位替换）
    kind:        来源类别（"cond" / "macro"），仅作调试/归组
    body:        inline 模式：展开时铺进源码的宏体（与 marker 一起换回原文）
# 注：旧 "sync" 模式（同步词窗口消歧）已删——它只服务"无 mode 字段"的旧格式记录，
# 而 `_expand`/`restore_condition_blocks` 产出的锚全部显式带 mode（2026-09-17）。
Doc: preprocessor/README.md
"""

import re

from lexer.comment_syntax import CommentSyntax

from ._markers import inline_marker, line_marker


def make_marker(kind: str, seq: int) -> str:
    """生成统一 marker 编号：tpc:<kind>:<seq>。"""
    return f"tpc:{kind}:{seq}"


def restore_anchors(
    rendered: str,
    anchors: list[dict] | None,
    *,
    syntax: CommentSyntax,
) -> str:
    """统一回插引擎：按锚定位 marker，替换为原文（source_text），消耗式。

    line/inline 锚：marker 唯一 → 精确替换一次（原文不被全局复用）。
    未知 mode → fail-fast（静默跳过会让占位残留到输出，不在本层降级）。
    多轮扫描直到不再变化：原文可能含内层 marker（嵌套条件块/嵌套宏调用）。

    syntax：语言包注释形态（占位以注释形态穿过管线，标点从声明取——
    引擎不认识 `//` / `/* */`，见 `preprocessor/_markers.py`）。
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
            source_text = entry.get("source_text", "")
            if not marker:
                continue

            if mode == "line":
                # 整行 marker：优先整行替换为 source_text（可为多行原文段）；
                # 渲染后 marker 若被并进其他行（非独占行），退化为文本替换。
                text = line_marker(syntax, marker)
                m = re.search(
                    rf"^[ \t]*{re.escape(text)}[ \t]*$", result, re.MULTILINE
                )
                if m:
                    result = result[:m.start()] + source_text + result[m.end():]
                    changed = True
                elif text in result:
                    # 宽松退化：占位文本出现处原位替换
                    result = result.replace(text, source_text)
                    changed = True
            elif mode == "inline":
                # 行内 marker + body 区间替换：按操作栈机械撤销展开——
                # 找到 marker（行内块注释形态）后，body 有两条定位路径：
                #   1. marker 后（展开原文顺序：`<marker>= 1'b1` 保留在
                #      clean_source，parser 跳过注释看到端口默认值；渲染端
                #      行尾锚定把 marker 挪到行尾后 body 仍在 marker 前同行）
                #   2. marker 前同行（渲染行尾锚定形态：`= 1'b1 <marker>,`）
                # 两种都替换 [body..marker] 整体为宏调用原文（source_text，body 不残留）。
                marker_text = inline_marker(syntax, marker)
                m_pos = result.find(marker_text)
                if m_pos < 0:
                    continue
                body = entry.get("body", "")
                if body:
                    b_pos = result.find(body, m_pos + len(marker_text))
                    if b_pos >= 0:
                        b_end = b_pos + len(body)
                        result = result[:m_pos] + source_text + result[b_end:]
                        changed = True
                        continue
                    # marker 前同行（行尾锚定形态）：body 被渲染挪到 marker 前
                    line_start = result.rfind("\n", 0, m_pos) + 1
                    b_pos = result.rfind(body, line_start, m_pos)
                    if b_pos >= 0:
                        result = result[:b_pos] + source_text + result[m_pos + len(marker_text):]
                        changed = True
                        continue
                # 无 body 或 body 渲染后不可定位：仅替换 marker（保守，body 残留）
                result = result.replace(marker_text, source_text)
                changed = True
            else:
                raise ValueError(
                    f"[preprocessor] 未知锚 mode: {mode!r}"
                    f"（支持 line/inline，见 preprocessor/README.md）"
                )
    return result

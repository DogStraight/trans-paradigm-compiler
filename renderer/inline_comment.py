"""
inline_comment.py — 基于锚点的行内注释回注

设计思路：将 inline comment 视为"特殊宏"，复用宏体恢复的文本级替换思路。

解析阶段：记录注释紧跟的 token 内容作为锚点（anchor token）。
渲染后：在渲染输出中搜索锚点内容，在锚点后追加注释文本。

与旧指纹方案对比：
- 无 multi-token fingerprint → 无动态窗算法、无 token_index 回溯
- 锚点是紧前 token，不受宏展开影响（宏展开改变的是宏体，锚点是宏调用的相邻 token）
- 行号窗口 [line-3, line+3] 约束搜索范围，降低歧义
"""


def restore_comments(rendered: str, comment_anchors: list[dict]) -> str:
    """
    通过锚点匹配将 inline comment 回注到渲染文本中。

    每个锚点条目：
        anchor: 紧前 token 内容（如 ";"、")"、"="）
        text:   注释文本（如 "// my comment"）
        line:   源行号（0-based）

    策略：
    1. 按源行号排序，保证插入顺序
    2. 在 [line-3, line+3] 窗口内搜索锚点
    3. 同一行连续多个匹配时取最后一个（靠近行尾）
    4. 一行仅插入一条注释
    5. 匹配失败则退化到窗口最后一行行尾追加
    """
    if not comment_anchors:
        return rendered, 0

    # 去重：parser 回溯可能导致同一条 comment 被多次收集
    # 按 (text, line) 去重，保留最先记录的锚点（最接近注释的紧前 token）
    seen: set[tuple[str, int]] = set()
    unique: list[dict] = []
    for c in comment_anchors:
        key = (c["text"], c["line"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    lines = rendered.split("\n")
    occupied: set[int] = set()

    for c in sorted(unique, key=lambda x: x["line"]):
        anchor = c["anchor"]
        comment = c["text"]
        src_line = c["line"]

        start = max(0, src_line - 1 - 3)
        end = min(len(lines), src_line + 3)

        best_idx = -1
        best_pos = -1

        for i in range(start, end):
            if i in occupied:
                continue
            # 从右向左搜：优先匹配行尾附近的锚点（更可能是注释位置）
            pos = lines[i].rfind(anchor)
            if pos < 0:
                continue
            # 取最后一个匹配（同一行可能有多个相同 token）
            if i > best_idx or (i == best_idx and pos > best_pos):
                best_idx = i
                best_pos = pos

        if best_idx >= 0:
            # 在锚点后插入注释
            pos = best_pos + len(anchor)
            line = lines[best_idx]
            indent = " " if pos > 0 and not line[pos - 1].isspace() else ""
            lines[best_idx] = line[:pos] + indent + "  " + comment + line[pos:]
            occupied.add(best_idx)
        else:
            # 退化到行号窗口最后一行行尾
            target = min(end - 1, len(lines) - 1)
            if target not in occupied:
                lines[target] = lines[target].rstrip() + "  " + comment
                occupied.add(target)

    return "\n".join(lines), len(unique)

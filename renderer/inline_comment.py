"""
inline_comment.py — 基于锚点的注释回注

两条互补路径：
1. AST 路径（block body）：collect_line_comments → Comment 节点 → Renderer 原生渲染
2. 锚点路径（列表结构内）：prepare_production 收集锚点 → restore_line_comments 渲染后回插
行内注释由 parse_token（锚点路径）收集。
"""


def restore_comments(rendered: str, comment_anchors: list[dict]) -> tuple[str, int]:
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


def restore_line_comments(rendered: str, anchors: list[dict]) -> tuple[str, int]:
    """基于锚点的行注释回插。

    工作原理：行注释出现在 source 中某两行之间，无法挂到 AST 节点 sub_node。
    此函数在渲染后根据"下一 token 锚点"将注释插回。

    锚点条目：
        text:   注释文本（如 "// my comment"）
        anchor: 注释后第一个有效 token 的内容（回插定位依据）
        line:   源行号（用于排序和窗口约束）

    策略：
    1. 按源行号排序
    2. 在 [line-1, line+2] 窗口内搜索锚点文本
    3. 在锚点所在行之前插入注释行
    4. (text, line) 去重，处理回溯导致的重复收集
    """
    if not anchors:
        return rendered, 0

    # 去重
    seen: set[tuple[str, int]] = set()
    unique: list[dict] = []
    for c in anchors:
        key = (c["text"], c["line"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    lines = rendered.split("\n")
    inserted: set[int] = set()  # 已插入注释的行偏移，防止位置冲突

    for c in sorted(unique, key=lambda x: x["line"]):
        text = c["text"]
        anchor = c["anchor"]
        src_line = c["line"]

        if not anchor:
            continue

        start = max(0, src_line - 1 - 1)  # line-2
        end = min(len(lines), src_line + 2)  # line+2

        best_idx = -1

        for i in range(start, end):
            if i in inserted:
                continue
            if anchor in lines[i]:
                best_idx = i
                break

        if best_idx >= 0:
            # 判断锚点是否在行内容中间（非行首首个 token）
            stripped = lines[best_idx].lstrip()
            content_pos = stripped.find(anchor)
            if content_pos > 0:
                # 锚点在行内容中间 → 拆分，在锚点前插注释行
                raw_pos = len(lines[best_idx]) - len(stripped) + content_pos
                before = lines[best_idx][:raw_pos]
                after = lines[best_idx][raw_pos:]
                line_indent = lines[best_idx][:len(lines[best_idx]) - len(stripped)]
                comment_line = line_indent + text
                lines[best_idx] = before.rstrip()
                lines.insert(best_idx + 1, comment_line)
                lines.insert(best_idx + 2, line_indent + after.lstrip())
                # 后续 inserted 偏移 +2
                inserted = {j + 2 if j >= best_idx else j for j in inserted}
                inserted.add(best_idx + 1)
            else:
                # 锚点在行首 → 整行前插（标准路径）
                indent = " " * (len(lines[best_idx]) - len(lines[best_idx].lstrip()))
                comment_line = indent + text
                lines.insert(best_idx, comment_line)
                inserted = {j + 1 if j >= best_idx else j for j in inserted}
                inserted.add(best_idx)
        else:
            # 退化：锚点没找到，在行号窗口末尾追加
            target = min(end - 1, len(lines) - 1)
            if target not in inserted:
                indent = " " * (len(lines[target]) - len(lines[target].lstrip()))
                comment_line = indent + text
                lines.insert(target + 1, comment_line)
                inserted = {j + 1 if j >= target else j for j in inserted}
                inserted.add(target)

    return "\n".join(lines), len(unique)

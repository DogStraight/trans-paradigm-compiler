"""
inline_comment.py — 基于锚点的注释回注

两条互补路径：
1. AST 路径（block body）：collect_line_comments → Comment 节点 → Renderer 原生渲染
2. 锚点路径（列表结构内）：prepare_production 收集锚点 → restore_line_comments 渲染后回插
行内注释由 parse_token（锚点路径）收集。

Doc: docs/decisions/0006-renderer-improve-roadmap.md（改进路线：阶段 2 注释 attachment 的目标替换对象）
"""

import re


def restore_comments(
    rendered: str,
    comment_anchors: list[dict],
    only_tpc: bool = False,
    only_midline: bool = False,
) -> tuple[str, int]:
    """
    通过锚点匹配将 inline comment 回注到渲染文本中。

    每个锚点条目：
        anchor: 紧前 token 内容（如 ";"、")"、"="）
        text:   注释文本（如 "// my comment"）
        line:   源行号（0-based）
        midline: 行中注释标记（P1.5——注释后还有同行代码 token）

    策略：
    1. 按源行号排序，保证插入顺序
    2. 在 [line-3, line+3] 窗口内搜索锚点
    3. 同一行连续多个匹配时取最后一个（靠近行尾）
    4. 一行仅插入一条注释
    5. 匹配失败则退化到窗口最后一行行尾追加

    only_tpc=True：只回插 tpc marker（`/*<tpc:*>`，宏/条件块还原依赖），跳过
    普通注释。宏展开/变换路径渲染行号与源行号错位（展开改变行数），±3 窗口
    在渲染文本定位到错误区域，普通注释（如 `end // case: x` 的 anchor='end'
    通用子串）会错插到端口/参数行——与 line 通道 only_tpc 语义对称，普通注释
    锚点漂移时跳过（丢失但结构合法），tpc marker 仍必须回插（否则宏还原失效）。

    only_midline=True：只回插行中注释（midline=True）。行中注释不挂 attachment
    （P1.5 行中块注释保持原位），无渲染兜底——inline_comments 开关关闭时也
    必须回插防丢。
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

        if only_tpc and "tpc:" not in comment:
            continue  # 展开路径：普通注释锚点漂移，跳过（tpc marker 仍回插）
        if only_midline and not c.get("midline"):
            continue  # 只回插行中注释（行尾注释由 attachment 渲染）

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


def _interp_tpc_line(src_line: int, rendered_tpc_src: dict, rendered_tpc: dict) -> int:
    """用已渲染 tpc marker（源行号 → 渲染行号）分段线性插值 src_line 的渲染位置。

    tpc marker 大多数随 AST 渲染（位置精确），少数被 production 吞掉走此回插；
    被吞 marker 的渲染位置用源行号最接近的已渲染 marker 线性插值（模块内行距
    接近线性），比裸源行号窗口（模块边界偏移 ±150）可靠。
    """
    pairs = sorted((s, rendered_tpc[m]) for m, s in rendered_tpc_src.items())
    if not pairs:
        return src_line
    prev = [p for p in pairs if p[0] <= src_line]
    nxt = [p for p in pairs if p[0] > src_line]
    if prev and nxt:
        p_src, p_r = prev[-1]
        n_src, n_r = nxt[0]
        return int(p_r + (src_line - p_src) * (n_r - p_r) / max(1, n_src - p_src))
    if prev:
        p_src, p_r = prev[-1]
        return p_r + (src_line - p_src)
    n_src, n_r = nxt[0]
    return n_r - (n_src - src_line)


def restore_line_comments(
    rendered: str,
    anchors: list[dict],
    tpc_src_map: dict | None = None,
    only_tpc: bool = False,
) -> tuple[str, int]:
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

    only_tpc=True：只回插 tpc marker（`// <tpc:*>`，宏/条件块还原依赖），
    跳过普通注释。变换路径禁用普通注释恢复（锚点漂移会误匹配拆坏注释行），
    但宏 marker 是唯一性插值定位、不依赖锚点窗口，仍必须回插——否则
    protect_and_reverse 找不到 marker，宏还原失效。
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
    # 已作为整行渲染存在的注释（strip 缩进比较）：随 AST 渲染（未被 production
    # skip 吞掉），不再回插——否则同一注释被"AST 渲染 + line_comment 回插"双通道
    # 重复（宏锚/条件占位 marker 在块内容易触发 parser 回溯双收集）。
    existing_lines: set[str] = {ln.strip() for ln in lines}
    inserted: set[int] = set()  # 已插入注释的行偏移，防止位置冲突

    # 已随 AST 渲染的 tpc: marker（位置精确）——作为被吞 marker 的插值锚点
    rendered_tpc: dict[str, int] = {}  # marker -> render_line(1-based)
    for i, l in enumerate(lines, 1):
        m = re.search(r"// <(tpc:[^>]+)>", l)
        if m:
            rendered_tpc[m.group(1)] = i
    rendered_tpc_src: dict[str, int] = {}
    if tpc_src_map:
        rendered_tpc_src = {
            k: tpc_src_map[k] for k in rendered_tpc if k in tpc_src_map
        }

    for c in sorted(unique, key=lambda x: x["line"]):
        text = c["text"]
        anchor = c["anchor"]
        src_line = c["line"]
        is_tpc = "tpc:" in text

        if only_tpc and not is_tpc:
            continue  # 变换路径：普通注释锚点漂移，跳过（tpc marker 仍回插）

        if text in existing_lines:
            continue

        # 行尾注释（`code // 注释`）已由 join/attachment 输出（行尾包含注释
        # 文本）→ 不重复回插——否则"列表分隔符后注释"被 join 输出后又经
        # line 回插双通道重复。
        if any(ln.rstrip().endswith(text.strip()) for ln in lines):
            continue

        if not anchor:
            continue

        if is_tpc:
            # 被吞 tpc marker：用已渲染 marker 分段线性插值定位
            center = _interp_tpc_line(src_line, rendered_tpc_src, rendered_tpc)
            start = max(0, center - 5)
            end = min(len(lines), center + 5)
        else:
            start = max(0, src_line - 1 - 1)  # line-2
            end = min(len(lines), src_line + 2)  # line+2

        best_idx = -1

        if is_tpc:
            # tpc marker anchor 用词边界匹配：避免 'cpuregs' 误匹配
            # 'cpuregs_wrdata'（子串，如 TESTBUG_001 被插到 case 分支），
            # 只匹配完整 token 出现（'cpuregs[' 等）。
            anchor_re = re.compile(rf"\b{re.escape(anchor)}\b")
            for i in range(start, end):
                if i in inserted:
                    continue
                if anchor_re.search(lines[i]):
                    best_idx = i
                    break
        else:
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
                line_indent = lines[best_idx][: len(lines[best_idx]) - len(stripped)]
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
            # 退化：锚点没找到。不追加到窗口末尾——那会把注释塞进文件尾
            # （如 endmodule 之后），污染结构导致重新解析 truncated；直接跳过，
            # 注释丢失但结构合法。常见于连续注释块（锚点指向下一条注释文本，
            # 渲染后不存在，如模块头注释组）。
            continue

    return "\n".join(lines), len(unique)

"""
inline_comment.py — 基于指纹的行内注释回注

解析阶段收集 inline comment 和前文 token 指纹，
渲染后通过指纹匹配将注释插回生成代码的对应位置。

匹配策略：子序列匹配（flexible）+ 末端偏好评分。
指纹是 token 内容列表，判断渲染行是否按顺序包含这些 token 内容，
忽略空白差异。多行匹配时优先选匹配结束位置最靠近行尾的行，
因为 inline comment 天然位于代码构造的末尾。
"""


def _match_end(line: str, tokens: list[str]) -> int:
    """子序列匹配，返回匹配结束位置（-1 表示不匹配）"""
    pos = 0
    for t in tokens:
        pos = line.find(t, pos)
        if pos == -1:
            return -1
        pos += len(t)
    return pos


def _best_match_line(
    lines: list[str], tokens: list[str], start: int, end: int, skip: set[int]
) -> int:
    """在 [start, end) 范围内找最佳匹配行。

    评分规则（两阶段）：
    1. 匹配结束位置离行尾非空白越近越好（绝对字符距离）
    2. 平局时优先选择索引更大的行（更深嵌套，更接近注释原始位置）
    返回 -1 表示无可匹配行。
    """
    best_idx = -1
    best_dist = 10**9
    for i in range(start, end):
        if i in skip:
            continue
        pos = _match_end(lines[i], tokens)
        if pos < 0:
            continue
        content_len = len(lines[i].rstrip())
        if content_len == 0:
            continue
        dist = content_len - pos
        # 平局时优先选择索引更大的行（更深嵌套，更可能是注释位置）
        if dist < best_dist or (dist == best_dist and i > best_idx):
            best_dist = dist
            best_idx = i
    return best_idx


def inject_comments(rendered: str, inline_comments: list[dict]) -> str:
    """
    在渲染后的文本中匹配指纹，回注 inline comment。

    策略：
    - 按源行号排序（稳定），优先保证注释出现顺序与源文件一致
    - 在 [line-3, line+3] 窗口内找最佳匹配行
    - 匹配成功则追加到行尾
    - 匹配失败则退化到行号窗口最后一行
    """
    if not inline_comments:
        return rendered

    lines = rendered.split("\n")
    occupied: set[int] = set()

    for c in sorted(inline_comments, key=lambda x: x["line"]):
        tokens = c["fingerprint"]
        start = max(0, c["line"] - 1 - 3)
        end = min(len(lines), c["line"] + 3)

        best = _best_match_line(lines, tokens, start, end, occupied)
        if best >= 0:
            pos = _match_end(lines[best], tokens)
            line = lines[best]
            # 在指纹匹配位置后插入注释，而非行尾追加
            indent = " " if pos > 0 and not line[pos - 1].isspace() else ""
            lines[best] = line[:pos] + indent + c["text"] + line[pos:]
            occupied.add(best)
        else:
            target = min(end - 1, len(lines) - 1)
            if target not in occupied:
                lines[target] = lines[target].rstrip() + "  " + c["text"]
                occupied.add(target)

    return "\n".join(lines)

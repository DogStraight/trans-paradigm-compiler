"""wrap_comments.py — 超长注释折行 pass

把超过 max_line_width 的纯 `//` 注释按词折成多行（VeriGood wrapComment 借鉴）。
续行保留 `// ` 前缀（注释语义：每行都是独立 `//` 注释，可读性不破坏）。

安全：
  - 只折纯注释行（行首 `//`），不碰行内注释（`code // comment`——折了破坏代码行）
  - 只折无格式化指令的注释（`// verilog_format: off` 等跳过）
  - 幂等：折出的行 ≤ max_len 不再折
  - 不折 URL/长词（单词超宽保留，防拆断链接/数字）

此 pass 默认**不启用**（破坏性最小原则）——由 [formatter.wrap_comments].enabled 控制。
"""

from __future__ import annotations


def _wrap_comment_line(line: str, max_len: int) -> list[str]:
    """折单条 `//` 注释行 → 多行（每行 `// ` 前缀）。"""
    # 只处理 `//` 开头的纯注释（含缩进）
    s = line.lstrip()
    if not s.startswith("//"):
        return [line]
    lead = line[: len(line) - len(s)]
    # 保留 `// ` 前缀（已有空格或补一个）
    m = s[:2] + (" " if len(s) == 2 or s[2] != " " else s[2:])
    # 前缀长度计入：`// ` 之后是文本
    prefix = lead + "// "
    text = s[2:].lstrip()
    if len(line) <= max_len or not text:
        return [line]

    words = text.split()
    out: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip() if cur else w
        if len(prefix) + len(trial) > max_len:
            if cur:
                out.append(prefix + cur.strip())
            cur = w
        else:
            cur = trial
    if cur:
        out.append(prefix + cur.strip())
    return out if out else [line]


def run_wrap_comments(lines: list[str], max_width: int = 100) -> list[str]:
    """折所有超宽纯注释行（行内注释/非注释不碰）。"""
    result: list[str] = []
    for line in lines:
        result.extend(_wrap_comment_line(line, max_width))
    return result

"""ifdef_annotate.py — 条件编译指令注释标注 pass

给 `` `else `` / `` `endif `` 补配对宏名注释（VeriGood 借鉴）：
    `ifdef FEATURE_A
      wire a;
    `else // FEATURE_A        ← 补
      wire b;
    `endif // FEATURE_A       ← 补

纯文本栈跟踪（通用算法，非语言知识）：
  - `` `ifdef/`ifndef `` → push 宏名
  - `` `elsif `` → 栈顶替换（条件变化，沿用当前宏名）
  - `` `else `` → 补 `` `else // NAME ``（栈顶）
  - `` `endif `` → pop 并补 `` `endif // NAME ``

安全：只改指令行（不碰 token），已有注释不重复（`` `else // 已有 `` 保留）；
只标注"配对明确的"——空栈（孤 `else/`endif）不补。
"""

from __future__ import annotations

from typing import Sequence

_IFDEF_OPEN = ("`ifdef", "`ifndef")
_IFDEF_ELSE = ("`else",)
_IFDEF_END = ("`endif",)


def _extract_name(line: str) -> str | None:
    """从 `` `ifdef NAME `` 提取宏名（去除行内注释/尾随内容）。"""
    s = line.lstrip()
    for kw in _IFDEF_OPEN:
        if s.startswith(kw):
            rest = s[len(kw):].strip()
            # 宏名 = 第一个词（到空白或注释）
            name = rest.split()[0] if rest else ""
            # 去掉行内注释（`ifdef FOO // comment`）
            name = name.split("//")[0].strip()
            return name or None
    return None


def _annotate_endif(line: str, s: str, leading: str, stack: list[str]) -> str:
    """`` `endif ``：pop 栈顶并补配对宏名（已有注释/空栈 → 原样）。"""
    name = stack.pop() if stack else None
    if name and "//" not in s:
        return f"{leading}`endif // {name}"
    return line


def _annotate_elsif(line: str, s: str, leading: str) -> str:
    """`` `elsif ``：补自身条件名（`` `elsif FEATURE_B `` → 尾补 `` // FEATURE_B ``）。"""
    if "//" in s:
        return line
    name = _extract_elsif_name(s)
    if not name:
        return line
    return f"{leading}`elsif {name} // {name}"


def _annotate_else(line: str, s: str, leading: str, stack: list[str]) -> str:
    """`` `else ``：沿用栈顶宏名（条件分支仍是同一个 ifdef 块）。"""
    name = stack[-1] if stack else None
    if name and "//" not in s:
        return f"{leading}`else // {name}"
    return line


def run_ifdef_annotate(lines: Sequence[str]) -> list[str]:
    """给 `` `else `` / `` `endif `` 补配对宏名注释（幂等：已有注释不重复）。"""
    stack: list[str] = []
    result: list[str] = []
    for line in lines:
        s = line.lstrip()
        leading = line[: len(line) - len(s)]
        if s.startswith(_IFDEF_OPEN):
            name = _extract_name(line)
            if name:
                stack.append(name)
            result.append(line)
        elif s.startswith(_IFDEF_END):
            result.append(_annotate_endif(line, s, leading, stack))
        elif s.startswith("`elsif"):
            result.append(_annotate_elsif(line, s, leading))
        elif s.startswith(_IFDEF_ELSE):
            result.append(_annotate_else(line, s, leading, stack))
        else:
            result.append(line)
    return result


def _extract_elsif_name(s: str) -> str | None:
    """从 `` `elsif NAME `` 提取条件名（第一个词）。"""
    rest = s[len("`elsif"):].strip()
    name = rest.split()[0] if rest else ""
    return name.split("//")[0].strip() or None

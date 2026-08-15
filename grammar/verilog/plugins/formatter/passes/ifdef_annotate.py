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


def run_ifdef_annotate(lines: list[str]) -> list[str]:
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
            name = stack.pop() if stack else None
            if name and "//" not in s:
                # 已有注释不覆盖；无注释则补 `` `endif // NAME ``
                result.append(f"{leading}`endif // {name}")
            else:
                result.append(line)
        elif s.startswith(("`elsif",)):
            # elsif 保留自身条件名（`` `elsif FEATURE_B `` → 补 `` // FEATURE_B ``）
            if "//" not in s:
                name = _extract_elsif_name(s)
                if name:
                    result.append(f"{leading}`elsif {name} // {name}")
                    continue
            result.append(line)
        elif s.startswith(_IFDEF_ELSE):
            # else 沿用栈顶宏名（条件分支仍是同一个 ifdef 块）
            name = stack[-1] if stack else None
            if name and "//" not in s:
                result.append(f"{leading}`else // {name}")
            else:
                result.append(line)
        else:
            result.append(line)
    return result


def _extract_elsif_name(s: str) -> str | None:
    """从 `` `elsif NAME `` 提取条件名（第一个词）。"""
    rest = s[len("`elsif"):].strip()
    name = rest.split()[0] if rest else ""
    return name.split("//")[0].strip() or None

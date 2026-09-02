"""check_test.py — 注释驱动测试框架（Semgrep 式 ruleid:/ok: 断言，零代码测试）。

声明式规则（[[checks]]）的测试形态：样例源文件内嵌指令注释，引擎校验
"注释标记的代码段是否按预期命中/未命中规则"——测试编写零代码，规则
行为变化时断言随样例自动更新语义。

指令注释（`//` 行注释）：
    // ruleid: NC001           下一段代码（到下一个指令注释前）必须命中 NC001
    // ok: NC001               下一段代码不得命中 NC001
    // ruleid: NC001, NC005    多规则（逗号分隔）

区间语义：指令注释所在行之后、下一个指令注释之前为被标记代码段。
诊断按起始行（0-based）归属：落在段内（指令行之后）即计入该段。

用法（pytest）：
    from analyzer.check_test import run_comment_driven
    failures = run_comment_driven(ProjectChecker(...), sample_path)
    assert not failures, "\\n".join(failures)

Doc: docs/semantic_checks.md（注释驱动测试框架）
"""

from __future__ import annotations

import re
from typing import Any

# 指令注释：// ruleid: A, B / // ok: A, B
_RULEID_RE = re.compile(r"//\s*ruleid:\s*([^\n]+)")
_OK_RE = re.compile(r"//\s*ok:\s*([^\n]+)")


def parse_directives(source: str) -> tuple[list[dict], dict[int, int]]:
    """解析指令注释。

    Returns:
        (directives, region_map):
            directives: [{"line": 行号(0-based), "type": "ruleid"|"ok",
                          "rules": [id, ...]}, ...]（按行排序）
            region_map: {指令行: 段结束行(下一个指令行或 EOF)}
    """
    directives: list[dict] = []
    lines = source.splitlines()
    for idx, line in enumerate(lines):
        m = _RULEID_RE.search(line)
        if m:
            directives.append(
                {
                    "line": idx,
                    "type": "ruleid",
                    "rules": [r.strip() for r in m.group(1).split(",") if r.strip()],
                }
            )
            continue
        m = _OK_RE.search(line)
        if m:
            directives.append(
                {
                    "line": idx,
                    "type": "ok",
                    "rules": [r.strip() for r in m.group(1).split(",") if r.strip()],
                }
            )
    directives.sort(key=lambda d: d["line"])
    region_map: dict[int, int] = {}
    for i, d in enumerate(directives):
        end = directives[i + 1]["line"] if i + 1 < len(directives) else len(lines)
        region_map[d["line"]] = end
    return directives, region_map


def run_comment_driven(checker: Any, path: str) -> list[str]:
    """运行注释驱动测试：检查样例文件，校验指令命中。

    checker: ProjectChecker 实例（check(path) 返回 report）。
    path: 样例源文件路径。

    Returns:
        failures: 断言失败描述列表（空 = 全过）。
            格式: "L{行}: ruleid NC001 未命中" /
                  "L{行}: ok NC001 意外命中"
    """
    with open(path, encoding="utf-8") as f:
        source = f.read()
    directives, region_map = parse_directives(source)
    if not directives:
        return []

    report = checker.check(path)
    # 收集诊断（syntax + semantic），起始行 0-based
    diags: list[tuple[int, str]] = []
    for f in report["files"]:
        for d in f.get("syntax", []):
            r = d.get("range")
            if r:
                diags.append((r["start"]["line"], d.get("code", "")))
        for d in f.get("semantic", []):
            r = d.get("range")
            if r:
                diags.append((r["start"]["line"], d.get("code", "")))

    failures: list[str] = []
    for d in directives:
        start, end = d["line"], region_map[d["line"]]
        # 段内诊断：指令行本身（同行的声明/代码）到段结束前
        # （下一个指令行不包含——那是下一段的起点）。
        region_codes = {code for line, code in diags if start <= line < end}
        for rule in d["rules"]:
            if d["type"] == "ruleid":
                if rule not in region_codes:
                    failures.append(
                        f"L{start + 1}: ruleid {rule} 未命中"
                        f"（段内诊断: {sorted(region_codes)}）"
                    )
            else:  # ok
                if rule in region_codes:
                    failures.append(
                        f"L{start + 1}: ok {rule} 意外命中"
                        f"（段内诊断: {sorted(region_codes)}）"
                    )
    return failures

"""Bifrost 有效性抽查探针（刻意含已知坏味）——**不是产品代码，不要当样例抄**。

用途：`bifrost scan tools/bifrost_probe` 应报出 5 条（见下）。报不出说明工具或
策略面失效（外部审计的"门禁有效性抽查"，与 `tools/check_gate_efficacy.py` 同思路）。

期望命中：
- `bifrost.correctness.dynamic-evaluation`（`eval`）
- `bifrost.performance.file-read-in-loop`（循环内 `open`）
- `bifrost.performance.parsing-in-loop`（循环内 `json.loads`）
- `bifrost.performance.regex-compile-in-loop`（循环内 `re.compile`）
- `bifrost.performance.subprocess-in-loop`（循环内 `subprocess.run`）

Doc: policy/bifrost_audit.md（外部审计规程：有效性抽查节）
"""

import json
import re
import subprocess


def read_all(paths: list[str]) -> list[str]:
    """循环内 open + re.compile（两处坏味，均为真实的重复开销形态）。"""
    out: list[str] = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        pat = re.compile(r"\d+")
        out.append(" ".join(pat.findall(text)))
    return out


def run_each(cmds: list[str]) -> list[str]:
    """循环内 subprocess + json.loads（子进程与解析都在循环里）。"""
    outs: list[str] = []
    for c in cmds:
        res = subprocess.run(c, shell=True, capture_output=True, text=True)
        outs.append(json.loads(res.stdout or "{}").get("k", ""))
    return outs


def compute(flag: bool, expr: str) -> object:
    """动态求值（correctness 类，探针里刻意保留）。"""
    if flag:
        return eval(expr)
    return json.loads(expr)

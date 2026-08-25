"""run_differential.py — 与 verible-verilog-format 差分对拍（可选依赖）。

差分属性（风格无关，不比字节相等）：
    1. 接受域：Verible 接受 ∧ 属于 V2001 子集 → tpc 必须接受（假拒检测）。
    2. 互操作：tpc 输出必须被 Verible 接受（渲染器产出合法代码检测）。

Verible 二进制定位：环境变量 VERIBLE_FORMAT，或 PATH 中的
verible-verilog-format。缺失则跳过（exit 0 + 提示）。

用法：
    python tests/differential/run_differential.py            # 语料 = samples + edge
    python tests/differential/run_differential.py <file.v>   # 单文件
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# 二进制定位优先级：VERIBLE_FORMAT 环境变量 → PATH → 仓库内
# tests/differential/.tools/verible/（fetch_verible.ps1 下载的固定位置）。
_TOOLS_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          ".tools", "verible", "verible-verilog-format.exe")
VERIBLE = (
    os.environ.get("VERIBLE_FORMAT")
    or shutil.which("verible-verilog-format")
    or (_TOOLS_BIN if os.path.isfile(_TOOLS_BIN) else None)
)


def _verible_accepts(path: str) -> bool:
    """verible-verilog-format 对文件 exit 0 = 可解析。"""
    assert VERIBLE is not None  # main() 已守卫缺失二进制
    try:
        r = subprocess.run([VERIBLE, path], capture_output=True, timeout=30)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def main() -> None:
    if not VERIBLE:
        print("skip: verible-verilog-format 未找到（设置 VERIBLE_FORMAT 或装到 PATH）")
        return

    from pipeline import run_pipeline_on_source

    targets: list[str] = []
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        targets = [sys.argv[1]]
    else:
        for root in ("tests/e2e/samples", "tests/edge/edge_corpus"):
            for dirpath, _, names in os.walk(root):
                # 接受域只对"合法语料"检查：lint_err/errors（故意写错的样本）
                # 与 edge/reject（故意拒绝的语料）本就被设计为失败，Verible 的
                # 宽松解析器能容忍它们——不构成对拍样本。
                if any(k in dirpath for k in ("lint_err", "errors")) or \
                        os.path.sep + "reject" in dirpath:
                    continue
                targets += [os.path.join(dirpath, n) for n in names if n.endswith(".v")]

    findings: list[str] = []
    n = 0
    for path in targets:
        n += 1
        with open(path, encoding="utf-8") as f:
            src = f.read()
        # 只对无宏指令的纯 Verilog 做接受域对拍（宏路径两边语义不同）
        if any(m in src for m in ("`ifdef", "`define", "`include")):
            continue
        v_ok = _verible_accepts(path)
        if not v_ok:
            continue  # Verible 都不接受 → 不构成对拍样本
        r = run_pipeline_on_source(source=src, quiet=True, expand_macros=True,
                                   analyzer_enabled=False, transform_enabled=False,
                                   renderer_enabled=True, parse_enabled=True,
                                   no_lint=False, format_output=True)
        if not r.get("success"):
            findings.append(f"[FALSE-REJECT] {path}: verible 接受但 tpc 失败: "
                            f"{r.get('error', '')}")
            continue
        out = r.get("output", "")
        tmp = path + ".tpc_out.v"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(out)
        if not _verible_accepts(tmp):
            findings.append(f"[BAD-INTEROP] {path}: tpc 输出不被 verible 接受")
        os.remove(tmp)

    print(f"differential: {n} files checked, findings: {len(findings)}")
    for f_ in findings:
        print("  " + f_)
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()

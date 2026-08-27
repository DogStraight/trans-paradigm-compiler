"""run_differential_svparser.py — 与 sv-parser（parse_sv）差分对拍（可选依赖）。

对标属性（风格无关，不比字节相等）：
    1. 接受域：sv-parser 接受 ∧ 属于 V2005 子集语料 → tpc 必须接受
       （假拒检测——sv-parser 收但 tpc 拒 = tpc 真缺陷）。
    2. 宽进差异：sv-parser 拒 ∧ tpc 收 → 记录（非失败）。sv-parser 严格
       实现 Annex A，tpc 宽进（如 `wire \\a.b;` 无空格：sv-parser 须写
       `\\a.b ;`，tpc 分隔符提前终止直接可解析）——这是有意的取舍差异，
       不算 tpc 缺陷，但值得定期观察量级。
    3. 互操作：tpc 输出必须被 sv-parser 接受（渲染器产出合法代码检测）。

sv-parser 定位：parse_sv.exe（编译自 sv-parser 仓库 examples/parse_sv.rs，
E:\\research\\sv-parser）。二进制缺失则跳过（exit 0 + 提示）。

⚠ 边界：sv-parser 是 IEEE 1800-2017 全量（SystemVerilog），tpc 是
Verilog-2005 子集（无 SV）。差分只对"2005 子集语料"（samples/edge）做
接受域检查——语料不用 SV 特性，故 sv-parser 收 ≠ SV 特性，接受域判定
成立。SV 特性语料（如 logic/always_ff）不在 samples/edge 中，天然排除。

用法：
    python tests/differential/run_differential_svparser.py            # 语料 = samples + edge
    python tests/differential/run_differential_svparser.py <file.v>   # 单文件
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# parse_sv 二进制定位：SV_PARSER 环境变量 → PATH → 仓库内固定位置
_TOOLS_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          ".tools", "sv-parser", "parse_sv.exe")
SV_PARSER = (
    os.environ.get("SV_PARSER")
    or shutil.which("parse_sv")
    or (_TOOLS_BIN if os.path.isfile(_TOOLS_BIN) else None)
)


def _sv_parser_accepts(path: str) -> bool:
    """parse_sv 对文件 exit 0 = 可解析。"""
    assert SV_PARSER is not None  # main() 已守卫缺失二进制
    try:
        r = subprocess.run([SV_PARSER, "-q", path], capture_output=True, timeout=60)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _collect_targets() -> list[str]:
    """语料 = samples + edge（合法语料，排除 lint_err/errors/reject/宏）。"""
    targets: list[str] = []
    for root in ("tests/e2e/samples", "tests/edge/edge_corpus"):
        for dirpath, _, names in os.walk(root):
            if any(k in dirpath for k in ("lint_err", "errors")) or \
                    os.path.sep + "reject" in dirpath:
                continue
            targets += [os.path.join(dirpath, n) for n in names if n.endswith(".v")]
    # 排除宏指令文件（两边预处理器语义不同，不构成对拍样本）
    return [t for t in targets if not any(
        m in open(t, encoding="utf-8").read()
        for m in ("`ifdef", "`define", "`include")
    )]


def main() -> None:
    if not SV_PARSER:
        print("skip: parse_sv 未找到（设置 SV_PARSER 或编译 sv-parser examples/parse_sv.rs 到"
              " tests/differential/.tools/sv-parser/）")
        return

    from pipeline import run_pipeline_on_source

    targets = ([sys.argv[1]] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1])
               else _collect_targets())

    false_reject: list[str] = []   # sv-parser 收 ∧ tpc 拒 = 真缺陷
    lenient_diff: list[str] = []   # sv-parser 拒 ∧ tpc 收 = 宽进取舍（非失败）
    bad_interop: list[str] = []    # tpc 输出不被 sv-parser 接受
    n = 0
    for path in targets:
        n += 1
        s_ok = _sv_parser_accepts(path)
        r = run_pipeline_on_source(source=open(path, encoding="utf-8").read(),
                                   quiet=True, expand_macros=True,
                                   analyzer_enabled=False, transform_enabled=False,
                                   renderer_enabled=True, parse_enabled=True,
                                   no_lint=False, format_output=True)
        t_ok = bool(r.get("success"))
        if s_ok and not t_ok:
            false_reject.append(f"[FALSE-REJECT] {path}: sv-parser 接受但 tpc 失败: "
                                f"{r.get('error', '')}")
            continue
        if not s_ok and t_ok:
            lenient_diff.append(f"[LENIENT] {path}: sv-parser 拒但 tpc 收（宽进差异）")
            continue
        if s_ok and t_ok:
            out = r.get("output", "")
            tmp = path + ".tpc_out.v"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(out)
            if not _sv_parser_accepts(tmp):
                bad_interop.append(f"[BAD-INTEROP] {path}: tpc 输出不被 sv-parser 接受")
            os.remove(tmp)

    print(f"sv-parser differential: {n} files checked")
    print(f"  false-reject（真缺陷）: {len(false_reject)}")
    for f_ in false_reject:
        print("    " + f_)
    print(f"  lenient-diff（宽进取舍）: {len(lenient_diff)}")
    for f_ in lenient_diff:
        print("    " + f_)
    print(f"  bad-interop（互操作）: {len(bad_interop)}")
    for f_ in bad_interop:
        print("    " + f_)
    # 门禁：假拒与互操作为硬失败；宽进差异仅记录（有意取舍，含 tpc 专属
    # 增强语法样本——sv-parser 不认 impl/type 等扩展属预期）
    sys.exit(1 if (false_reject or bad_interop) else 0)


if __name__ == "__main__":
    main()

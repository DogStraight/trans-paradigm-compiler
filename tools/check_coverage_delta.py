"""tools/check_coverage_delta.py — 增量覆盖率自查（只看本次改动的引擎文件）。

Doc: AGENTS.md（运行节：快速回归层 smoke / 全量测试定位）

动机：全量 `--cov` 串行 ~32min，只在发布时跑 → **平时新增代码的覆盖率是
盲区**（0.1.2 收尾轮新增的 MH 检查器，覆盖率当时无从得知）。本脚本只统计
本次改动的引擎源码文件，跑 smoke 层，几十秒内给出反馈；完整覆盖仍留发布时
全量跑。

用法：
    python tools/check_coverage_delta.py                  # 对比工作区（含未跟踪）
    python tools/check_coverage_delta.py --base HEAD~3    # 对比指定基线
    python tools/check_coverage_delta.py --fail-under 60  # 低于阈值即失败
                                                          # （默认只报告，不失败）

设计取舍：
- **默认只报告不失败**：smoke 层未必覆盖改动文件的全部路径（新分支可能要全量
  测试才走到），硬卡会误伤；需要卡时用 `--fail-under` 显式表态。
- **配置驱动**：统计范围取自 `pyproject.toml` 的 `[tool.coverage.run].source`，
  不硬编码包名——新增引擎包时本脚本自动跟上，不需要改代码。
- **不纳入 pytest**：它跑测试，若再被 pytest 调用会自我递归且拖慢门禁；作为
  独立脚本由人/CI 在提交前调用。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import tomllib

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cov_config() -> dict:
    """读 pyproject.toml 的 coverage 配置（统计范围 + 全量阈值）。"""
    with open(os.path.join(_ROOT, "pyproject.toml"), "rb") as f:
        data = tomllib.load(f)
    return data.get("tool", {}).get("coverage", {})


def _git_lines(*args: str) -> list[str]:
    """跑 git 命令并返回非空输出行（失败则返回空列表，由调用方判断）。"""
    proc = subprocess.run(
        ["git", *args], cwd=_ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    if proc.returncode != 0:
        print(f"[warn] git {' '.join(args)} 失败：{proc.stderr.strip()}")
        return []
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


def _changed_sources(base: str, sources: list[str]) -> list[str]:
    """本次改动的引擎源码文件（已跟踪的 diff + 未跟踪的新文件）。"""
    candidates = _git_lines("diff", "--name-only", base)
    candidates += _git_lines("ls-files", "--others", "--exclude-standard")
    out: list[str] = []
    for rel in candidates:
        norm = rel.replace("\\", "/")
        if not norm.endswith(".py"):
            continue
        if not any(norm == s or norm.startswith(s + "/") for s in sources):
            continue
        if norm not in out:
            out.append(norm)
    return out


def _module_name(rel: str) -> str:
    """源码路径 → coverage 能识别的模块名。

    coverage 的 `--cov=` 只认模块/包名，传文件路径会得到
    “Module linter/scanner.py was never imported”（实测）——故做转换；
    `__init__.py` 退回到其所在包名。
    """
    path = rel[:-3] if rel.endswith(".py") else rel
    if path.endswith("/__init__"):
        path = path[: -len("/__init__")]
    return path.replace("/", ".")


def _lookup(cov: dict, rel: str) -> dict | None:
    """在 coverage JSON 里按路径后缀找文件（键可能是相对或绝对路径）。"""
    want = rel.replace("/", os.sep)
    for key, info in cov.items():
        if key.endswith(want) or key.replace("\\", "/").endswith(rel):
            return info
    return None


def _related_tests(files: list[str]) -> list[str]:
    """改动文件所在包 → 对应测试目录（取最外层同名目录，存在才返回）。

    为何不只跑 smoke：smoke 是**代表层**，新写的单测/门禁常忘标 smoke，
    只看 smoke 会把它们覆盖的代码算成缺失（实测：新写的 MH 检查器只看
    smoke 是 75.3%，把它自己的测试目录一并跑才是真实数）。而跑全量又等于
    全量覆盖率（串行 ~32min），与增量快速反馈的目标相背。按包名定位测试
    目录是两者之间的中点：通常十几秒，且天然含未标 smoke 的新测试。
    """
    targets: list[str] = []
    for pkg in dict.fromkeys(f.split("/")[0] for f in files):
        for dirpath, dirnames, _ in os.walk(os.path.join(_ROOT, "tests")):
            if os.path.basename(dirpath) == pkg:
                targets.append(os.path.relpath(dirpath, _ROOT).replace("\\", "/"))
                dirnames[:] = []  # 取最外层同名目录即可
                break
    return targets


def _run_cov(files: list[str]) -> tuple[dict, str]:
    """对改动文件跑相关测试并返回 (coverage JSON, 实际测试目标描述)。"""
    json_path = os.path.join(tempfile.mkdtemp(prefix="tpc_cov_"), "cov.json")
    targets = _related_tests(files)
    if targets:
        scope = targets
        label = "改动包对应的测试目录：" + " ".join(targets)
    else:
        scope = ["-m", "smoke"]
        label = "回退 smoke 层（未找到与改动包同名的测试目录）"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *scope,
        "-n",
        "0",  # xdist 下每 worker 独立计数会失真（见 pyproject 注释）
        "-q",
        "--no-header",
        # 覆盖 pyproject 的全量阈值：增量场景的总覆盖率天然偏低（只看改动
        # 文件），是否达标由本脚本按文件判定，不能借用全局 fail_under。
        "--cov-fail-under=0",
        *[f"--cov={_module_name(f)}" for f in files],
        f"--cov-report=json:{json_path}",
    ]
    print(f"[info] 统计 {len(files)} 个改动文件 → {' '.join(files)}")
    print(f"[info] 测试范围：{label}")
    proc = subprocess.run(cmd, cwd=_ROOT, capture_output=True, text=True, encoding="utf-8")
    if not os.path.isfile(json_path):
        print("[error] 未生成覆盖率报告——pytest 可能未跑完：")
        print((proc.stdout or "")[-1500:])
        print((proc.stderr or "")[-800:])
        sys.exit(2)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    # coverage JSON 的路径分隔符文平台相关，统一成正斜杠便于比对
    normalized: dict[str, dict] = {}
    for path, info in data.get("files", {}).items():
        normalized[path.replace("\\", "/").lstrip("./")] = info
    return normalized, label


def _coverage_row(f: str, cov: dict) -> tuple[str, float, int, list[int]] | None:
    """单文件覆盖率行 `(文件, 百分比, 语句数, 缺失行)`；报告里没有 → None。"""
    info = _lookup(cov, f)
    if info is None:
        print(f"  [?]    {f}  — 未出现在报告中（本次测试范围未导入该模块？）")
        return None
    summary = info.get("summary", {})
    return (
        f,
        float(summary.get("percent_covered", 0.0)),
        int(summary.get("num_statements", 0)),
        info.get("missing_lines", []) or [],
    )


def _print_rows(rows: list[tuple[str, float, int, list[int]]]) -> None:
    """逐文件覆盖率表（缺失行最多预览 12 个）。"""
    width = max(len(r[0]) for r in rows)
    print()
    print(f"{'文件':<{width}}  覆盖率  语句  缺失行")
    for f, pct, stmts, missing in rows:
        miss_preview = ",".join(str(n) for n in missing[:12])
        if len(missing) > 12:
            miss_preview += f" …(+{len(missing) - 12})"
        print(f"{f:<{width}}  {pct:6.1f}%  {stmts:4d}  {miss_preview}")


def _check_threshold(
    rows: list[tuple[str, float, int, list[int]]], fail_under: float
) -> int:
    """阈值判定 → 退出码（低于阈值逐条列出）。"""
    below = [(f, p) for f, p, _, _ in rows if p < fail_under]
    if below:
        detail = "；".join(f"{f} {p:.1f}%" for f, p in below)
        print(f"[FAIL] 低于阈值 {fail_under:g}%：{detail}")
        return 1
    print(f"[OK] 均不低于阈值 {fail_under:g}%")
    return 0


def _report(files: list[str], cov: dict, fail_under: float | None) -> int:
    """打印每文件覆盖率；返回退出码。"""
    rows = [row for row in (_coverage_row(f, cov) for f in files) if row is not None]

    if not rows:
        print("[warn] 无可用覆盖率数据")
        return 0 if fail_under is None else 1

    _print_rows(rows)
    total = sum(r[1] * r[2] for r in rows) / max(sum(r[2] for r in rows), 1)
    print(f"\n[summary] 改动文件合计覆盖率 {total:.1f}%（语句加权）")
    if fail_under is not None:  # NaN 比较在阈值判定内显式处理
        return _check_threshold(rows, fail_under)
    return 0


def main() -> int:
    cov_cfg = _cov_config()
    sources = [s.rstrip("/") for s in cov_cfg.get("run", {}).get("source", [])]
    default_under = cov_cfg.get("report", {}).get("fail_under")

    ap = argparse.ArgumentParser(description="增量覆盖率自查（改动文件）")
    ap.add_argument("--base", default="HEAD", help="对比基线（默认 HEAD＝工作区改动）")
    ap.add_argument(
        "--fail-under",
        type=float,
        default=None,
        metavar="N",
        help=(
            "低于 N 个百分点即失败（默认只报告不失败；"
            f"全量阈值为 {default_under}）"
        ),
    )
    ap.add_argument("--list", action="store_true", help="只列出改动文件，不跑覆盖率")
    args = ap.parse_args()

    if not sources:
        print("[error] pyproject.toml 未声明 [tool.coverage.run].source")
        return 2
    files = _changed_sources(args.base, sources)
    if not files:
        print(f"[info] 相对 {args.base} 无引擎源码改动 → 无需增量覆盖率")
        return 0
    if args.list:
        for f in files:
            print(f)
        return 0

    cov, _ = _run_cov(files)
    return _report(files, cov, args.fail_under)


if __name__ == "__main__":
    sys.exit(main())

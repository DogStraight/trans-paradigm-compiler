"""tests/perf/run_perf.py — 0.1.5 块 1：性能基线 + ratchet（本地/夜间）。

口径（`tests/perf/README.md` 有完整说明）：
- 场景 = 真实用户路径（check / format），输入 = 仓内真实语料，**不造微基准**；
- 每次运行同时测一个**校准微基准**，场景耗时记为 `ratio = 场景秒 / 校准秒`
  ——以 ratio 立基线，跨机器可比（硬件/解释器整体快慢被约掉）；
- 每个场景 1 次预热 + 3 次取**中位数**；录制基线要求 CV ≤10%，否则拒绝（先稳定再立）；
- `--compare`：场景集合变化 / ratio 劣化 >10% ⇒ exit 1；基线缺失 ⇒ exit 2；
  测量不稳定只告警（避免夜间噪声假红，稳定性由 `--save` 硬门禁保证）。

用法：
    python tests/perf/run_perf.py --save          # 录制/更新基线（需稳定）
    python tests/perf/run_perf.py --compare       # 与基线比（ratchet；夜间/本地）
    python tests/perf/run_perf.py --check-baseline  # 只校验基线文件（秒级）
    python tests/perf/run_perf.py --list-scenarios
Doc: tests/perf/README.md
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = str(ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from core.console import ensure_utf8_stdio  # noqa: E402 — 路径引导之后才可 import

ensure_utf8_stdio()

BASELINE = ROOT / "tools" / "baselines" / "perf_baseline.json"
TOLERANCE = 0.10
CV_LIMIT = 0.10
SCHEMA = 1
CALIBRATION_ITERS = 3_000_000
_CORPUS = ROOT / "tests" / "e2e" / "samples"


@dataclass(frozen=True)
class Scenario:
    """一个性能场景：真实入口 + 真实语料。"""

    name: str
    kind: str  # "check" | "format"
    path: Path
    rules_dir: str = "grammar/verilog"
    include_dirs: tuple[Path, ...] = ()


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("tv80_check", "check", _CORPUS / "real" / "ref" / "ref_tv80_core.v"),
    Scenario("picorv32_check", "check", _CORPUS / "real" / "ref" / "ref_picorv32.v"),
    Scenario("tv80_format", "format", _CORPUS / "real" / "ref" / "ref_tv80_core.v"),
    Scenario(
        "crc32_check",
        "check",
        _CORPUS / "real_c_ref" / "ref" / "crc32.c",
        rules_dir="grammar/c",
        include_dirs=(
            _CORPUS / "real_c_ref" / "ref",
            _CORPUS / "real_c_ref" / "stubs",
        ),
    ),
)


def _calibration_work() -> float:
    """固定浮点/整数混合循环（约 0.2s）；只用于归一化，不含被测代码。"""
    acc = 0
    for i in range(CALIBRATION_ITERS):
        acc = (acc + i * 2654435761) & 0xFFFFFFFF
    return float(acc)


def _time_calibration() -> float:
    started = time.perf_counter()
    _calibration_work()
    return time.perf_counter() - started


def _time_once(scenario: Scenario) -> float:
    """单次场景耗时（秒）；check 走 ProjectChecker，format 走真实 CLI 子进程。"""
    if scenario.kind == "check":
        from analyzer.checker import ProjectChecker

        checker = ProjectChecker(
            rules_dir=scenario.rules_dir,
            ext_dirs=None if scenario.include_dirs else [],
            include_dirs=[str(path) for path in scenario.include_dirs] or None,
        )
        started = time.perf_counter()
        checker.check([str(scenario.path)])
        return time.perf_counter() - started
    started = time.perf_counter()
    subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "format", str(scenario.path)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return time.perf_counter() - started


def _cv(samples: list[float]) -> float:
    """样本变异系数（标准差/均值）；样本不足 2 个 → 1.0（视为不稳定）。"""
    if len(samples) < 2:
        return 1.0
    mean = statistics.mean(samples)
    return statistics.pstdev(samples) / mean if mean else 1.0


def measure_calibration(reps: int = 5) -> float:
    """校准微基准：先 2 次预热（解释器自适应特化/缓存），再取 reps 中位。

    关键：**整轮只测一次**，所有场景共用一个校准值——逐场景重测会把
    "循环冷/热" 混进 ratio（实测：逐场景校准导致同轮 ratio 漂移 30–50%）。
    """
    for _ in range(2):
        _calibration_work()
    return statistics.median([_time_calibration() for _ in range(reps)])


def measure_scenario(scenario: Scenario, reps: int, calibration: float) -> dict:
    """1 次预热 + reps 次测量 → {seconds, ratio, cv, source_bytes}。"""
    _time_once(scenario)  # 预热（文件缓存/模块导入不污染中位数）
    samples = [_time_once(scenario) for _ in range(reps)]
    median = statistics.median(samples)
    return {
        "seconds": round(median, 3),
        "ratio": round(median / calibration, 2) if calibration else 0.0,
        "cv": round(_cv(samples), 3),
        "source_bytes": scenario.path.stat().st_size,
    }


def measure_all(reps: int = 3) -> dict[str, dict]:
    calibration = measure_calibration()
    return {
        scenario.name: measure_scenario(scenario, reps, calibration)
        for scenario in SCENARIOS
    }


def _machine() -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
    }


def load_baseline(path: Path = BASELINE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_names() -> set[str]:
    return {scenario.name for scenario in SCENARIOS}


def validate_baseline(data: dict) -> list[str]:
    """基线结构/场景集完整性校验（--check-baseline 与 policy 测试共用）。"""
    errors: list[str] = []
    if data.get("schema") != SCHEMA:
        errors.append(f"schema={data.get('schema')} != {SCHEMA}")
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        return errors + ["scenarios 缺失或为空"]
    names = set(scenarios)
    if names != expected_names():
        errors.append(f"场景集不一致：基线={sorted(names)} / 代码={sorted(expected_names())}")
    for name, entry in scenarios.items():
        ratio = entry.get("ratio") if isinstance(entry, dict) else None
        if not isinstance(ratio, (int, float)) or ratio <= 0:
            errors.append(f"{name}: ratio 非法（{ratio!r}）")
    return errors


def compare_ratios(
    current: dict[str, float], baseline: dict[str, float], tolerance: float = TOLERANCE
) -> list[str]:
    """ratio 表对比 → 违规列表（空 = 通过）。纯函数，便于单测。"""
    violations: list[str] = []
    for name in sorted(set(baseline) - set(current)):
        violations.append(f"{name}: 基线条目在本次运行中消失（场景被删/失败）")
    for name in sorted(set(current) - set(baseline)):
        violations.append(f"{name}: 新增场景未入基线（先 --save 或删场景）")
    for name in sorted(set(current) & set(baseline)):
        base = baseline[name]
        now = current[name]
        if base <= 0:
            violations.append(f"{name}: 基线 ratio 非法（{base}）")
            continue
        limit = base * (1.0 + tolerance)
        if now > limit:
            violations.append(
                f"{name}: 劣化 {(now / base - 1) * 100:.1f}% "
                f"(基线 {base:.2f} → 本次 {now:.2f}，阈值 {tolerance * 100:.0f}%)"
            )
    return violations


def _ratios(measured: dict[str, dict]) -> dict[str, float]:
    return {name: float(entry["ratio"]) for name, entry in measured.items()}


def _print_table(measured: dict[str, dict], baseline: dict[str, dict] | None = None) -> None:
    print(f"{'场景':<18}{'秒':>9}{'ratio':>10}{'CV':>8}" + ("  基线ratio  变化" if baseline else ""))
    for name, entry in measured.items():
        line = f"{name:<18}{entry['seconds']:>9.2f}{entry['ratio']:>10.2f}{entry['cv']:>8.2f}"
        if baseline:
            base = float(baseline[name]["ratio"]) if name in baseline else 0.0
            change = (float(entry["ratio"]) / base - 1) * 100 if base else 0.0
            line += f"{base:>11.2f}{change:>+9.1f}%"
        print(line)


def _save(args: argparse.Namespace) -> int:
    measured = measure_all(args.reps)
    unstable = [name for name, entry in measured.items() if entry["cv"] > CV_LIMIT]
    if unstable:
        print(f"[FAIL] 测量不稳定（CV > {CV_LIMIT:.0%}）：{unstable}；先稳定环境再 --save")
        return 2
    payload = {
        "schema": SCHEMA,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tolerance": TOLERANCE,
        "cv_limit": CV_LIMIT,
        "reps": args.reps,
        "calibration_iters": CALIBRATION_ITERS,
        "machine": _machine(),
        "scenarios": measured,
    }
    args.baseline.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    _print_table(measured)
    print(f"[saved] {args.baseline}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    if not args.baseline.is_file():
        print(f"[FAIL] 基线不存在：{args.baseline}（先 --save）")
        return 2
    baseline = load_baseline(args.baseline)
    errors = validate_baseline(baseline)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 2
    measured = measure_all(args.reps)
    unstable = [name for name, entry in measured.items() if entry["cv"] > CV_LIMIT]
    if unstable:
        print(f"[warn] 本次测量 CV > {CV_LIMIT:.0%}：{unstable}（median 仍用于对比）")
    _print_table(measured, baseline["scenarios"])
    violations = compare_ratios(_ratios(measured), {
        name: float(entry["ratio"]) for name, entry in baseline["scenarios"].items()
    })
    if violations:
        print("[FAIL] 性能 ratchet：")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("[PASS] 性能基线：比例在容差内，场景集一致")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_perf", description=(__doc__ or "run_perf").splitlines()[0]
    )
    parser.add_argument("--save", action="store_true", help="录制/更新基线")
    parser.add_argument("--compare", action="store_true", help="与基线对比（ratchet）")
    parser.add_argument("--check-baseline", action="store_true", help="只校验基线文件")
    parser.add_argument("--list-scenarios", action="store_true", help="列出场景")
    parser.add_argument("--reps", type=int, default=3, help="每场景测量次数（默认 3）")
    parser.add_argument("--baseline", type=Path, default=BASELINE, help="基线路径")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.list_scenarios:
        for scenario in SCENARIOS:
            print(f"{scenario.name}\t{scenario.kind}\t{scenario.path}")
        return 0
    if args.check_baseline:
        if not args.baseline.is_file():
            print(f"[FAIL] 基线不存在：{args.baseline}")
            return 2
        errors = validate_baseline(load_baseline(args.baseline))
        for error in errors:
            print(f"[FAIL] {error}")
        print("[PASS] 基线结构/场景集完整" if not errors else f"[FAIL] {len(errors)} 项违规")
        return 0 if not errors else 2
    if args.save:
        return _save(args)
    if args.compare:
        return _compare(args)
    print("[FAIL] 需要 --save / --compare / --check-baseline / --list-scenarios 之一")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

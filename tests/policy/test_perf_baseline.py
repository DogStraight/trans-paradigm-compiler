"""0.1.5 块 1 判据：性能基线与 ratchet（只测结构/比较逻辑，不跑重场景）。

被测：`tests/perf/run_perf.py` + `tools/baselines/perf_baseline.json`。
真实计时只在 `--save`/`--compare`/nightly 跑；本文件保证"门禁本身"不腐烂——
基线场景集与代码一致、比较逻辑双向有效、基线缺失/损坏会红。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERF_DIR = ROOT / "tests" / "perf"
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

import run_perf  # noqa: E402  # pyright: ignore[reportMissingImports]


class TestBaselineHealth:
    def test_baseline_structure_and_scenarios(self) -> None:
        data = run_perf.load_baseline()
        assert run_perf.validate_baseline(data) == []
        assert set(data["scenarios"]) == run_perf.expected_names()

    def test_baseline_has_machine_and_ratios(self) -> None:
        data = run_perf.load_baseline()
        assert data["machine"]["python"]
        for name, entry in data["scenarios"].items():
            assert entry["ratio"] > 0, name
            assert entry["cv"] <= data["cv_limit"], name

    def test_check_baseline_cli(self) -> None:
        assert run_perf.main(["--check-baseline"]) == 0

    def test_missing_baseline_exits_2(self, tmp_path: Path) -> None:
        assert run_perf.main(["--compare", "--baseline", str(tmp_path / "none.json")]) == 2


class TestCompareLogic:
    def test_unchanged_passes(self) -> None:
        assert run_perf.compare_ratios({"a": 100.0}, {"a": 100.0}) == []

    def test_within_tolerance_passes(self) -> None:
        assert run_perf.compare_ratios({"a": 105.0}, {"a": 100.0}) == []
        assert run_perf.compare_ratios({"a": 100.0}, {"a": 100.0}, tolerance=0.2) == []

    def test_regression_over_tolerance_fails(self) -> None:
        violations = run_perf.compare_ratios({"a": 111.0}, {"a": 100.0})
        assert len(violations) == 1
        assert "劣化 11.0%" in violations[0]

    def test_new_scenario_fails(self) -> None:
        violations = run_perf.compare_ratios({"a": 100.0, "b": 5.0}, {"a": 100.0})
        assert any("新增场景" in v for v in violations)

    def test_disappeared_scenario_fails(self) -> None:
        violations = run_perf.compare_ratios({"a": 100.0}, {"a": 100.0, "b": 5.0})
        assert any("消失" in v for v in violations)

    def test_invalid_baseline_ratio_fails(self) -> None:
        assert run_perf.compare_ratios({"a": 100.0}, {"a": 0.0})

    def test_cv_helper(self) -> None:
        assert run_perf._cv([2.0, 2.0, 2.0]) == 0.0
        assert run_perf._cv([1.0]) == 1.0
        assert run_perf._cv([1.0, 2.0]) > 0.0

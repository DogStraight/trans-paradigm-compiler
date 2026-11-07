"""INV-RATCHET-NOT-VANISH：基线非空而当前为空必须 FAIL，不得当作「欠账清零」。

为什么有这条（外部证伪 F1，2026-11-07 实测）：`structural_score` 在 bifrost 报表为空时
把基线 78 项全记作「消除」并 exit 0——ratchet 分不清"债还完了"和"量具死了"。同类形状
在 `feature_sites` / `min_pack_probe` / `assert_strength` 上一样成立，故判据抽到
`tools/_ratchet.py` 单一实现，并由本文件**逐条驱动**（不是只测 helper）。

判据：基线项集合非空、当前为空 ⇒ exit 2 + 消息带「基线 N 项」；真要归零走 `--save`/`--record`。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for extra in (str(ROOT / "tools"), str(ROOT / "tests" / "policy")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import _ratchet  # noqa: E402  # pyright: ignore[reportMissingImports]
import feature_sites  # noqa: E402  # pyright: ignore[reportMissingImports]
import min_pack_probe  # noqa: E402  # pyright: ignore[reportMissingImports]
import structural_score  # noqa: E402  # pyright: ignore[reportMissingImports]
import test_assert_strength as tas  # noqa: E402

#: 本文件必须真的驱动了这么多个 ratchet 入口（防"测试自己变成空壳"）。
EXPECTED_DRIVEN = 4


def test_guard_allows_nonempty_and_first_baseline() -> None:
    """非空当前集合、以及基线本身为空（首次建立）都返回 0。"""
    assert _ratchet.guard_not_vanished("x", 5, 3) == 0
    assert _ratchet.guard_not_vanished("x", 0, 0) == 0
    assert _ratchet.guard_not_vanished("x", 7, 0) == 2


def test_structural_score_empty_score_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    """量具一项都没产出、基线有项 → exit 2 + 消息点名「基线 N 项 / 当前 0 项」。"""
    assert structural_score._compare(ROOT, structural_score._Score()) == 2
    err = capsys.readouterr().err
    assert "基线有" in err and "当前 0 项" in err, f"消息太空泛：{err!r}"


def test_feature_sites_vanished_instances_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """当前 instances 全空、基线非空 → exit 2 + 消息点名基线项数。"""
    assert feature_sites.cmd_compare({}) == 2
    err = capsys.readouterr().err
    assert re.search(r"基线有 \d+ 项", err), f"消息太空泛：{err!r}"


def test_min_pack_probe_vanished_passed_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """基线记着若干"仍绿"的测试、本次一个都没有 → exit 2。"""
    baseline = tmp_path / "min_pack_baseline.json"
    baseline.write_text(
        json.dumps(
            {"pack": "grammar/yaml", "targets": list(min_pack_probe._TARGET_DEFAULT),
             "passed": ["tests/engine/a.py::test_x", "tests/engine/b.py::test_y"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def _empty(*_args, **_kwargs) -> dict:
        return {"pack": "grammar/yaml", "targets": list(min_pack_probe._TARGET_DEFAULT),
                "passed": [], "failed": {}, "errored": {}}

    monkeypatch.setattr(min_pack_probe, "run_probe", _empty)
    assert min_pack_probe.main(["--baseline", str(baseline)]) == 2
    err = capsys.readouterr().err
    assert "基线有 2 项" in err and "当前 0 项" in err, f"消息太空泛：{err!r}"


def test_min_pack_compare_without_baseline_fails_fast(tmp_path: Path) -> None:
    """`--compare` 是严格模式：缺基线直接 exit 2（且不白跑一轮分钟级探针）。"""
    missing = tmp_path / "no_such_baseline.json"
    assert min_pack_probe.main(["--compare", "--baseline", str(missing)]) == 2


def test_assert_strength_zero_asserts_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """断言总数塌到 0（扫描面失效）→ ratchet 用例必须红，且消息点名基线项数。"""
    empty = {"files": 279, "tests": 0, "asserts": 0, "weak": 0, "parse_errors": 0,
             "truthiness": 0, "nonempty": 0, "nullness": 0}
    monkeypatch.setattr(tas, "scan", lambda _root: empty)
    with pytest.raises(AssertionError) as exc:
        tas.test_repo_strict_weak_ratio_within_ratchet()
    assert "基线有" in str(exc.value) and "当前 0 项" in str(exc.value), (
        f"消息太空泛：{exc.value}"
    )


def test_every_ratchet_is_wired_to_the_guard() -> None:
    """防假绿：四个入口的源码里必须真的调同一个 helper（删掉接线就红）。

    这比"测试文件自己数了几个名字"有效——数名字是自证的，查接线才是在查实现。
    """
    wired = (
        "tools/structural_score.py",
        "tools/feature_sites.py",
        "tools/min_pack_probe.py",
        "tests/policy/test_assert_strength.py",
    )
    missing = [
        rel for rel in wired
        if "_ratchet.guard_not_vanished" not in (ROOT / rel).read_text(encoding="utf-8")
    ]
    assert not missing, f"这些入口没接 ratchet 判据：{missing}"
    assert len(wired) == EXPECTED_DRIVEN

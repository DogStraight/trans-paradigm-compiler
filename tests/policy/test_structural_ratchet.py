"""结构欠账分（ratchet）的 fail-closed 判据。

背景（审计 2026-11-07 外部证伪 F1）：`structural_score.py --compare` 在 bifrost
报表为空串时把基线全部项记作「消除」并 exit 0——ratchet 分不清「债还完了」与
「量具死了」。两条 fail-closed 判据：

1. `_bifrost`：退出码非 0 / JSON 结构不对 / report 为空串 → SystemExit（不返回空串）；
2. `_compare`：基线有项、当前量具 0 项 = 全量消失 → 退出码 2（不是 0）。

同时钉住"正常路径不误伤"：报表有内容时照常返回；当前项与基线一致时照常 exit 0。
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tools"))

import structural_score as ss  # noqa: E402  # pyright: ignore[reportMissingImports]


def _fake_run(returncode: int, stdout: str, stderr: str = ""):
    """替身：与 subprocess.run 同形的返回对象。"""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _report_stdout(report: str) -> str:
    return json.dumps({"structuredContent": {"report": report}})


def test_bifrost_rejects_empty_report(monkeypatch):
    """F1：report 为空串 = 量具没产出口径，必须 FAIL 而不是返回空报表。"""
    monkeypatch.setattr(
        ss.subprocess,
        "run",
        lambda *a, **k: _fake_run(0, _report_stdout("")),
    )
    with pytest.raises(SystemExit, match="报表为空"):
        ss._bifrost(Path("."), "compute_cyclomatic_complexity", {})


def test_bifrost_rejects_nonzero_exit(monkeypatch):
    """F1：外部工具退出码非 0 必须 FAIL（不许把失败当零命中）。"""
    monkeypatch.setattr(
        ss.subprocess,
        "run",
        lambda *a, **k: _fake_run(2, "", "boom"),
    )
    with pytest.raises(SystemExit, match="退出码 2"):
        ss._bifrost(Path("."), "report_structural_clone_smells", {})


def test_bifrost_returns_non_empty_report(monkeypatch):
    """正常路径：无命中的规范报表（`No ... met`）照常返回。"""
    text = "No structural clone smells met minScore 90."
    monkeypatch.setattr(
        ss.subprocess,
        "run",
        lambda *a, **k: _fake_run(0, _report_stdout(text)),
    )
    assert ss._bifrost(Path("."), "report_structural_clone_smells", {}) == text


def test_compare_all_items_gone_fails_closed(monkeypatch):
    """F1：基线有项、当前 0 项 = 全量消失，退出码 2（不许 0 假绿）。"""
    base = {"total": 5, "components": {}, "items": {"CC|pkg/mod.py:f": 5}}
    monkeypatch.setattr(ss, "_load_baseline", lambda root: base)
    rc = ss._compare(Path("."), ss._Score())
    assert rc == 2


def test_compare_with_measurement_still_green(monkeypatch):
    """正常路径：当前项与基线一致时照常 0（不得把 guard 误伤成常红）。"""
    base = {"total": 5, "components": {}, "items": {"CC|pkg/mod.py:f": 5}}
    monkeypatch.setattr(ss, "_load_baseline", lambda root: base)
    score = ss._Score(items=[ss._Item("CC", "pkg/mod.py:f", 5)])
    assert ss._compare(Path("."), score) == 0

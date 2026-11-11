"""D10 kept 基线门禁：`scan_redundant_code` 的基线必须等于现实，且判定双向有效。

背景（作者 2026-11-11 选方案 A）：D10 逐条裁定 10 条候选 → 8 条刻意保持、2 条真死
形参删除。刻意保持项进 `tools/baselines/redundant_code_kept.json`（键
`<relpath>::<R1|R2|R3>:<符号>`，值必须有非空 `reason`）。

锁四件事（缺一条基线就退化成"红着没人看"）：
1. 基线集合 == 实跑集合（出现新候选 = 回归；条目消失 = 基线腐化）；
2. 每条基线有实质理由（空理由就是白名单）；
3. 反向演练：往基线塞一条不存在的项 ⇒ 判定必须红（证明"基线失效"方向有牙）；
4. 探针被绕过（基线非空、当前 0 条）⇒ exit 2（`_ratchet.guard_not_vanished`）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import scan_redundant_code as tool  # noqa: E402  # pyright: ignore[reportMissingImports]

BASELINE = ROOT / "tools" / "baselines" / "redundant_code_kept.json"


def _items() -> dict[str, dict]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["items"]


def _live_keys() -> set[str]:
    files = tool._collect_files([Path("linter"), Path("parser")])
    findings = [finding for path in files for finding in tool.scan_file(path)]
    return {tool._finding_key(finding) for finding in findings}


def test_baseline_matches_reality() -> None:
    """基线集合 == 实跑集合（新候选 / 过期条目都算漂移）。"""
    assert set(_items()) == _live_keys(), (
        "kept 基线与现实不一致：新候选请修或登记理由；已修好的条目请同提交删除"
    )


def test_every_entry_has_reason() -> None:
    """每条必须有实质理由（空理由 = 白名单，等于没判）。"""
    bad = {
        key: meta
        for key, meta in _items().items()
        if not str(meta.get("reason") or "").strip()
    }
    assert not bad, f"以下 kept 条目缺 reason：{sorted(bad)}"


def test_strict_is_green_with_baseline() -> None:
    """`--strict` 在基线与现实一致时必须 exit 0（否则 CI 永远红）。"""
    assert tool.main(["--strict"]) == 0


def test_ghost_entry_is_red(tmp_path: Path, capsys) -> None:
    """反向演练：基线里塞一条不存在的项 ⇒ exit 1 且明确报"基线失效"。"""
    data = {"owner": "D10", "items": dict(_items())}
    data["items"]["ghost/file.py::R1:ghost_symbol"] = {
        "reason": "反向演练用假条目",
        "evidence": "不存在于实跑集合",
        "owner": "D10",
    }
    ghost = tmp_path / "ghost.json"
    ghost.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    rc = tool.main(["--baseline", str(ghost)])
    out = capsys.readouterr().out
    assert rc == 1, f"假条目未让门禁变红（rc={rc}）"
    assert "基线失效" in out and "ghost/file.py" in out


def test_vanished_baseline_exits_2(tmp_path: Path, capsys) -> None:
    """反向演练：基线非空、当前扫描 0 条 ⇒ exit 2（防探针被绕过）。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = tool.main(["--paths", str(empty), "--baseline", str(BASELINE)])
    assert rc == 2, f"全量消失未按 exit 2 处理（rc={rc}）"
    assert "全量消失" in capsys.readouterr().err

"""功能散点登记表门禁——**不跑扫描**（计量是分钟级工具，按需人工跑）。

守两件事（对应 `policy/structural_budget.md` R6「判保持要登记」的同一哲学）：

1. **基线覆盖全部功能族**：`tools/feature_sites_baseline.json` 里的族集合 ==
   `tools/feature_sites.py::FAMILIES` 的族集合——新增一族却忘了 `--save`，
   该族就会**静默不设防**（"没看"被当成"没问题"）。
2. **判保持必须可审计**：`tools/feature_sites_kept.json` 每条要有非空 `reason` 与非空
   `source`，且键指向基线里**真实存在**的 `family:instance`——否则等于把欠账洗掉。

⚠ 本测试**不**断言"散点数"（那是 `--compare` 的活，属按需门禁）：
口径见 `docs/gaps/gap-feature-scatter.md`。

Doc: docs/gaps/gap-feature-scatter.md
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tools" / "feature_sites_baseline.json"
KEPT = ROOT / "tools" / "feature_sites_kept.json"
CONVERGED = ROOT / "tools" / "feature_sites_converged.json"


def _load(path: Path) -> dict:
    assert path.exists(), f"{path.relative_to(ROOT)} 不存在（先跑 tools/feature_sites.py --save）"
    return json.loads(path.read_text(encoding="utf-8"))


def _family_names() -> set[str]:
    """从工具源码取族名（不 import——工具是脚本，避免它 import 期的副作用）。"""
    import re

    text = (ROOT / "tools" / "feature_sites.py").read_text(encoding="utf-8")
    block = text.split("FAMILIES: dict[str, dict] = {", 1)[1].split("\n}", 1)[0]
    return set(re.findall(r'^    "([a-z_]+)":', block, re.M))


def test_baseline_covers_every_family():
    """基线的族集合必须与工具声明的族集合一致（新增族必须重记基线）。"""
    base = _load(BASELINE)["families"]
    declared = _family_names()
    assert declared, "未从工具源码解析出任何族——解析锚点可能已失效"
    missing = declared - set(base)
    assert not missing, f"基线缺族 {sorted(missing)}——新增族后须 `--save` 重记"
    extra = set(base) - declared
    assert not extra, f"基线有多余族 {sorted(extra)}——族已删则须 `--save` 重记"


def test_every_family_has_summary_and_instances():
    for fam, data in _load(BASELINE)["families"].items():
        assert data.get("instances"), f"族 {fam} 无实例（枚举锚点可能已失效）"
        summary = data["summary"]
        for key in ("instances", "scatter_total", "budget"):
            assert key in summary, f"族 {fam} 摘要缺 {key}"


@pytest.mark.parametrize("entry", sorted(_load(KEPT).get("kept", {}).items()))
def test_kept_entries_are_auditable(entry):
    """每条判保持：键指向真实实例 + reason/source 非空。"""
    key, meta = entry
    base = _load(BASELINE)["families"]
    fam, _, inst = key.partition(":")
    assert fam in base, f"判保持条目 {key} 的族不存在于基线"
    assert inst in base[fam]["instances"], f"判保持条目 {key} 的实例不存在于基线"
    for field in ("reason", "source"):
        assert str(meta.get(field, "")).strip(), f"判保持条目 {key} 缺 {field}"


def _converged() -> dict:
    if not CONVERGED.exists():
        return {}
    return json.loads(CONVERGED.read_text(encoding="utf-8")).get("converged", {})


@pytest.mark.parametrize("entry", sorted(_converged().items()))
def test_converged_entries_are_auditable(entry):
    """每个『已收敛』登记点必须：文件真实存在 + reason/source 非空 + source 指向的门禁存在。

    这是**反向防滥用**：把欠账洗成"已收敛"只要写一行 JSON，故要求 source 落在
    一个**真实存在的测试文件**上——收敛声明必须可点开验证（口径同
    `policy/structural_budget.md` R6：判保持要登记理由与出处）。
    """
    path, meta = entry
    assert (ROOT / path).exists(), f"已收敛条目 {path} 指向的文件不存在"
    for field in ("reason", "source"):
        assert str(meta.get(field, "")).strip(), f"已收敛条目 {path} 缺 {field}"
    gate = str(meta["source"]).split("::", 1)[0]
    assert (ROOT / gate).exists(), f"已收敛条目 {path} 的 source 门禁不存在：{gate}"


def test_converged_paths_are_actually_counted_out():
    """写进收敛表的路径必须真的出现在基线里（否则是空转登记）。"""
    base = _load(BASELINE)["families"]
    counted: set[str] = set()
    for fam in base.values():
        for inst in fam["instances"].values():
            counted.update(inst.get("converged", []))
    for path in _converged():
        assert path in counted, f"已收敛条目 {path} 未在任何族的收敛点里出现（空转登记）"

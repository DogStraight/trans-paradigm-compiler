"""policy/check_invariants.py 自测：不变量清单门禁的有效性 + 真实仓库回归。

为什么需要它（enumeration-illusion-audit 的教训）：把"该证伪什么"变成数据后，
数据会腐烂——规则/测试被删，清单却仍指向旧锚点，"我们只检查这 N 条"就退化成
"这 N 条里有几条没人管"。本文件锁两件事：
1. **锚点失效必红**（注入坏锚点 → 门禁报错），证明门禁不是摆设；
2. 真实仓库清单可解析（回归）。
Doc: docs/invariants.toml
"""

import importlib.util
import sys
import tomllib
from pathlib import Path

_CHECKER = Path(__file__).resolve().parent.parent.parent / "policy" / "check_invariants.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_invariants", _CHECKER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


checker = _load()
ROOT = Path(__file__).resolve().parent.parent.parent


def _write_manifest(tmp_path: Path, body: str) -> None:
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "invariants.toml").write_text(body, encoding="utf-8")


def _minimal(**over) -> str:
    item = {
        "id": "INV-TEST",
        "statement": "这是一条足够长的可证伪断言（测试夹具）",
        "violation": "违反形态：注入一个可以观察到的错误行为",
        "observable": "观察方式：运行门禁并断言它变红而不是通过",
        "verification": "procedural",
        "manual_check": "人工核对 diff 里新增分支是否对应新形态",
        "known_pass": "夹具自身成立；当前实现下该断言为真",
    }
    item.update(over)
    lines = ["[[invariant]]"]
    for k, v in item.items():
        lines.append(f'{k} = "{v}"')
    return "\n".join(lines)


# ── 有效锚点解析（真实仓库）──────────────────────────────────────

def test_real_manifest_is_clean() -> None:
    """真实清单：字段齐全、id 唯一、锚点全部可解析。"""
    rep = checker.collect(ROOT)
    assert rep.issues == [], [f"{i.invariant}.{i.field}: {i.message}" for i in rep.issues]
    assert len(rep.invariants) >= 3
    assert rep.mechanized >= 1, "至少要有一条可判定不变量（否则清单只是口号集合）"


def test_every_invariant_is_falsifiable_in_shape() -> None:
    """每条都必须写清「违反长什么样」+「怎么观察」，且二者不得雷同。"""
    data = tomllib.loads((ROOT / "docs" / "invariants.toml").read_text(encoding="utf-8"))
    for it in data["invariant"]:
        assert it["violation"].strip() != it["statement"].strip(), it["id"]
        assert len(it["observable"].strip()) >= 12, it["id"]


# ── 反例：锚点失效/字段缺失必须变红（证明门禁有效）──────────────

def test_stale_test_anchor_is_rejected(tmp_path: Path) -> None:
    _write_manifest(tmp_path, _minimal(
        verification="mechanized",
        gate="tests/policy/test_nope.py::test_missing",
        violation_probe="tests/policy/test_nope.py::test_missing",
    ).replace('manual_check = "人工核对 diff 里新增分支是否对应新形态"\n', ""))
    rep = checker.collect(tmp_path)
    assert any("不存在" in i.message or "不在" in i.message for i in rep.issues)


def test_stale_policy_rule_anchor_is_rejected(tmp_path: Path) -> None:
    # 用一个真实存在的脚本 + 不存在的规则 id
    _write_manifest(tmp_path, _minimal(
        verification="mechanized",
        gate="policy/check_hardcode.py#R999",
        violation_probe="policy/check_hardcode.py#R999",
    ).replace('manual_check = "人工核对 diff 里新增分支是否对应新形态"\n', ""))
    # 夹具树里没有 policy/check_hardcode.py → 应报"脚本不存在"
    rep = checker.collect(tmp_path)
    assert rep.issues, "坏锚点必须被拒绝"
    assert any("不存在" in i.message for i in rep.issues)


def test_stale_mutation_index_is_rejected(tmp_path: Path) -> None:
    _write_manifest(tmp_path, _minimal(
        verification="mechanized",
        gate="tools/check_gate_efficacy.py#9999",
        violation_probe="tools/check_gate_efficacy.py#9999",
    ).replace('manual_check = "人工核对 diff 里新增分支是否对应新形态"\n', ""))
    rep = checker.collect(tmp_path)
    assert rep.issues


def test_mechanized_without_probe_is_rejected(tmp_path: Path) -> None:
    """mechanized 但没给 violation_probe → 拒绝（否则"门禁存在"≠"门禁会响"）。"""
    body = _minimal(verification="mechanized", gate="docs/invariants.toml#x")
    body = body.replace('manual_check = "人工核对 diff 里新增分支是否对应新形态"\n', "")
    _write_manifest(tmp_path, body)
    rep = checker.collect(tmp_path)
    assert any(i.field == "violation_probe" for i in rep.issues)


def test_procedural_without_manual_check_is_rejected(tmp_path: Path) -> None:
    body = _minimal()
    body = body.replace('manual_check = "人工核对 diff 里新增分支是否对应新形态"\n', "")
    _write_manifest(tmp_path, body)
    rep = checker.collect(tmp_path)
    assert any(i.field == "manual_check" for i in rep.issues)


def test_duplicate_id_and_same_statement_are_rejected(tmp_path: Path) -> None:
    one = _minimal()
    two = _minimal()
    _write_manifest(tmp_path, one + "\n\n" + two)
    rep = checker.collect(tmp_path)
    assert any(i.field == "id" and "重复" in i.message for i in rep.issues)
    same = _minimal(violation="这是一条足够长的可证伪断言（测试夹具）")
    _write_manifest(tmp_path, same)
    rep2 = checker.collect(tmp_path)
    assert any(i.field == "violation" and "雷同" in i.message for i in rep2.issues)


def test_main_returns_nonzero_on_bad_manifest(tmp_path: Path) -> None:
    body = _minimal(verification="mechanized", gate="bogus", violation_probe="bogus")
    _write_manifest(tmp_path, body)
    assert checker.main(["--root", str(tmp_path), "--quiet"]) == 1

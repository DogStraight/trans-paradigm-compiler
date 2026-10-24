"""审计维度注册表门禁：防"todo 黑洞"与"没探针就宣布关闭"。

规则（对应 policy/audit_loop.md）：
  R1 每条维度必须有 id / name / origin / closure / status
  R2 id 唯一且形如 D<N>
  R3 probe = "todo" 必须有 trigger（否则是"以后再说"的黑洞）
  R4 status = "closed" 必须有真实探针（无探针不得宣布关闭）
  R5 probe 指向的脚本必须存在（防锚点腐烂）
  R6 新增维度必须声明 origin（user / agent），便于回溯"谁想到的"
Doc: policy/audit_loop.md
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY = ROOT / "docs" / "audit_dimensions.toml"
REQUIRED = ("id", "name", "origin", "closure", "status")
TODO = "todo"


def _dims() -> list[dict]:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8")).get("dimension", [])


def test_registry_is_wellformed() -> None:
    dims = _dims()
    assert dims, "注册表为空"
    seen = set()
    for d in dims:
        for f in REQUIRED:
            assert d.get(f), f"{d.get('id')} 缺 {f}"
        assert re.fullmatch(r"D\d+", d["id"]), d["id"]
        assert d["id"] not in seen, f"重复 id: {d['id']}"
        seen.add(d["id"])
        assert d["origin"] in ("user", "agent"), (d["id"], d["origin"])
        assert d["status"] in ("open", "closed"), (d["id"], d["status"])


def test_todo_dimensions_have_trigger() -> None:
    for d in _dims():
        if d.get("probe") == TODO:
            assert d.get("trigger"), f"{d['id']} 标 todo 却没有 trigger（黑洞）"


def test_closed_dimensions_have_real_probe() -> None:
    for d in _dims():
        if d["status"] == "closed":
            assert d.get("probe", TODO) != TODO, (
                f"{d['id']} 无探针却标 closed——不允许"
            )


def test_probe_scripts_exist() -> None:
    for d in _dims():
        probe = d.get("probe", TODO)
        if probe == TODO:
            continue
        for token in probe.split():
            if token.endswith(".py"):
                assert (ROOT / token).is_file(), f"{d['id']} 探针脚本不存在: {token}"


def test_every_dimension_states_a_closure() -> None:
    """closure 必须能判断'关没关'——太短的就是口号。"""
    for d in _dims():
        assert len(d["closure"].strip()) >= 12, d["id"]

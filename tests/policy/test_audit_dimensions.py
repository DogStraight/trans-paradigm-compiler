"""审计维度注册表门禁：防"todo 黑洞"与"没探针就宣布关闭"。

规则（对应 policy/collaboration.md「审计维度轮」）：
  R1 每条维度必须有 id / name / origin / closure / status
  R2 id 唯一且形如 D<N>
  R3 probe = "todo" 必须有 trigger（否则是"以后再说"的黑洞）
  R4 status = "closed" 必须有真实探针（无探针不得宣布关闭）
  R5 probe 指向的脚本必须存在（防锚点腐烂）
  R6 新增维度必须声明 origin（user / agent），便于回溯"谁想到的"
Doc: policy/collaboration.md
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY = ROOT / "docs" / "audit_dimensions.toml"
REQUIRED = ("id", "name", "origin", "closure", "status")
TODO = "todo"
ADHOC = "adhoc"  # 每次现写的探针（作者 2026-10-24 定：不入库，避免堆积失效探针）


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


def test_adhoc_dimensions_declare_recipe() -> None:
    """ad-hoc 探针：不要求入库实现，但必须写清"每次怎么现写"，否则等于没有探针。"""
    for d in _dims():
        if d.get("probe") == ADHOC:
            assert len(d.get("adhoc", "").strip()) >= 12, f"{d['id']} 缺 adhoc 配方"
            assert d.get("trigger"), f"{d['id']} 标 adhoc 却没有 trigger"


def test_closed_dimensions_have_real_probe() -> None:
    for d in _dims():
        if d["status"] == "closed":
            assert d.get("probe", TODO) not in (TODO, ADHOC), (
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


def test_every_dimension_declares_proxy_and_invalidation() -> None:
    """探针是代理不是本体：必须写清"代理哪条性质"和"什么变化会让它失效"。

    没有这两项的探针会安静腐化——被闭开原则淘汰后仍照常返回 PASS（假绿），
    比没有探针更危险。这两项也是每轮开局人工复核（collaboration.md）的输入。
    """
    for d in _dims():
        assert len(d.get("proxies", "").strip()) >= 12, f"{d['id']} 缺 proxies"
        assert len(d.get("invalidated_if", "").strip()) >= 12, f"{d['id']} 缺 invalidated_if"


def test_every_dimension_states_a_closure() -> None:
    """closure 必须能判断'关没关'——太短的就是口号。"""
    for d in _dims():
        assert len(d["closure"].strip()) >= 12, d["id"]


# ── 槽位化（可插拔管线）──────────────────────────────────────────

def _pipeline() -> list[dict]:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8")).get("pipeline", [])


def test_pipeline_slots_are_legal() -> None:
    """槽位三态：file（路径必须存在）/ external（外部能力）/ todo（必须带 trigger）。"""
    slots = _pipeline()
    assert slots, "pipeline 为空——制度必须声明槽位"
    seen = set()
    for s in slots:
        assert s.get("slot"), "槽位缺 slot 名"
        assert s["slot"] not in seen, f"重复槽位: {s['slot']}"
        seen.add(s["slot"])
        assert isinstance(s.get("enabled"), bool), f"{s['slot']} 的 enabled 必须是布尔"
        assert s.get("purpose"), f"{s['slot']} 缺 purpose"
        kind = s.get("impl_kind")
        assert kind in ("file", "external", "todo"), (s["slot"], kind)
        if kind == "file":
            assert (ROOT / s["impl"]).is_file(), f"{s['slot']} 实现不存在: {s['impl']}"
        elif kind == "todo":
            assert s.get("trigger"), f"{s['slot']} 是空槽却无 trigger（黑洞）"


def test_disabled_slots_are_not_deleted() -> None:
    """卸载 = enabled 翻转，槽位仍在册（禁止用删除表达"当前不需要"）。"""
    slots = _pipeline()
    assert all("slot" in s for s in slots)
    assert any(not s["enabled"] for s in slots), (
        "至少要有一个留白槽位——制度应可插拔，而不是只有全开一种状态"
    )


def test_goals_have_evidence() -> None:
    """闭合目标：met=true 必须附证据，且证据指向的文件存在（外部能力除外）。"""
    goals = tomllib.loads(REGISTRY.read_text(encoding="utf-8")).get("goal", [])
    assert goals, "必须声明本版闭合目标"
    for g in goals:
        assert g.get("id") and g.get("statement"), g
        if g.get("met"):
            ev = g.get("evidence", "").strip()
            assert ev, f"{g['id']} 标 met 却无证据"
            assert (ROOT / ev).exists(), f"{g['id']} 证据不存在: {ev}"

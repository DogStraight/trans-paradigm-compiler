"""覆盖门禁：引擎包内所有模块级/类级可变全局必须登记（或规则化覆盖）。

背景：`core/global_state.py` 的覆盖曾是**手工表**——新增全局态静默漏登记 →
测试顺序敏感（幽灵 flake：全量并行偶现、串行不复现）。本门禁把"记得登记"
变成红：`发现集 - 登记集 - 规则化覆盖` 非空即失败。

登记选择（四张表，见 `core/global_state.py` 模块 docstring）：
    TRACKED            测试级状态（每个测试结束还原）
    INSTALL_STATE      语言安装态（模块结束还原：模块 fixture 合法拥有它）
    CONTENT_ADDRESSED  键 = 输入，同参结果恒定（可跨测试保留）
    CONSTANT           字面量常量（若被改写即缺陷）
    COVERED_ELSEWHERE  由 snapshot/restore 定制逻辑覆盖
"""

import pytest

from core.global_state import (
    CONSTANT,
    CONTENT_ADDRESSED,
    COVERED_ELSEWHERE,
    INSTALL_STATE,
    TRACKED,
    _split_target,
    assert_clean,
    discover_mutable_globals,
    restore,
    snapshot,
    unregistered_globals,
)

pytestmark = pytest.mark.smoke


def test_no_unregistered_globals():
    """引擎包内每个可变全局都在登记表里（新增不登记即红）。"""
    missing = unregistered_globals()
    assert not missing, (
        "发现未登记的模块级/类级可变全局（新增全局态必须登记，否则测试顺序"
        "敏感会复发）：\n  " + "\n  ".join(missing)
        + "\n按性质选表：常量→CONSTANT；键=输入的缓存→CONTENT_ADDRESSED；"
        "其余状态→TRACKED（并确认策略：deepcopy/ref/clear/clear-new/truncate）"
    )


def test_registered_entries_resolvable():
    """登记表条目可解析（防改名后登记表悬空——名称漂移当场红）。"""
    bad: list[str] = []
    for table in (TRACKED, INSTALL_STATE, CONTENT_ADDRESSED, COVERED_ELSEWHERE, CONSTANT):
        for name in table:
            try:
                owner, attr = _split_target(name)
                getattr(owner, attr)
            except Exception as exc:  # noqa: BLE001 — 任一异常都算悬空
                bad.append(f"{name}（{exc}）")
    assert not bad, "登记表条目无法解析：\n  " + "\n  ".join(bad)


def test_tiers_are_disjoint():
    """两层还原表互斥（同一对象不能既是测试级又是安装态，否则语义矛盾）。"""
    overlap = set(TRACKED) & set(INSTALL_STATE)
    assert not overlap, f"条目同时登记在两层：{sorted(overlap)}"


def test_discovery_finds_known_state():
    """发现机制本身有效（抽样断言已知状态在发现集内）。"""
    found = set(discover_mutable_globals())
    for name in (
        "parser.pratt_parser._atom_name_map",
        "transform.engine.AstTransformer._shared_ctx",
        "linter.checkers.expression.ExpressionChecker._DEPTH",
        "pipeline._PIPELINE_SHARED",
    ):
        assert name in found, f"{name} 未被扫描到（发现机制退化）"


@pytest.mark.parametrize(
    "name, mutate",
    [
        ("parser.pratt_parser._atom_name_map", {"__leak__": "X"}),
        ("parser._production._prod_feat_cache", {"__leak__": {"x": 1}}),
        ("transform.engine.AstTransformer._shared_ctx", {"__leak__": 1}),
        ("renderer.doc._LAYOUT_CACHE", {(1, 2): 3}),
        ("transform.engine._plugin_index", {"__leak__": None}),
    ],
)
def test_restore_covers_tracked_entries(name, mutate):
    """两层登记表的各策略真实生效：写入后全量 restore 回到基线。"""
    owner, attr = _split_target(name)
    base = snapshot()

    container = getattr(owner, attr)
    container.update(mutate)

    restore(base)
    after = getattr(owner, attr)
    for key in mutate:
        assert key not in after, f"{name} 还原失败：{key} 仍在"


def test_assert_clean_detects_value_only_leak():
    """只改值不改键的泄漏也能检出（_DEPTH 类计数器是典型幽灵来源）。"""
    base = snapshot()
    from linter.checkers.expression import ExpressionChecker

    ExpressionChecker._DEPTH["n"] = 7
    with pytest.raises(AssertionError, match="_DEPTH"):
        assert_clean(base)


def test_assert_clean_passes_on_baseline():
    """基线自身是干净的（每个测试开始前断言的前提）。"""
    assert_clean(snapshot())

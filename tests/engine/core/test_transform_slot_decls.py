"""tests/engine/core/test_transform_slot_decls.py — 槽位契约声明（0.1.2 5b-3c-1）。

槽位从"桥内硬编码触发"走向**声明式**：`[[transform.slots]]` 声明触发节点
（`on`）/ 遍历形态（`walk`）/ ctx 来源（`ctx`）/ 结果接回（`result`）；
**时点不在此声明**（归 `[pipeline.units.*]`）。报告面的执行 = 引擎
`SlotRunnerPlugin`（`transform/slot_runner.py`）——组件不再需要自己的桥插件。
"""

import re
import tomllib
from pathlib import Path

import pytest

from core.plugin_loader import (
    _load_transform_ctx_channels,
    _load_transform_slot_decls,
    register_transform_slot,
)

_ROOT = Path(__file__).resolve().parents[3]
_TP_DIR = _ROOT / "grammar" / "verilog" / "plugins" / "typed_ports"
_TOML = _TP_DIR / "tpc.toml"
_HANDLERS = _TP_DIR / "_transform.py"

# 校验逻辑测试用的探针槽位名（不动真实槽位注册面）
PROBE = "test_slot_decl_probe"
_TOML_RAW = tomllib.loads(_TOML.read_text(encoding="utf-8"))
_DECLARED = {d["name"]: d for d in _TOML_RAW["transform"]["slots"]}


@pytest.fixture
def probe_slot() -> str:
    """注册一个探针槽位（测后还原注册面）。

    真实槽位需组件加载才注册，而测试基建的全局状态还原会移除
    "基线后新增"键、组件模块又在 `sys.modules` 缓存里不重 exec
    —— 故本文件不依赖组件加载链：直接解析 TOML 验真实声明，
    校验逻辑用探针槽位。
    """
    from core import plugin_loader

    def _fn(node, ctx):  # noqa: ANN001, ANN201
        return node

    slots = plugin_loader._transform_slots
    had = PROBE in slots
    prev = slots.get(PROBE)
    register_transform_slot(PROBE)(_fn)
    yield PROBE
    if had:
        slots[PROBE] = prev
    else:
        slots.pop(PROBE, None)


def test_toml_declares_four_slots_with_contract() -> None:
    assert set(_DECLARED) == {
        "build_wrapper",
        "delete_type_decl",
        "auto_connect_ports",
        "replace_impl_binding",
    }
    bw = _DECLARED["build_wrapper"]
    assert bw["on"] == "TypeDecl"
    assert bw["walk"] == "top"
    assert bw["result"] == "extra"
    assert bw["ctx"] == {"type_decl": "$node", "impl_block": "TypeImplDecl"}

    ric = _DECLARED["replace_impl_binding"]
    assert ric["on"] == ["ImplBinding", "ImplBindingWithInterface"]
    assert ric["walk"] == "recursive"
    assert ric["result"] == "replace"


def test_declared_slots_match_registered_handlers() -> None:
    """防漂移：TOML 声明的槽位名 == `_transform.py` 注册的槽位名集合。"""
    src = _HANDLERS.read_text(encoding="utf-8")
    registered = set(re.findall(r'@register_transform_slot\("([^"]+)"\)', src))
    assert registered == set(_DECLARED)


def test_typed_ports_declares_ctx_channel() -> None:
    """ctx 通道声明（type_map 的构造方式在语言包，引擎不认识 kind/attr 语义）。"""
    chans = _load_transform_ctx_channels("test-cdir", _TOML_RAW["transform"])
    assert chans == {"type_map": {"symbol_kind": "typed_port", "attr": "type_name"}}


def test_ctx_channel_requires_kind_and_attr() -> None:
    with pytest.raises(ValueError, match="缺 symbol_kind"):
        _load_transform_ctx_channels("c", {"ctx_channels": {"m": {"attr": "a"}}})
    with pytest.raises(ValueError, match="缺 attr"):
        _load_transform_ctx_channels("c", {"ctx_channels": {"m": {"symbol_kind": "k"}}})


def _load(decls: list) -> dict:
    return _load_transform_slot_decls("test-cdir", {"slots": decls})


def test_decl_item_must_be_table() -> None:
    with pytest.raises(ValueError, match="须为表"):
        _load(["some_slot"])


def test_missing_name_fails() -> None:
    with pytest.raises(ValueError, match="缺 name"):
        _load([{"on": "X"}])


def test_unregistered_slot_fails() -> None:
    with pytest.raises(ValueError, match="未注册"):
        _load([{"name": "no_such_slot", "on": "X"}])


def test_duplicate_slot_fails(probe_slot: str) -> None:
    with pytest.raises(ValueError, match="槽位名重复"):
        _load(
            [
                {"name": probe_slot, "on": "X"},
                {"name": probe_slot, "on": "Y"},
            ]
        )


def test_missing_on_fails(probe_slot: str) -> None:
    with pytest.raises(ValueError, match="on 须为非空节点名"):
        _load([{"name": probe_slot}])


def test_bad_walk_fails(probe_slot: str) -> None:
    with pytest.raises(ValueError, match="walk 非法"):
        _load([{"name": probe_slot, "on": "X", "walk": "deep"}])


def test_bad_result_fails(probe_slot: str) -> None:
    with pytest.raises(ValueError, match="result 非法"):
        _load([{"name": probe_slot, "on": "X", "result": "inplace"}])


def test_bad_ctx_source_fails(probe_slot: str) -> None:
    with pytest.raises(ValueError, match="ctx 特殊来源非法"):
        _load(
            [
                {
                    "name": probe_slot,
                    "on": "X",
                    "ctx": {"foo": "$self"},
                }
            ]
        )


def test_defaults_applied(probe_slot: str) -> None:
    """walk 缺省 top；result 缺省 none；ctx 缺省空。"""
    decls = _load([{"name": probe_slot, "on": "X"}])
    assert decls[probe_slot] == {
        "name": probe_slot,
        "on": ["X"],
        "walk": "top",
        "result": "none",
        "ctx": {},
    }


def test_no_slots_declared_is_empty() -> None:
    assert _load_transform_slot_decls("test-cdir", {}) == {}

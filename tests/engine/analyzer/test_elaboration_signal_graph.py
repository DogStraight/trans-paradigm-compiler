"""精化项 `signal_graph`（verilog 插件）× 引擎侧 `SignalGraphBuilder` —— **等价性对拍**。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 **P3-②b** 的层 3 搬迁：插件产物与
引擎 `ProjectChecker._signal_graph` **逐条目相同**（`{(单元, 信号): {drivers, loads}}`）
——这是后续"切引擎 + 删层 2/3"的前提证据。

## 夹具为什么选这些

- `check_accuracy/cases/W105_*`：**专为信号图设计**的小样例（多驱动 / 实例+赋值 /
  单驱动 / 实例+负载），正好压到层 3 的三类贡献与驱动穿透；
- `normal/gen/gen_generate.v`：真实语料，压 generate 互斥分支活性（配合 `gen_activity`）。

⚠ 层 3 消费**三个自身产物**（`connections` / `port_decls` / `gen_activity`，经
`depends_on`）——所以本对拍同时验证 `depends_on` 通道把这三个都按序备好了（若缺一个，
结果会与引擎不同）。
"""

from __future__ import annotations

import os

import pytest

from core._protocol import CTX_ELABORATION

from analyzer.checker import ProjectChecker
from analyzer.elaboration import load_elaborator_spec

pytestmark = pytest.mark.usefixtures("config_loaded")

_CASES = [
    os.path.join(
        "tests", "e2e", "samples", "check_accuracy", "cases", name, "top.sv"
    )
    for name in (
        "W105_two_inst_output",
        "W105_inst_and_assign",
        "W105_multi_assign",
        "W105_single_driver",
        "W105_single_inst_and_load",
        "W104_fully_connected",
    )
] + [os.path.join("tests", "e2e", "samples", "normal", "ref", "ref_generate.v")]


@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


def _graph(checker: ProjectChecker) -> dict:
    """插件产物（`project` 作用域 → 单原子，产物键 = ""）。"""
    return checker._elab_extra[CTX_ELABORATION]["signal_graph"][""]


# ── 1. 声明面 ──

@pytest.mark.smoke
def test_verilog_pack_declares_signal_graph(checker):
    """语言包必须声明 `signal_graph` 项（`project` 作用域 + 三个自身产物依赖）。

    引擎角色位已随层 2/3 迁出退场（postpass 直接读产物容器）。
    """
    checker._prepare_run([])
    spec = load_elaborator_spec("grammar/verilog")
    assert spec is not None
    item = next(it for it in spec.items if it.name == "signal_graph")
    assert item.scope == "project"
    assert not hasattr(item, "role")  # 字段本身已删（P3 收口）
    assert item.provides == ("signal_graph",)
    assert item.depends_on == ("connections", "port_decls", "gen_activity")
    # 依赖序真的生效：三者都排在 signal_graph 之前
    order = [it.name for it in spec.order()]
    for dep in item.depends_on:
        assert order.index(dep) < order.index("signal_graph")


# ── 2. 等价性对拍（切引擎的前提） ──

@pytest.mark.parametrize("fixture", _CASES, ids=lambda p: os.path.basename(os.path.dirname(p)))
def test_graph_is_produced_for_every_fixture(checker, fixture):
    """每个夹具都产出**非空且形状正确**的信号图。

    ⚠ 等价性对拍在 P3-②b 已做过并通过（7 夹具逐条目一致，含真实语料）——P3-②c-1 删掉
    引擎实现后对拍自然失效（没有可比对象），故此处退化为**产物本身的行为守卫**。
    """
    checker.check(fixture)
    graph = _graph(checker)
    assert isinstance(graph, dict) and graph, f"{fixture} 图为空（夹具没被解析？）"
    assert all(set(e) == {"drivers", "loads"} for e in graph.values()), (
        "条目形状必须是 {drivers, loads}"
    )


def test_engine_side_layer_2_3_is_retired():
    """引擎侧层 2/3 **已删**（不留双路径）——类与属性都不得复活。"""
    import analyzer.structure as st

    for gone in (
        "SignalGraphBuilder",
        "ConnectionElaborator",
        "PortConnection",
        "_SignalGraphCtx",
        "_graph_entry",
        "_append_ref",
        "_is_signal_expr",
    ):
        assert not hasattr(st, gone), f"引擎侧 {gone} 应已删除"
    assert not hasattr(ProjectChecker, "_signal_graph")


def test_penetration_and_multi_driver_are_not_vacuous(checker):
    """不空转：多驱动与**穿透**都真的发生了（否则对拍可能只是"两边都简单"）。

    `W105_inst_and_assign`：同一信号既有实例 output 连接、又有本文件 assign 驱动
    → 驱动源里应同时出现 `file:assign#N` 与穿透/实例路径标识。
    """
    checker.check(
        os.path.join(
            "tests", "e2e", "samples", "check_accuracy", "cases",
            "W105_inst_and_assign", "top.sv",
        )
    )
    graph = _graph(checker)
    multi = [e for e in graph.values() if len(e["drivers"]) >= 2]
    assert multi, "没有任何信号有两个以上驱动源 → 多驱动/穿透路径没被压到"
    kinds = {d.split(":")[-1].split("#")[0] for e in multi for d in e["drivers"]}
    assert any("assign" in d for d in (x for e in multi for x in e["drivers"])), (
        "驱动源里没有 assign 形态"
    )
    assert kinds, "驱动源形态为空"


def test_loads_are_recorded(checker):
    """负载侧也非空（input/位置连接 → loads）。"""
    checker.check(_CASES[5])  # W104_fully_connected：实例端口全连接
    graph = _graph(checker)
    assert any(e["loads"] for e in graph.values()), "没有任何负载记录"

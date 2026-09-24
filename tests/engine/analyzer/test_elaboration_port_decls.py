"""精化项 `port_decls`（verilog 插件）× 引擎侧 `ModuleExtractor._fill_ports` —— **等价性对拍**。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 **P3-②a**：插件产物 `port_decls` 与
引擎侧 `ModuleInfo.ports` **逐项相同**——这是后续"层 2/3 与 ports 一次性搬迁"的前提证据。

## 两个夹具，覆盖三种声明形态

| 夹具 | 覆盖 |
|---|---|
| `tests/e2e/samples/check_accuracy/cases/EX001_non_ansi_header/top.sv` | **裸名头部**（`module top(a, b)`）+ **体内旧式声明**（`input a;`）→ 回填路径 |
| `tests/e2e/samples/normal/gen/gen_generate.v` | **ANSI 头部**（方向 + 宽度 + 网络类型） |

⚠ P3-②a 阶段本项**只新增、无人消费**（引擎侧 `ModuleInfo.ports` 仍在原位、仍是层 2/3 的
输入）——本文件的存在意义就是**对拍**。切换 + 删引擎侧在 P3-②b。

⚠ 已知键口径差异（本阶段不影响对拍，P3-②b 要处理）：产物按**原子键（单元名）**归位，
同名单元在多个文件重复定义时"最后一个原子赢"；而引擎 `module_index` 是"**首个**定义者
优先"。两个夹具的单元名唯一，故此处不暴露该差异。
"""

from __future__ import annotations

import os

import pytest

from core._protocol import CTX_ELABORATION

from analyzer.checker import ProjectChecker
from analyzer.elaboration import ROLE_UNIT_PORTS, load_elaborator_spec

pytestmark = pytest.mark.usefixtures("config_loaded")

_FIXTURE_LEGACY = os.path.join(
    "tests", "e2e", "samples", "check_accuracy", "cases",
    "EX001_non_ansi_header", "top.sv",
)
_FIXTURE_ANSI = os.path.join(
    "tests", "e2e", "samples", "normal", "gen", "gen_generate.v"
)


@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


def _engine_ports(checker: ProjectChecker) -> dict:
    """引擎侧旧实现的端口表（对拍基准），拍平成与产物同形的 dict。"""
    return {
        name: {
            pn: {
                "name": p.name,
                "direction": p.direction,
                "width_expr": p.width_expr,
                "net_type": p.net_type,
                "decl_node": p.decl_node,
            }
            for pn, p in (info.ports or {}).items()
        }
        for name, info in checker._ctx.module_index.items()
    }


def _plugin_ports(checker: ProjectChecker) -> dict:
    return checker._elab_extra[CTX_ELABORATION]["port_decls"]


# ── 1. 声明面 ──

@pytest.mark.smoke
def test_verilog_pack_declares_port_decls(checker):
    """语言包必须声明 `port_decls` 项（含引擎角色位与作用域）——缺声明即静默降级。"""
    checker._prepare_run([])
    spec = load_elaborator_spec("grammar/verilog")
    assert spec is not None
    item = next(it for it in spec.items if it.name == "port_decls")
    assert item.scope == "unit"
    assert item.role == ROLE_UNIT_PORTS
    assert item.provides == ("port_decls",)
    assert spec.role_key(ROLE_UNIT_PORTS) == "port_decls"


# ── 2. 等价性对拍（搬迁的前提） ──

@pytest.mark.parametrize("fixture", ["legacy", "ansi"])
def test_plugin_matches_engine_per_port(checker, fixture):
    checker.check(_FIXTURE_LEGACY if fixture == "legacy" else _FIXTURE_ANSI)
    plugin = _plugin_ports(checker)
    engine = _engine_ports(checker)

    assert set(plugin) == set(engine), "单元集与引擎不一致"
    assert engine, "夹具没被解析（空索引 → 对拍退化成空转）"
    for unit, engine_ports in engine.items():
        assert plugin[unit] == engine_ports, f"单元 {unit} 的端口表不一致"


def test_body_port_backfill_is_not_vacuous(checker):
    """不空转：**裸名头部 + 体内声明**那条路径真的回填了方向（否则对拍无意义）。"""
    checker.check(_FIXTURE_LEGACY)
    ports = _plugin_ports(checker)["top"]
    assert set(ports) == {"a", "b"}, "裸名端口没登记全"
    # 方向来自**体内** `input a;` / `output b;`（回填路径，非头部）
    assert ports["a"]["direction"] == "input"
    assert ports["b"]["direction"] == "output"
    assert ports["a"]["width_expr"] == ""  # body 声明无宽度 → 空
    # 与引擎逐项一致（同一断言在对拍里已覆盖，这里显式锁住"回填发生了"）
    assert _plugin_ports(checker) == _engine_ports(checker)


def test_ansi_ports_carry_direction_and_width(checker):
    """ANSI 头部那条路径带上方向与宽度表达式（`data_in` 是参数化宽度）。"""
    checker.check(_FIXTURE_ANSI)
    ports = _plugin_ports(checker)["generate_test"]
    assert set(ports) >= {"clk", "data_in", "data_out"}
    assert ports["clk"]["direction"] == "input"
    assert ports["data_out"]["direction"] == "output"
    assert ports["data_in"]["width_expr"], "ANSI 宽度表达式没取到"
    # 网络类型也在（`input wire ...`）
    assert ports["clk"]["net_type"] == "wire"


def test_decl_node_is_exposed_for_related_chain(checker):
    """`decl_node` 随产物带出（related 链跨文件定位用），且 `_file` 已写。"""
    checker.check(_FIXTURE_LEGACY)
    port = _plugin_ports(checker)["top"]["a"]
    assert port["decl_node"] is not None
    assert getattr(port["decl_node"], "_file", "").endswith("top.sv")

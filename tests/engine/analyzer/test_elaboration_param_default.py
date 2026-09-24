"""精化项 `param_default`（verilog 插件）—— golden 值 + 退场守卫 + 降级。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 **P2** 落地的 `param_default`。

⚠ **golden 值的来源**（重要，别当随手写的期望）：P2 搬迁时先做**等价性对拍**——
引擎侧旧实现（`ModuleExtractor._fill_params` → `ModuleInfo.params`）与插件产物
逐项比较，实测**完全相同**；随后才删掉引擎侧实现（"先证后改"）。故下面这组
`{参数名: 值文本}` 是**对拍通过后冻结**的契约，不是猜测值。

覆盖四点：
1. 语言包确实声明了 `elaborator` 能力与 `param_default` 项（声明缺失 = 静默降级）；
2. golden 值：头部参数 / 体内参数（含多声明符）/ 无参数单元；
3. **引擎角色位已退场**（P3-①：gen 求值迁入插件后，单元常量只经插件间依赖通道消费，
   引擎不再中转）——本项**无** `role`；
4. 未声明能力的语言包 → 降级（无容器键、无角色产物）。

⚠ 夹具源码形态受**语法包当前覆盖**限制：头部多参数必须**逐个重复 `parameter`
关键字**（`#(parameter W = 8, parameter D = W/2)`）；`#(parameter W = 8, D = 4)` 与
ANSI 风格 `#(W = 8, D = 4)` 在本次实测中**解析失败**（既有语法覆盖缺口，与精化搬迁
无关，另记）。写夹具时按可解析形态来，否则被 lint 阻断 → 空索引 → 断言退化成空转。
"""

from __future__ import annotations

import pytest

from core._protocol import CTX_ELABORATION

from analyzer.checker import ProjectChecker
from analyzer.elaboration import ROLE_GEN_ACTIVITY, load_elaborator_spec

pytestmark = pytest.mark.usefixtures("config_loaded")

_TOP = """\
module top #(parameter W = 8, parameter D = W/2) (input clk);
  lib #(.W(16)) u_lib ();
  plain u_plain ();
endmodule
"""

_LIB = """\
module lib #(parameter W = 4) (input clk);
  parameter X = W * 2;
  parameter Y = 1, Z = 2;
  wire [W-1:0] w;
endmodule
"""

_PLAIN = "module plain (input a);\nendmodule\n"

# 对拍通过后冻结的 golden 值（来源见模块头）。⚠ 值 = **渲染器**产出的文本，
# 不是原样源码（`W/2` → `"W / 2"`：运算符两侧补空格）——别按源码原样抄。
_GOLDEN_TOP = {"W": "8", "D": "W / 2"}
_GOLDEN_LIB = {"W": "4", "X": "W * 2", "Y": "1", "Z": "2"}


@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


@pytest.fixture
def project(tmp_path):
    """top 实例化 lib（头部 + 体内参数）与 plain（无参数）——三者同目录。"""
    top = tmp_path / "top.sv"
    top.write_text(_TOP, encoding="utf-8")
    (tmp_path / "lib.sv").write_text(_LIB, encoding="utf-8")
    (tmp_path / "plain.sv").write_text(_PLAIN, encoding="utf-8")
    return top


def _params_of(checker: ProjectChecker) -> dict:
    """本语言包精化产物 `param_default`：{单元名: {参数名: 值文本}}。"""
    return checker._elab_extra[CTX_ELABORATION]["param_default"]


# ── 1. 声明面 ──

@pytest.mark.smoke
def test_verilog_pack_declares_elaborator(checker):
    """语言包必须声明 `elaborator` 能力与 `param_default` 项——缺声明即静默降级。"""
    checker._prepare_run([])
    spec = load_elaborator_spec("grammar/verilog")
    assert spec is not None, "[capabilities] elaborator 未声明"
    assert "param_default" in [it.name for it in spec.items]
    item = next(it for it in spec.items if it.name == "param_default")
    assert item.scope == "unit"
    # 无引擎角色位：单元常量只经插件间依赖通道（`gen_activity` 的 depends_on）消费
    assert item.role is None
    assert item.provides == ("param_default",)


# ── 2. golden 值（头部 / 体内 / 无参数） ──

def test_param_default_golden_values(checker, project):
    checker.check(str(project))
    params = _params_of(checker)

    assert set(params) >= {"top", "lib", "plain"}, "单元原子没产出（夹具被阻断？）"
    assert params["top"] == _GOLDEN_TOP  # 头部 `#(...)` 参数
    assert params["lib"] == _GOLDEN_LIB  # 头部 + 体内（含多声明符 `parameter Y = 1, Z = 2;`）
    assert params["plain"] == {}  # 无参数单元 → 空表（键仍在，下游不必两套写法）


def test_param_default_body_overrides_are_not_engine_responsibility(checker, project):
    """体内参数也在产物里（引擎侧已无参数抽取——这条挡住"搬回引擎"的回潮）。"""
    checker.check(str(project))
    lib_params = _params_of(checker)["lib"]
    assert "X" in lib_params and "Y" in lib_params and "Z" in lib_params


# ── 3. 引擎角色位（过渡期 generate 条件求值的来源） ──

def test_role_unit_constants_is_retired(checker, project):
    """P3-① 后：引擎侧 `unit_constants` **已退场**——单元常量只由产物承载。

    generate 条件求值改由插件自己的 `gen_activity` 求解器经 `ctx.products` 读取
    （不经引擎中转），故引擎不再需要该角色位（`ROLES` 里已无 `unit_constants`）。
    本用例锁住"退场"，防它被无意中搬回引擎。
    """
    checker.check(str(project))
    assert _params_of(checker)["lib"] == _GOLDEN_LIB
    assert checker._elaborator.role_key("unit_constants") is None
    assert not hasattr(checker._ctx, "unit_constants")


# ── 4. 未声明能力 → 降级 ──

def test_pack_without_capability_degrades():
    """c4 未声明 `elaborator` → 无容器键、无角色产物（与旧行为一致）。"""
    checker = ProjectChecker(rules_dir="grammar/c4")
    checker._prepare_run([])
    assert checker._elaborator.declared is False
    assert checker._elaborator.role_key(ROLE_GEN_ACTIVITY) is None

    checker._elaborate()
    assert CTX_ELABORATION not in checker._elab_extra
    assert checker._ctx.gen_activity == {}

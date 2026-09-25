"""精化项 `param_override`（verilog 插件）× `width_check` 自带的合并逻辑 —— **对拍**。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 **P3-②c-3**：把各检查原先**各自
一份**的"实例化点覆盖后参数表"合并逻辑上提为共享产物 `param_override`。

⚠ 这一步的性质是**去重共享**，**不是**"把语言知识搬出引擎"——那段合并（调用者参数 →
目标单元默认 → site 覆盖）今天本来就在插件侧（`width_check._override_params` /
`hier_check._merged_params`），引擎里没有对应实现（ADR-0019 决策 4 更正节）。

## ⚠ 已知技法差异（迁移消费方前必须处理，故此处**显式探测**）

`width_check._override_params` 用**自带的 `node_text` 渲染器**把覆盖值取成文本；本项目用
**服务渲染器**（`_render`）。**字面量**覆盖（`#(.W(16))`）两者逐字一致；**表达式**覆盖
（`#(.W(4*4))`）可能只差空白形态（`4*4` vs `4 * 4`）——数值求值等价，但**文本比较**
（`_override_changes_params` 的 `pv != defaults.get(pn)`）行为可能随之改变。

故本项当前**只新增**（消费方仍用各自那份），本文件的意义就是把这个差异钉住；切换时
须先处理它（否则 W201 的"有效覆盖判据"可能变脸）。
"""

from __future__ import annotations

import os

import pytest

from core._protocol import CTX_ELABORATION

from analyzer.checker import ProjectChecker
from analyzer.elaboration import load_elaborator_spec
from grammar.verilog.plugins.checks.width_check import _width_check as wc

pytestmark = pytest.mark.usefixtures("config_loaded")

# 真实夹具：`A #(.W(16)) u_a();` + 模块 A 体内 `parameter W = 4;`（覆盖 ≠ 默认）
_FIXTURE = os.path.join(
    "tests", "e2e", "samples", "check_accuracy", "cases",
    "W201_param_override_trunc", "top.sv",
)

# 表达式覆盖的合成夹具（探测渲染差异）
_EXPR = """\
module b;
  parameter W = 2;
  reg [1:0] y;
  wire [W-1:0] x;
  assign y = x;
endmodule

module top2;
  b #(.W(4*4)) u_b();
endmodule
"""


class _Ctx:
    """postpass 上下文替身：`width_check` 的助手只吃 `extra`。"""

    def __init__(self, extra: dict) -> None:
        self.extra = extra


class _Analyzer:
    """analyzer 替身：`width_check._file_params` 只吃 `_ast`。"""

    def __init__(self, ast) -> None:
        self._ast = ast


@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


def _only_path(checker: ProjectChecker) -> str:
    """单文件夹具的产物键（= `memo` 的绝对路径键；`check()` 会把入口归一化）。"""
    return next(iter(checker._ctx.memo))


def _override_product(checker: ProjectChecker, path: str) -> list[dict]:
    container = checker._elab_extra[CTX_ELABORATION]
    return container["param_override"][path]


def _width_check_view(checker: ProjectChecker, path: str) -> list[dict]:
    """用 `width_check` **自己的**助手算一遍（对拍基准）。"""
    container = checker._elab_extra[CTX_ELABORATION]
    ctx = _Ctx({CTX_ELABORATION: container})
    params_all = wc._module_params(ctx)
    fr = checker._ctx.memo[path]
    caller = wc._file_params(_Analyzer(fr.ast), params_all)
    out = []
    for site in fr.inst_sites:
        mod = wc.node_text(getattr(site, "module_name", None))
        defaults = params_all.get(mod, {})
        out.append(
            {
                "inst_name": wc.node_text(getattr(site, "inst_name", None)),
                "module_name": mod,
                "params": wc._override_params(site, defaults, caller),
                "changed": wc._override_changes_params(site, defaults),
            }
        )
    return out


# ── 1. 声明面 ──

@pytest.mark.smoke
def test_verilog_pack_declares_param_override(checker):
    """语言包必须声明 `param_override` 项（作用域 + 两个依赖）。"""
    checker._prepare_run([])
    spec = load_elaborator_spec("grammar/verilog")
    assert spec is not None
    item = next(it for it in spec.items if it.name == "param_override")
    assert item.scope == "file"
    assert item.role is None  # 引擎不消费 → 无角色位（终态）
    assert item.provides == ("param_override",)
    assert item.depends_on == ("param_default", "connections")
    order = [it.name for it in spec.order()]
    for dep in item.depends_on:
        assert order.index(dep) < order.index("param_override")


# ── 2. 对拍（字面量覆盖：逐字一致） ──

def test_product_matches_width_check_literal_override(checker):
    """字面量覆盖下，产物与 `width_check` 自己的合并**逐项一致**。"""
    checker.check(_FIXTURE)
    path = _only_path(checker)
    product = _override_product(checker, path)
    baseline = _width_check_view(checker, path)

    assert product, "产物为空"
    assert len(product) == len(baseline) == 1
    assert product[0]["inst_name"] == baseline[0]["inst_name"] == "u_a"
    assert product[0]["module_name"] == baseline[0]["module_name"] == "A"
    assert product[0]["params"] == baseline[0]["params"]
    assert product[0]["changed"] == baseline[0]["changed"] is True


def test_override_is_not_vacuous(checker):
    """不空转：覆盖真的生效——`W` 从默认 4 变成 16，且标记为"有效覆盖"。"""
    checker.check(_FIXTURE)
    entry = _override_product(checker, _only_path(checker))[0]
    assert entry["params"]["W"] == "16", "覆盖值没进合并表"
    assert entry["changed"] is True, "覆盖 ≠ 默认 却未标记 changed"


# ── 3. 已知技法差异：表达式覆盖（记录，不假装一致） ──

def test_expression_override_may_differ_only_in_whitespace(checker, tmp_path):
    """**表达式**覆盖：两个渲染器可能只差空白——数值等价，但**文本**可能不等。

    本用例把差异钉住：断言"去空白后一致"（若哪天连去空白都不一致，说明是**语义**差异
    而非技法差异，迁移前必须查清）。这也是"切换消费方前须先处理该差异"的依据。
    """
    src = tmp_path / "expr.v"
    src.write_text(_EXPR, encoding="utf-8")
    checker.check(str(src))
    path = _only_path(checker)

    product = _override_product(checker, path)
    baseline = _width_check_view(checker, path)
    assert product and baseline

    for got, want in zip(product, baseline):
        assert got["params"].keys() == want["params"].keys()
        for name, value in got["params"].items():
            assert value.replace(" ", "") == want["params"][name].replace(" ", ""), (
                f"参数 {name} 的两份文本连去空白后都不一致——这是**语义**差异，"
                f"不是渲染技法差异：{value!r} vs {want['params'][name]!r}"
            )

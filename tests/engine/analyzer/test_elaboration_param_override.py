"""精化项 `param_override`（verilog 插件）—— golden 行为 + 消费方去重守卫。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 **P3-②c-3**：把各检查原先**各自
一份**的"实例化点覆盖后参数表"合并逻辑上提为共享产物 `param_override`，并让
`width_check` 改读它（删掉自带那份）。

⚠ 这一步的性质是**去重共享**，**不是**"把语言知识搬出引擎"——那段合并今天本来就在插件侧
（ADR-0019 决策 4 更正节），引擎里没有对应实现。

⚠ **golden 的来源**：搬迁时先与 `width_check` **自带的**合并（`_override_params` /
`_override_changes_params`）**逐项对拍**（字面量覆盖下 `params` 与 `changed` 全等），
通过后才删掉那份实现——故下面的值是**对拍通过后冻结**的契约。删掉基准后对拍退化为
golden + 语义断言 + **退场守卫**（自带实现不得复活）。

## 已知技法差异（已论证安全，记录在案）

`width_check` 原先用**自带的 `node_text` 渲染器**取覆盖值文本，共享产物用**服务渲染器**
（`_render`）——字面量逐字一致；**表达式**覆盖（`#(.W(4*4))`）可能只差空白。

该差异**只可能让原先多触发** B4 重算；而"少触发"仅发生在覆盖文本与默认文本**完全相同**
时（语义必然相等 → 重算也不会产出新诊断），故**不会漏诊断**。本文件用
`const_eval`（本语言包自己的求值器）断言表达式覆盖的**语义值**，把这一点钉住。
"""

from __future__ import annotations

import os

import pytest

from core._protocol import CTX_ELABORATION

from analyzer.checker import ProjectChecker
from analyzer.elaboration import load_elaborator_spec
from grammar.verilog.plugins.checks import _shared as shared
from grammar.verilog.plugins.checks.width_check import _width_check as wc

pytestmark = pytest.mark.usefixtures("config_loaded")

# 真实夹具：`A #(.W(16)) u_a();` + 模块 A 体内 `parameter W = 4;`（覆盖 ≠ 默认）
_FIXTURE = os.path.join(
    "tests", "e2e", "samples", "check_accuracy", "cases",
    "W201_param_override_trunc", "top.sv",
)

# 表达式覆盖的合成夹具（压"文本可能不同、语义相同"那条路径）
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


@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


def _only_path(checker: ProjectChecker) -> str:
    """单文件夹具的产物键（= `memo` 的绝对路径键；`check()` 会把入口归一化）。"""
    return next(iter(checker._ctx.memo))


def _product(checker: ProjectChecker) -> list[dict]:
    return checker._elab_extra[CTX_ELABORATION]["param_override"][_only_path(checker)]


# ── 1. 声明面 ──

@pytest.mark.smoke
def test_verilog_pack_declares_param_override(checker):
    """语言包必须声明 `param_override` 项（作用域 + 两个依赖）。"""
    checker._prepare_run([])
    spec = load_elaborator_spec("grammar/verilog")
    assert spec is not None
    item = next(it for it in spec.items if it.name == "param_override")
    assert item.scope == "file"
    assert not hasattr(item, "role")  # 字段本身已删（终态）
    assert item.provides == ("param_override",)
    assert item.depends_on == ("param_default", "connections")
    order = [it.name for it in spec.order()]
    for dep in item.depends_on:
        assert order.index(dep) < order.index("param_override")


# ── 2. golden 行为（字面量覆盖） ──

def test_literal_override_golden(checker):
    """字面量覆盖：合并表与"有效覆盖"判据（对拍通过后冻结的 golden）。"""
    checker.check(_FIXTURE)
    entries = _product(checker)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["inst_name"] == "u_a"
    assert entry["module_name"] == "A"
    assert entry["params"] == {"W": "16"}  # 调用者参数 ∪ 目标默认 ∪ site 覆盖
    assert entry["changed"] is True  # 覆盖 16 ≠ 默认 4


# ── 3. 表达式覆盖：语义等价（技法差异下的安全边界） ──

def test_expression_override_is_semantically_sound(checker, tmp_path):
    """表达式覆盖：产物文本可能只差空白，但**求值语义**必须正确（= 16）。"""
    src = tmp_path / "expr.v"
    src.write_text(_EXPR, encoding="utf-8")
    checker.check(str(src))
    entries = _product(checker)
    assert len(entries) == 1
    value = entries[0]["params"]["W"]
    assert value.replace(" ", "") == "4*4", f"覆盖文本形态异常：{value!r}"
    assert wc.const_eval(value) == 16, "表达式覆盖的语义值不对"
    assert entries[0]["changed"] is True  # 16 ≠ 默认 2


# ── 4. 退场守卫（消费方去重，不留双路径） ──

def test_width_check_no_longer_aggregates_its_own_override_table():
    """`width_check` **不得**再自带覆盖合并——同一语义只维护一处。"""
    for gone in ("_override_params", "_override_changes_params"):
        assert not hasattr(wc, gone), f"width_check.{gone} 应已删除（改读共享产物）"
    # 改读**共享助手**（`checks/_shared.override_of`）——一份产物读取器，
    # width_check / hier_check 共用；插件内不再留私有合并逻辑。
    assert wc.override_of is shared.override_of, "应改读共享产物助手"

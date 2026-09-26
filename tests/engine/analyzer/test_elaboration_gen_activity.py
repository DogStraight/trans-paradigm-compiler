"""精化项 `gen_activity`（verilog 插件）—— golden 行为 + 求值器单元面 + 退场守卫。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 **P3-①** 的 gen 族搬迁。

⚠ **golden 的来源**（别当随手写的期望）：搬迁时先做**等价性对拍**——插件产物与引擎侧
`GenerateEvaluator._precompute_generate_active` **逐节点相同**（两个夹具各跑一次，实测
通过）；**随后才删掉引擎侧实现**（"先证后改"）。故下面关于活性/条件的断言都是**对拍
通过后冻结**的契约，不是猜测值。

## 两个夹具，各自压不同路径

| 夹具 | 覆盖 |
|---|---|
| 真实语料 `tests/e2e/samples/normal/ref/ref_generate.v` | generate-for + generate if/else；条件是 `DATA_WIDTH > 8`（**不可判**）与 `g == 0`（含循环变量，**不可判**） |
| 合成 `_DECIDED`（体内 `parameter EN = 1` + `if (EN)`） | **可判**路径 |

⚠ **为什么必须两类都有**：求值器只认 **裸参数名**（含 `!` 前缀）/ 纯数字 / 纯常量
表达式；**参数名与运算符混排**（`DATA_WIDTH > 8`）一律**不可判** → 该块按活跃展开、
**全为 `True`**。只用真实语料时，"插件参数表丢失"与"正常"**都是全 True** → 判据退化成
**假等价**。第一版就是这么写的，被"不空转"断言当场抓到（原以为 `DATA_WIDTH > 8` 可判）。

## 依赖通道也被压到

`gen_activity` 求解器经 `ctx.products["param_default"]` 读单元常量
（`depends_on = ["param_default"]`）——引擎不中转。可判夹具上，若该通道失效，
可判条件退化为不可判 → 产物里不再有 `False`。
"""

from __future__ import annotations

import os
from typing import cast

import pytest

from core._protocol import CTX_ELABORATION
from core.define import Node

from analyzer.checker import ProjectChecker
from analyzer.elaboration import SolveCtx, load_elaborator_spec
from analyzer.elaboration.service import ServiceApi

pytestmark = pytest.mark.usefixtures("config_loaded")

_FIXTURE_REAL = os.path.join(
    "tests", "e2e", "samples", "normal", "ref", "ref_generate.v"
)

# 可判条件夹具：体内 `parameter EN = 1;` + `if (EN)`（裸参数名 → 求值器能判）
_DECIDED = """\
module gen_dec (input clk);
  parameter EN = 1;
  generate
  if (EN) begin: on_path
      wire a;
  end else begin: off_path
      wire b;
  end
  endgenerate
endmodule
"""


@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


@pytest.fixture
def decided(tmp_path):
    path = tmp_path / "gen_dec.v"
    path.write_text(_DECIDED, encoding="utf-8")
    return path


def _activity(checker: ProjectChecker) -> dict:
    """产物 `gen_activity`：{文件路径: {id(节点): bool}}。"""
    return checker._elab_extra[CTX_ELABORATION]["gen_activity"]


# ── 1. 声明面 ──

@pytest.mark.smoke
def test_verilog_pack_declares_gen_activity(checker):
    """语言包必须声明 `gen_activity` 项（含角色位与依赖）——缺声明即静默退化为不过滤。"""
    checker._prepare_run([])
    spec = load_elaborator_spec("grammar/verilog")
    assert spec is not None
    item = next(it for it in spec.items if it.name == "gen_activity")
    assert item.scope == "file"
    assert not hasattr(item, "role")  # 字段本身已删（P3 收口）
    assert item.provides == ("gen_activity",)
    assert item.depends_on == ("param_default",)
    order = [it.name for it in spec.order()]
    assert order.index("param_default") < order.index("gen_activity")


# ── 2. 产物形状与可判/不可判两条路径 ──

def test_container_shape_is_per_file_node_map(checker, decided):
    """形状 = `{文件路径: {id(节点): bool}}`（角色位契约定义寻址键与形状）。"""
    checker.check(str(decided))
    activity = _activity(checker)
    assert set(activity) == set(checker._ctx.memo), "原子键应为文件路径"
    inner = activity[next(iter(activity))]
    assert inner and all(isinstance(v, bool) for v in inner.values())
    assert all(isinstance(k, int) for k in inner)


def test_decided_branch_is_actually_filtered(checker, decided):
    """**不空转**：可判条件（裸参数 `EN = 1`）确实过滤掉了未选中分支。

    若 `depends_on` 通道失效（拿不到 `param_default`），该条件会退化为不可判 →
    整个 generate 块按活跃展开 → 产物里不再有 `False`。本断言即守该通道。
    """
    checker.check(str(decided))
    values = [v for m in _activity(checker).values() for v in m.values()]
    assert values, "产物为空"
    assert False in values, "没有节点被判未选中 → 条件求值没生效（参数表丢了？）"
    assert True in values, "全部未选中 → 活性判定反了"


def test_real_corpus_conditions_are_undecidable_today(checker):
    """真实语料那条 `DATA_WIDTH > 8` **今天判不了**（参数名与运算符混排）。

    锁住这个**已知边界**（gap 档「求值能力」条）：不是本项回归，而是求值器能力的
    现状——全 True = 不误删分支（保守方向）。将来若扩求值能力（如让"参数比较字面量"
    可判），本用例会变红，届时须同时重审**对拍夹具的选择**（真实语料将不再"不敏感"）。
    """
    checker.check(_FIXTURE_REAL)
    values = [v for m in _activity(checker).values() for v in m.values()]
    assert values and all(values), (
        "真实夹具出现 False → 求值能力已扩展；请更新本用例与文件头说明"
    )


# ── 3. 求值器单元面（原 `test_gen_face.py` 的**可移植**部分） ──
# 原文件测的是引擎的**声明面**（`StructureCtx.gen_face()`）与"声明驱动"行为——声明面已
# 随 gen 族迁出删除，那部分**判据失效**（删除先证后删：主体不存在了）。此处只保留与
# **求值语义**有关、与"声明"无关的用例——它们现在测插件自己的常量。


class _FakeService:
    """服务替身：直接给固定文本（条件求值只吃渲染后的文本）。"""

    def __init__(self, text: str) -> None:
        self._text = text

    def render(self, node) -> str:
        del node  # 替身不消费入参
        return self._text


def _cond(text: str, params: dict):
    """文本条件 → 布尔｜None（插件私有求值器；原引擎测试同法直测私有）。"""
    from grammar.verilog.plugins.elaboration import _elaborator as elab

    node = Node("IfBlock")
    node.add_attr("condition", Node("Identifier"))
    # `_FakeService` 只实现被求值器调用到的那几个方法——代 ServiceApi 的测试替身
    ctx = SolveCtx(products={}, service=cast(ServiceApi, _FakeService(text)))
    return elab._eval_gen_cond(node, params, ctx)


def test_literal_and_plain_param_truth():
    assert _cond("0", {}) is False
    assert _cond("3", {}) is True
    assert _cond("W", {"W": "1"}) is True
    assert _cond("W", {"W": "0"}) is False
    assert _cond("W", {"W": "DATA_W"}) is None  # 值非纯数字 → 不可判


def test_not_op_negates_param():
    assert _cond("!W", {"W": "0"}) is True
    assert _cond("!W", {"W": "5"}) is False
    assert _cond("! W", {"W": "0"}) is True  # 前缀与名字之间允许空白
    assert _cond("!W", {"W": "DATA_W"}) is None  # 值非纯数字 → 不可判


def test_plain_const_expression_is_evaluated_without_eval():
    assert _cond("2*3<7", {}) is True
    assert _cond("1+0", {}) is True
    assert _cond("1/0", {}) is None  # 除零 → 不可判
    assert _cond("", {}) is None


def test_param_mixed_with_operator_is_undecidable():
    """已知边界：参数名与运算符混排一律不可判（求值器认的是**裸参数名**）。"""
    assert _cond("W > 8", {"W": "16"}) is None
    assert _cond("W+1", {"W": "16"}) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1+0", True),
        ("0", False),
        ("2", True),
        ("2*3<7", True),
        ("(1+2)*3", True),
        ("5%2", True),  # 取模：算术算子可达
        ("1/0", None),  # 除零 → 不可判
        ("1 && 0", None),  # 逻辑运算属语言层
        ("1|0", None),  # 位运算属语言层
        ("!0", None),  # 一元逻辑非属语言层（`!` 只在**参数名前缀**位置被认）
        ("1 << 1", None),  # 移位属语言层
        ("WIDTH", None),  # 标识符 → 不可判
        ("1 + x", None),
        ("", None),
    ],
)
def test_const_expr_neutral_subset(text, expected):
    """常量算式求值器的**中性子集与拒收面**（原 `test_analyzer.py::TestConstExprEval`
    整体搬迁——求值器随 gen 族进了插件，测试跟着走，覆盖不减）。
    """
    from grammar.verilog.plugins.elaboration import _elaborator as elab

    assert elab._eval_const_expr(text) is expected


# ── 4. 退场守卫（不留双路径） ──

def test_engine_side_gen_evaluation_is_retired(checker):
    """P3-①b：引擎侧 gen 求值链、`[structure]` gen 声明面、`unit_constants` 角色**已删**。

    本用例是"不留双路径"的机器守卫——谁把它们搬回引擎，这里立刻变红。
    """
    import analyzer.structure as st

    for gone in ("GenerateEvaluator", "_GenFace", "_eval_const_expr", "_tokenize_const"):
        assert not hasattr(st, gone), f"引擎侧 {gone} 应已删除（不留双路径）"

    checker._prepare_run([])
    # `[structure]` 的 gen 声明面已删（条件求值形态归插件）
    assert not checker._ctx.struct.get("gen_block_rule")
    assert not checker._ctx.struct.get("gen_branch_rules")
    assert not checker._ctx.struct.get("gen_not_ops")
    assert checker._ctx.field("gen_condition") == ""
    assert checker._ctx.field("gen_then") == ""
    assert checker._ctx.field("gen_else_chain") == ""
    # generate 求值不再经引擎中转参数表（且角色的机制已整体退场）
    assert not hasattr(checker._elaborator, "role_key")

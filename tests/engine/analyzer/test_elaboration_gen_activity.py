"""精化项 `gen_activity`（verilog 插件）× 引擎侧 `GenerateEvaluator` —— **等价性对拍**。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 **P3-①** 的核心主张：
插件产物 `gen_activity` 与引擎侧 `GenerateEvaluator._precompute_generate_active`
**逐节点相同**（`{id(节点): bool}`）——这是"删掉引擎侧 gen 求值链"的前提证据。

## 两个夹具，各自压不同的路径

| 夹具 | 覆盖 | 为什么要它 |
|---|---|---|
| 真实语料 `tests/e2e/samples/normal/gen/gen_generate.v` | generate-for + generate if/else，条件是 `DATA_WIDTH > 8`（**不可判**）与 `g == 0`（含循环变量，**不可判**） | 真实形态 + 保守退让路径 |
| 合成 `_DECIDED` | 条件是**裸参数名** `EN`（**可判**） | 可判路径 |

⚠ **为什么必须两类都有**：引擎的求值器只认 **裸参数名**（含 `!` 前缀）/ 纯数字 / 纯常量
表达式；**参数名与运算符混排**（`DATA_WIDTH > 8`）一律**不可判** → 该 generate 块按活跃
展开、全为 `True`。若只用真实语料，则"插件参数表丢失"与"正常"**都是全 True**，对拍会
退化成假等价。可判夹具才让对拍对**依赖通道**敏感（见 `test_decided_branch_...`）。

## 依赖通道也被压到

插件求解器经 `ctx.products["param_default"]` 读单元常量（`depends_on`），引擎侧读的是
**独立注入**的 `unit_constants` 角色产物。若插件的 `depends_on` 未生效、参数表拿不到，
可判条件会退化为不可判 → 产物里**不再有 `False`** → 与引擎（有参数）不等价。
"""

from __future__ import annotations

import os

import pytest

from core._protocol import CTX_ELABORATION

from analyzer.checker import ProjectChecker
from analyzer.elaboration import ROLE_GEN_ACTIVITY, load_elaborator_spec
from analyzer.structure import GenerateEvaluator

pytestmark = pytest.mark.usefixtures("config_loaded")

_FIXTURE_REAL = os.path.join(
    "tests", "e2e", "samples", "normal", "gen", "gen_generate.v"
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


def _gen_maps(checker: ProjectChecker) -> tuple[dict, dict]:
    """(插件产物, 引擎旧实现) —— 都是 {文件路径: {id(节点): bool}}。"""
    container = checker._elab_extra[CTX_ELABORATION]
    plugin = container["gen_activity"]
    engine = {
        path: GenerateEvaluator(checker._ctx)._precompute_generate_active(fr)
        for path, fr in checker._ctx.memo.items()
    }
    return plugin, engine


# ── 1. 声明面 ──

@pytest.mark.smoke
def test_verilog_pack_declares_gen_activity(checker):
    """语言包必须声明 `gen_activity` 项（含角色位与依赖）——缺声明即静默退化为不过滤。"""
    checker._prepare_run([])
    spec = load_elaborator_spec("grammar/verilog")
    assert spec is not None
    item = next(it for it in spec.items if it.name == "gen_activity")
    assert item.scope == "file"
    assert item.role == ROLE_GEN_ACTIVITY
    assert item.provides == ("gen_activity",)
    # 条件求值要单元常量表 → 必须声明依赖（引擎据此定序）
    assert item.depends_on == ("param_default",)
    order = [it.name for it in spec.order()]
    assert order.index("param_default") < order.index("gen_activity")


# ── 2. 等价性对拍（删旧实现的前提） ──

@pytest.mark.parametrize("fixture_name", ["real", "decided"])
def test_plugin_matches_engine_per_node(checker, decided, fixture_name):
    """逐文件、逐节点比对：插件产物 == 引擎旧实现。"""
    checker.check(_FIXTURE_REAL if fixture_name == "real" else str(decided))
    plugin, engine = _gen_maps(checker)

    assert set(plugin) == set(engine), "产物覆盖的文件集与引擎不一致"
    assert engine, "夹具没被解析（空索引 → 对拍退化成空转）"
    for path, engine_map in engine.items():
        assert plugin[path] == engine_map, f"文件 {path} 的节点活性不一致"
        assert engine_map, f"文件 {path} 的活性表为空"


def test_decided_branch_is_actually_filtered(checker, decided):
    """**不空转**：可判条件（裸参数 `EN`）确实过滤掉了未选中分支。

    若插件的 `depends_on` 通道失效（拿不到参数表），该条件会退化为不可判 → 整个
    generate 块按活跃展开 → 产物里不再有 `False`。故本断言与对拍一起守依赖通道。
    """
    checker.check(str(decided))
    plugin, engine = _gen_maps(checker)
    values = [v for m in plugin.values() for v in m.values()]
    assert values, "产物为空"
    assert False in values, "没有节点被判未选中 → 条件求值没生效（参数表丢了？）"
    assert True in values, "全部未选中 → 活性判定反了"
    # 且引擎侧同样如此（同一语义）
    assert False in [v for m in engine.values() for v in m.values()]


def test_real_corpus_conditions_are_undecidable_today(checker):
    """真实语料那条 `DATA_WIDTH > 8` **今天判不了**（参数名与运算符混排）。

    锁住这个**已知边界**（gap 档「求值能力」条）：不是本项回归，而是求值器能力的
    现状——全 True = 不误删分支（保守方向）。将来若扩求值能力，本用例应随之更新，
    届时"全 True"的假设不成立，对拍夹具的选择也要重审。
    """
    checker.check(_FIXTURE_REAL)
    plugin, _ = _gen_maps(checker)
    values = [v for m in plugin.values() for v in m.values()]
    assert values and all(values), (
        "真实夹具出现 False → 求值能力已扩展；请更新本用例与测试文件头的说明"
    )


# ── 3. 引擎侧旧实现仍在（P3-①a 过渡期登记） ──

def test_engine_side_gen_evaluator_still_present(checker, decided):
    """P3-①a 过渡期：引擎侧 `GenerateEvaluator` 与插件产物**并存**（对拍成立后才删）。

    本用例是"双路径"的显式登记——**随 P3-①b（删引擎侧）一起删除**。
    """
    checker.check(str(decided))
    fr = next(iter(checker._ctx.memo.values()))
    engine_map = GenerateEvaluator(checker._ctx)._precompute_generate_active(fr)
    assert engine_map, "引擎侧旧实现没产出（过渡期登记失去意义）"
